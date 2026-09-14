"""novel2all Web UI（FastAPI + SSE SPA）。

v0.20 基础：项目状态 + skill 列表 + role 列表 + tracking state
v0.21 Step 3：SSE 流式写作端点 + 前端实时显示
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.memory import MemoryManager, Tracker
from novel2all.core.pipeline import (
    BlockingIssuesError,
    OutlineNotFoundError,
    PipelineCancelledError,
    WritingPipeline,
)
from novel2all.core.project import ProjectStructure
from novel2all.core.role import RoleRegistry
from novel2all.core.skill import SkillRegistry

logger = logging.getLogger(__name__)

# V0.30.0：Jinja2 模板 + 静态文件（HTMX 2.x + Alpine.js 3.x 本地化）
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# === SSE 工具函数 ===


def sse_event(event: str, data: dict[str, Any]) -> str:
    """格式化为 SSE 事件字符串。

    格式：
        event: <event>
        data: <json>

        （以 \\n\\n 结束）
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """V0.29.3：app 启动时建全局 LLMProvider 单例，关闭时清理。

        之前 V0.27 之前：每次请求都新建 LLMProvider，导致：
        - cache stats（hits/misses）每次请求重置，命中率永远显示 0
        - 重复初始化开销（load .env、读 MODEL_CONFIG）
        - V0.30 WebUI 暴露 cache 命中率时无法跨请求累计

        收益：cache 跨请求连续、stats 稳定、单进程多请求共享 provider
        """
        load_dotenv(".env", override=False)
        app.state.provider = LLMProvider(LLMConfig())
        # V0.31：活跃 pipeline task 注册表（用于 /api/write/cancel/{task_id} 取消正在运行的写作任务）
        # key = task_id (uuid4 hex[:8])，value = asyncio.Task
        app.state.active_pipelines = {}
        logger.info(
            "Web app started: LLMProvider initialized (model=%s, cache_enabled=%s)",
            app.state.provider.config.default_model,
            app.state.provider.config.cache_enabled,
        )
        try:
            yield
        finally:
            # 清理：打印最终 cache stats（debug 用）
            stats = app.state.provider.cache_stats()
            logger.info(
                "Web app shutting down: cache stats=%s",
                stats,
            )
            # V0.42：显式关闭 cache backend（SQLite 连接池等）
            app.state.provider.close()
            del app.state.provider

    app = FastAPI(
        title="novel2all Web UI",
        version="0.21.0",
        lifespan=lifespan,
    )

    # V0.30.0：mount 静态文件（HTMX + Alpine.js 本地化，零 CDN 依赖）
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # V0.29.3：测试 fallback（TestClient 默认不触发 lifespan 上下文）
    # 生产路径走 lifespan；测试路径直接初始化 provider
    # 这样 `app = create_app(); client = TestClient(app)` 也能工作
    if not hasattr(app.state, "provider"):
        load_dotenv(".env", override=False)
        app.state.provider = LLMProvider(LLMConfig())

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """V0.30.0：渲染 base.html + index.html（Jinja2 模板）。"""
        return templates.TemplateResponse(request, "index.html")

    @app.get("/api/status")
    async def status(project_root: str = ".") -> dict:
        root = Path(project_root).resolve()
        tracker = Tracker(root / "_tracking-state.json")
        if not tracker.exists():
            return {"initialized": False, "project_root": str(root)}
        state = tracker.read()
        return {
            "initialized": True,
            "project_root": str(root),
            "project_name": state.project_name,
            "genre": state.genre,
            "style_anchor": state.style_anchor,
            "total_chapters_target": state.total_chapters_target,
            "total_word_count_target": state.total_word_count_target,
            "last_updated_chapter": state.last_updated_chapter,
            "character_count": len(state.characters),
            "active_foreshadowing_count": len(
                [f for f in state.foreshadowing.values() if f.status == "active"]
            ),
            "timeline_count": len(state.timeline),
            "summary_count": len(state.recent_chapter_summaries),
        }

    @app.get("/api/skills")
    async def list_skills() -> list[dict]:
        skills_dir = Path(__file__).parent.parent / "skills"
        registry = SkillRegistry(skills_dir)
        registry.discover()
        return [
            {
                "name": s.name,
                "description": s.description,
                "user_invocable": s.user_invocable,
                "model_invocable": s.model_invocable,
            }
            for s in registry.list()
        ]

    @app.get("/api/roles")
    async def list_roles() -> list[dict]:
        roles_dir = Path(__file__).parent.parent / "roles"
        registry = RoleRegistry(roles_dir)
        registry.discover()
        return [
            {
                "name": r.name,
                "description": r.description,
                "preferred_model": r.preferred_model,
            }
            for r in registry.list()
        ]

    # V0.30.0：HTMX 局部更新端点（返回 HTML 片段而非 JSON）
    @app.get("/page/status", response_class=HTMLResponse)
    async def page_status(request: Request, project_root: str = ".") -> HTMLResponse:
        """HTMX 用：渲染 status_partial.html。"""
        root = Path(project_root).resolve()
        tracker = Tracker(root / "_tracking-state.json")
        if not tracker.exists():
            return templates.TemplateResponse(
                request,
                "status_partial.html",
                {"initialized": False, "project_root": str(root)},
            )
        state = tracker.read()
        return templates.TemplateResponse(
            request,
            "status_partial.html",
            {
                "initialized": True,
                "project_root": str(root),
                "project_name": state.project_name,
                "genre": state.genre,
                "style_anchor": state.style_anchor,
                "total_chapters_target": state.total_chapters_target,
                "total_word_count_target": state.total_word_count_target,
                "last_updated_chapter": state.last_updated_chapter,
                "character_count": len(state.characters),
                "active_foreshadowing_count": len(
                    [f for f in state.foreshadowing.values() if f.status == "active"]
                ),
                "timeline_count": len(state.timeline),
                "summary_count": len(state.recent_chapter_summaries),
            },
        )

    @app.get("/page/skills", response_class=HTMLResponse)
    async def page_skills(request: Request) -> HTMLResponse:
        """HTMX 用：渲染 skills_partial.html。"""
        skills_dir = Path(__file__).parent.parent / "skills"
        registry = SkillRegistry(skills_dir)
        registry.discover()
        skills = [
            {
                "name": s.name,
                "description": s.description,
                "user_invocable": s.user_invocable,
                "model_invocable": s.model_invocable,
            }
            for s in registry.list()
        ]
        return templates.TemplateResponse(request, "skills_partial.html", {"skills": skills})

    @app.get("/page/roles", response_class=HTMLResponse)
    async def page_roles(request: Request) -> HTMLResponse:
        """HTMX 用：渲染 roles_partial.html。"""
        roles_dir = Path(__file__).parent.parent / "roles"
        registry = RoleRegistry(roles_dir)
        registry.discover()
        roles = [
            {
                "name": r.name,
                "description": r.description,
                "preferred_model": r.preferred_model,
            }
            for r in registry.list()
        ]
        return templates.TemplateResponse(request, "roles_partial.html", {"roles": roles})

    # V0.30.1：模型选择器 + 写章节表单（HTMX partial）
    @app.get("/page/model-selector", response_class=HTMLResponse)
    async def page_model_selector(request: Request) -> HTMLResponse:
        """HTMX 用：渲染 model_selector.html（带当前模型 + 可选列表）。"""
        from novel2all.core.provider_router import MODEL_CONFIG

        provider: LLMProvider = request.app.state.provider
        models = [
            {
                "name": name,
                "anthropic_compat": bool(cfg.api_base and "anthropic" in cfg.api_base),
                "api_base": cfg.api_base,
                "api_key_env": cfg.api_key_env,
            }
            for name, cfg in MODEL_CONFIG.items()
        ]
        return templates.TemplateResponse(
            request,
            "model_selector.html",
            {"models": models, "current_model": provider.config.default_model},
        )

    @app.get("/page/write-form", response_class=HTMLResponse)
    async def page_write_form(request: Request) -> HTMLResponse:
        """HTMX 用：渲染 write_form.html（带模型下拉 + 流式提交按钮）。"""
        from novel2all.core.provider_router import MODEL_CONFIG

        provider: LLMProvider = request.app.state.provider
        models = [
            {
                "name": name,
                "anthropic_compat": bool(cfg.api_base and "anthropic" in cfg.api_base),
                "api_base": cfg.api_base,
                "api_key_env": cfg.api_key_env,
            }
            for name, cfg in MODEL_CONFIG.items()
        ]
        return templates.TemplateResponse(
            request,
            "write_form.html",
            {"models": models, "current_model": provider.config.default_model},
        )

    # V0.30.2：Cache 命中率面板（暴露 V0.24 + V0.29.0 LRU）
    @app.get("/page/cache-panel", response_class=HTMLResponse)
    async def page_cache_panel(request: Request) -> HTMLResponse:
        """HTMX 用：渲染 cache_panel.html（含 hit_rate 颜色逻辑 + LRU 进度条）。"""
        provider: LLMProvider = request.app.state.provider
        stats = provider.cache_stats()
        return templates.TemplateResponse(request, "cache_panel.html", {"stats": stats})

    # V0.34：章节编辑器（手动编辑 + AI 扩写引导）
    @app.get("/page/chapter-edit", response_class=HTMLResponse)
    async def page_chapter_edit(request: Request) -> HTMLResponse:
        """V0.34：章节编辑器页面（Alpine.js 加载章节内容 + textarea + 保存/扩写按钮）。"""
        return templates.TemplateResponse(request, "chapter_edit.html")

    @app.get("/api/cache/stats")
    async def cache_stats(request: Request) -> dict[str, Any]:
        """V0.29.3：返回 lifespan provider 的 cache 统计。

        V0.30 WebUI 暴露此端点做实时命中率面板。
        V0.30.6 C1：额外包含 prompt_prefix 子字典（量化 prefix cache 节省）。
        """
        provider: LLMProvider = request.app.state.provider
        return provider.cache_stats()

    # V0.30.6 C1：Prompt prefix cache 专用端点
    @app.get("/api/cache/prompt-stats")
    async def prompt_cache_stats(request: Request) -> dict[str, Any]:
        """V0.30.6 C1：返回 prompt prefix cache 统计。

        与 /api/cache/stats["prompt_prefix"] 等价，但更直接。
        用于 Web UI "prompt prefix 节省 ¥" 卡片 + benchmark 验证脚本。

        Returns:
            dict 含 prefix_hits/misses/total/hit_rate/unique_sys_prompts/
            cost_saved_cny/potential_savings_cny + model 参数
        """
        provider: LLMProvider = request.app.state.provider
        return provider.prompt_cache_stats()

    @app.post("/api/cache/prompt-stats/reset")
    async def reset_prompt_cache_stats(request: Request) -> dict[str, Any]:
        """V0.30.6 C1：重置 prompt prefix cache 统计（手动 reset）。"""
        provider: LLMProvider = request.app.state.provider
        provider.reset_prompt_cache_stats()
        return {"reset": True, "stats": provider.prompt_cache_stats()}

    # V0.30.6 C1：HTMX partial — prompt cache panel
    @app.get("/page/prompt-cache-panel", response_class=HTMLResponse)
    async def page_prompt_cache_panel(request: Request) -> HTMLResponse:
        """V0.30.6 C1：HTMX 渲染 prompt prefix cache 面板（每 30s 刷新）。

        实时显示 prefix hit rate + cost saved，激励用户：
        - 复用 system prompt（多章节共用同一角色卡）
        - 避免频繁更换写作风格
        """
        provider: LLMProvider = request.app.state.provider
        stats = provider.prompt_cache_stats()
        return templates.TemplateResponse(request, "prompt_cache_panel.html", {"stats": stats})

    # V0.43：Cache 迁移端点（POST 表单）
    @app.post("/api/cache/migrate")
    async def cache_migrate(
        src: str = Form(...),
        dst: str = Form(...),
        src_backend: str = Form("auto"),
        dst_backend: str = Form("auto"),
        max_size: int = Form(1024),
        ttl_seconds: int = Form(0),
    ) -> dict[str, Any]:
        """V0.43：在不同 cache backend 之间平滑迁移（零数据丢失）。

        Form 参数：
        - src: 源 cache 文件路径
        - dst: 目标 cache 文件路径
        - src_backend/dst_backend: "json" / "sqlite" / "auto"（按扩展名自动检测）
        - max_size: 目标 max_size
        - ttl_seconds: 目标 TTL

        返回：MigrationResult 转 dict（含 migrated/errors/elapsed 等）
        """
        from novel2all.core.migration import migrate_cache

        # auto-detect backend
        if src_backend == "auto":
            if src.endswith(".json"):
                src_backend = "json"
            elif src.endswith((".db", ".sqlite")):
                src_backend = "sqlite"
            elif src.startswith("redis://"):
                src_backend = "redis"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"无法自动检测 src backend（{src}）",
                )
        if dst_backend == "auto":
            if dst.endswith(".json"):
                dst_backend = "json"
            elif dst.endswith((".db", ".sqlite")):
                dst_backend = "sqlite"
            elif dst.startswith("redis://"):
                dst_backend = "redis"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"无法自动检测 dst backend（{dst}）",
                )

        if src_backend == "memory" or dst_backend == "memory":
            raise HTTPException(
                status_code=400,
                detail="memory backend 不支持迁移（无持久化）",
            )

        try:
            result = migrate_cache(
                src_backend=src_backend,
                dst_backend=dst_backend,
                src_path=src,
                dst_path=dst,
                max_size=max_size,
                ttl_seconds=ttl_seconds,
            )
        except Exception as e:
            logger.exception("V0.43 cache_migrate failed")
            raise HTTPException(status_code=500, detail=f"迁移失败: {e}")

        return {
            "src_backend": result.src_backend,
            "dst_backend": result.dst_backend,
            "src_path": result.src_path,
            "dst_path": result.dst_path,
            "total_entries": result.total_entries,
            "migrated": result.migrated,
            "skipped_expired": result.skipped_expired,
            "errors": result.errors,
            "elapsed_seconds": result.elapsed_seconds,
        }

    # V0.51：Cache 配置智能推荐端点
    @app.get("/api/cache/recommend")
    async def cache_recommend(request: Request) -> dict[str, Any]:
        """V0.51：根据 cache_stats() + 当前 LLMConfig 推荐 backend / max_size / ttl_seconds。

        返回结构见 CacheRecommendation.to_dict()：
        - current: 当前配置
        - recommended: 各字段推荐值 + 理由 + 预期影响 + 置信度
        - actions: 立即可执行的动作列表（含 how-to 步骤）
        - health_score: 0.0-1.0
        - issues: 检测到的问题列表
        - confidence: 整体置信度（high/medium/low）
        - notes: 备注（如数据不足警告）

        算法：见 novel2all.core.cache_recommend.recommend_cache_config()
        """
        from novel2all.core.cache_recommend import recommend_cache_config

        provider: LLMProvider = request.app.state.provider
        stats = provider.cache_stats()
        config = provider.config

        rec = recommend_cache_config(
            stats=stats,
            current_backend=config.cache_backend,
            current_max_size=config.cache_max_size,
            current_ttl_seconds=config.cache_ttl_seconds,
        )
        return rec.to_dict()

    # V0.51：Cache 推荐面板（HTMX partial 渲染）
    @app.get("/page/cache-recommend", response_class=HTMLResponse)
    async def page_cache_recommend(request: Request) -> HTMLResponse:
        """V0.51：HTMX 渲染推荐面板（含健康评分 + 推荐动作列表）。"""
        from novel2all.core.cache_recommend import recommend_cache_config

        provider: LLMProvider = request.app.state.provider
        stats = provider.cache_stats()
        config = provider.config

        rec = recommend_cache_config(
            stats=stats,
            current_backend=config.cache_backend,
            current_max_size=config.cache_max_size,
            current_ttl_seconds=config.cache_ttl_seconds,
        )
        return templates.TemplateResponse(
            request,
            "cache_recommend.html",
            {"rec": rec.to_dict()},
        )

    # V0.30.1：模型选择器 API
    @app.get("/api/models")
    async def list_models() -> list[dict[str, Any]]:
        """V0.30.1：列出 MODEL_CONFIG 中所有可用模型。

        前端模型选择器用。每条含：
        - name：模型名（litellm 格式，如 "minimax/MiniMax-M3"）
        - anthropic_compat：是否走 anthropic Messages API 路径
        - api_base：自定义 endpoint（None = 用 litellm 默认）
        - api_key_env：环境变量名（None = 用 LLMConfig 默认）
        """
        from novel2all.core.provider_router import MODEL_CONFIG

        models = []
        for name, cfg in MODEL_CONFIG.items():
            models.append(
                {
                    "name": name,
                    "anthropic_compat": bool(cfg.api_base and "anthropic" in cfg.api_base),
                    "api_base": cfg.api_base,
                    "api_key_env": cfg.api_key_env,
                }
            )
        return models

    @app.get("/api/model/current")
    async def get_current_model(request: Request) -> dict[str, str]:
        """V0.30.1：返回当前 provider 的 default_model。"""
        provider: LLMProvider = request.app.state.provider
        return {"model": provider.config.default_model}

    @app.post("/api/model/switch")
    async def switch_model(request: Request, model: str = Form(...)) -> dict[str, str]:
        """V0.30.1：切换 provider 的 default_model。

        切换后：
        - 后续 complete()/stream() 不传 model 参数时用新 model
        - 已创建的 provider（lifespan 单例）保持
        - cache stats 不受影响（LRU 保留）
        """
        from novel2all.core.provider_router import MODEL_CONFIG

        provider: LLMProvider = request.app.state.provider
        if model not in MODEL_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"未知模型: {model}。可选: {', '.join(MODEL_CONFIG.keys())}",
            )
        old_model = provider.config.default_model
        provider.config.default_model = model
        logger.info("V0.30.1: 模型切换 %s → %s", old_model, model)
        return {"old_model": old_model, "new_model": model}

    @app.post("/api/write/stream/model")
    async def write_stream_with_model(
        request: Request,
        chapter: int = Form(...),
        project_root: str = Form("."),
        skill: str = Form("story-long-write"),
        model: str | None = Form(None),
        min_chars: int = Form(2000),
        skip_pre_write: bool = Form(False),
        resume_from_chars: int = Form(0),  # V0.32：0 = 正常开始，>0 = 接续模式
    ) -> StreamingResponse:
        """V0.30.1：带 model 参数的流式写作端点（V0.29.3 单例 + V0.30 WebUI 集成）。

        复用了原 /api/write/stream 的逻辑，但接受 Form 参数（HTMX 友好）。

        V0.31：在 'started' 事件里 yield task_id（uuid4 hex[:8]），
        注册到 app.state.active_pipelines，让 /api/write/cancel/{task_id} 能取消。
        Pipeline 抛 PipelineCancelledError 时 yield 'cancelled' 事件（partial content 信息）。

        V0.32：接受 resume_from_chars 参数 → pipeline 接续 partial content 写。
        """
        # V0.30.1：用请求中的 model（不污染单例）
        from novel2all.cli.main import get_llm_for_model

        # V0.31：生成 task_id 提前（即便后续初始化失败也要返回 task_id 用于排查）
        task_id = uuid.uuid4().hex[:8]

        async def event_stream() -> AsyncIterator[str]:
            llm: LLMProvider = get_llm_for_model(model)
            root = Path(project_root).resolve()
            project = ProjectStructure(root=root)
            if not project.exists():
                yield sse_event(
                    "error",
                    {
                        "message": f"项目未初始化: {root}. 请先跑 novel2all setup.",
                        "task_id": task_id,
                    },
                )
                return

            yield sse_event(
                "started",
                {
                    "task_id": task_id,  # V0.31：让前端能调用 /api/write/cancel/{task_id}
                    "chapter": chapter,
                    "skill": skill,
                    "model": model or "default",
                    "min_chars": min_chars,
                    "skip_pre_write": skip_pre_write,
                    "resume_from_chars": resume_from_chars,  # V0.32
                    "project_root": str(root),
                },
            )

            try:
                manager = MemoryManager(project_root=root, llm=llm)
                skills_dir = Path(__file__).parent.parent / "skills"
                skill_registry = SkillRegistry(skills_dir)
                skill_registry.discover()
                pipeline = WritingPipeline(
                    manager=manager,
                    skill_registry=skill_registry,
                    llm=llm,
                    project=project,
                )
            except Exception as e:
                yield sse_event("error", {"message": f"Pipeline 初始化失败: {e}"})
                return

            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            collected: list[str] = []

            def on_chunk(text: str) -> None:
                collected.append(text)
                chunk_queue.put_nowait(text)

            async def run_pipeline() -> None:
                try:
                    await pipeline.write_chapter(
                        chapter=chapter,
                        outline_path=project.chapter_outline(chapter),
                        skill_name=skill,
                        stream_callback=on_chunk,
                        min_chars=min_chars,
                        skip_pre_write_check=skip_pre_write,
                        resume_from_chars=resume_from_chars,  # V0.32
                    )
                finally:
                    await chunk_queue.put(None)

            pipeline_task = asyncio.create_task(run_pipeline())
            # V0.31：注册到 app.state.active_pipelines（让 cancel endpoint 能找到）
            request.app.state.active_pipelines[task_id] = pipeline_task
            try:
                while True:
                    chunk = await chunk_queue.get()
                    if chunk is None:
                        break
                    yield sse_event("chunk", {"text": chunk})

                # V0.31：先取 pipeline_task 结果（可能抛 PipelineCancelledError）
                try:
                    result = await pipeline_task
                except PipelineCancelledError as cancel_exc:
                    # 用户中途取消 → 已保存 partial content 到 output_path
                    partial_content = "".join(collected)
                    yield sse_event(
                        "cancelled",
                        {
                            "task_id": task_id,
                            "chapter": cancel_exc.chapter,
                            "partial_chars": cancel_exc.partial_chars,
                            "output_path": str(cancel_exc.output_path),
                            "preview": partial_content[:200],
                            "message": (
                                f"已在 {cancel_exc.partial_chars} 字处取消，"
                                f"内容已保存到 {cancel_exc.output_path.name}"
                            ),
                        },
                    )
                    return

                if result.pre_write_issues:
                    yield sse_event(
                        "pre_write_check",
                        {"issues": [issue.model_dump() for issue in result.pre_write_issues]},
                    )

                yield sse_event(
                    "progress",
                    {"phase": "save", "message": f"已写文件: {result.output_path}"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "extract", "message": "提取角色/伏笔/时间线"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "merge", "message": "合并到 tracking state"},
                )

                if result.post_write_issues:
                    yield sse_event(
                        "post_write_check",
                        {"issues": [issue.model_dump() for issue in result.post_write_issues]},
                    )

                yield sse_event(
                    "done",
                    {
                        "task_id": task_id,
                        "output_path": str(result.output_path),
                        "content_chars": result.content_chars,
                        "resumed_from_chars": result.resumed_from_chars,  # V0.32
                        "post_issue_count": len(result.post_write_issues),
                        "pre_issue_count": len(result.pre_write_issues),
                    },
                )

            except OutlineNotFoundError as e:
                yield sse_event("error", {"message": str(e), "code": "outline_not_found"})
            except BlockingIssuesError as e:
                yield sse_event(
                    "error",
                    {
                        "message": f"pre-write check 发现 {len(e.issues)} 个 critical 问题",
                        "code": "blocking_issues",
                        "issues": [issue.model_dump() for issue in e.issues],
                    },
                )
            except Exception as e:
                if pipeline_task.done() and pipeline_task.exception():
                    exc = pipeline_task.exception()
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(exc).__name__}: {exc}"},
                    )
                else:
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(e).__name__}: {e}"},
                    )
            finally:
                # V0.31：无论成功/失败/取消，都从注册表移除
                request.app.state.active_pipelines.pop(task_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # V0.31：取消正在运行的 pipeline 任务
    @app.post("/api/write/cancel/{task_id}")
    async def cancel_write_task(task_id: str, request: Request) -> dict[str, Any]:
        """V0.31：取消 task_id 对应的 pipeline 任务。

        取消后：
        - pipeline 协程收到 CancelledError，捕获后保存 partial content 到 <chapter>.md
        - SSE 流发送 'cancelled' 事件（partial_chars + output_path）
        - 任务从 app.state.active_pipelines 注册表移除

        Returns:
            200 + {"task_id": ..., "status": "cancelled"} 成功取消
            404 + {"task_id": ..., "status": "not_found"} task_id 不存在（已完成/已取消）
        """
        pipeline_task = request.app.state.active_pipelines.get(task_id)
        if pipeline_task is None or pipeline_task.done():
            raise HTTPException(
                status_code=404,
                detail=f"task {task_id} 不存在或已完成",
            )
        pipeline_task.cancel()
        logger.info("V0.31 cancel: pipeline task %s cancelled", task_id)
        return {"task_id": task_id, "status": "cancelling"}

    @app.get("/api/write/active")
    async def list_active_pipelines(request: Request) -> list[dict[str, Any]]:
        """V0.31：列出当前活跃的 pipeline task（调试用）。

        Returns:
            [{"task_id": ..., "done": False, "cancelled": False}, ...]
        """
        result = []
        for tid, task in request.app.state.active_pipelines.items():
            result.append(
                {
                    "task_id": tid,
                    "done": task.done(),
                    "cancelled": task.cancelled() if hasattr(task, "cancelled") else False,
                }
            )
        return result

    @app.get("/api/tracking")
    async def get_tracking(project_root: str = ".") -> dict:
        root = Path(project_root).resolve()
        tracker = Tracker(root / "_tracking-state.json")
        if not tracker.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        state = tracker.read()
        return state.model_dump(mode="json")

    @app.get("/api/chapters")
    async def list_chapters(project_root: str = ".") -> list[dict]:
        """列出项目下已写章节。"""
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            return []
        result: list[dict] = []
        prose_dir = project.chapter_prose(1).parent  # 正文/ 目录
        if not prose_dir.exists():
            return []
        # 找所有 第NNN章.md
        import re

        for f in sorted(prose_dir.glob("第*章.md")):
            m = re.match(r"^第(\d+)章\.md$", f.name)
            if not m:
                continue
            ch = int(m.group(1))
            text = f.read_text(encoding="utf-8")
            result.append(
                {
                    "chapter": ch,
                    "filename": f.name,
                    "char_count": len(text),
                    "first_line": text.split("\n", 1)[0].strip()[:80],
                }
            )
        return result

    @app.get("/api/chapter/{chapter}/content")
    async def get_chapter_content(
        chapter: int,
        project_root: str = Query(".", description="项目根目录"),
    ) -> dict:
        """获取指定章节的完整内容。"""
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found")
        text_content = prose_path.read_text(encoding="utf-8")
        return {
            "chapter": chapter,
            "filename": prose_path.name,
            "content": text_content,
            "char_count": len(text_content),
            "first_line": text_content.split("\n", 1)[0].strip()[:120],
        }

    # V0.30.6 B6：章节导出端点
    @app.get("/api/chapter/{chapter}/export")
    async def export_chapter(
        chapter: int,
        format: str = Query("md", description="导出格式: md | txt | epub"),
        project_root: str = Query(".", description="项目根目录"),
    ) -> Response:
        """V0.30.6 B6：导出单章节为指定格式。

        支持格式：
        - md：Markdown（直接透传 + 标准 frontmatter）
        - txt：纯文本（剥离 markdown 语法）
        - epub：EPUB 3.0（单章节 + 元数据）

        Returns:
            Response: 带 Content-Disposition 头的文件流
        """
        from novel2all.core.exporter import (
            Chapter,
            get_exporter,
        )

        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")

        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found")

        try:
            ch = Chapter.from_md_file(prose_path)
            exporter = get_exporter(format)
            content_bytes = exporter.export_chapter(ch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("V0.30.6 B6 export_chapter failed")
            raise HTTPException(status_code=500, detail=f"Export failed: {e}") from e

        return Response(
            content=content_bytes,
            media_type=exporter.mime_type(),
            headers={
                # V0.30.6 B6: ASCII-safe filename（HTTP header 必须 latin-1）
                "Content-Disposition": (
                    f'attachment; filename="chapter_{chapter:03d}.{exporter.file_extension()}"'
                ),
            },
        )

    # V0.30.6 B6：批量导出端点（整本书）
    @app.get("/api/export")
    async def export_project(
        format: str = Query("epub", description="导出格式: md | txt | epub"),
        project_root: str = Query(".", description="项目根目录"),
        title: str = Query("", description="书名（EPUB 用）"),
        author: str = Query("", description="作者（EPUB 用）"),
    ) -> Response:
        """V0.30.6 B6：导出整本书为指定格式（自动发现所有 chapter）。

        支持格式：
        - md：单文件 Markdown（多章节拼接）
        - txt：纯文本（多章节拼接）
        - epub：EPUB 3.0（含导航 + 元数据 + 完整结构）
        """
        from novel2all.core.exporter import BookMetadata
        from novel2all.core.exporter import export_project as do_export

        root = Path(project_root).resolve()
        try:
            metadata = BookMetadata(
                title=title or "未命名作品",
                author=author or "未知作者",
            )
            content_bytes = do_export(root, format, metadata)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("V0.30.6 B6 export_project failed")
            raise HTTPException(status_code=500, detail=f"Export failed: {e}") from e

        from novel2all.core.exporter import get_exporter

        exporter = get_exporter(format)
        # V0.30.6 B6: HTTP header latin-1 only, so strip non-ASCII
        import re as _re

        safe_title = (title or "未命名作品").replace("/", "_").replace("\\", "_")
        safe_title_ascii = _re.sub(r"[^\\w\\-]", "_", safe_title) or "novel"
        return Response(
            content=content_bytes,
            media_type=exporter.mime_type(),
            headers={
                # V0.30.6 B6: ASCII-safe filename
                "Content-Disposition": (
                    f'attachment; filename="{safe_title_ascii}.{exporter.file_extension()}"'
                ),
            },
        )

    # V0.34：手动保存编辑后的章节
    @app.post("/api/chapter/{chapter}/save")
    async def save_chapter_content(
        chapter: int,
        request: Request,
        content: str = Form(...),
        project_root: str = Form("."),
    ) -> dict[str, Any]:
        """V0.34：保存用户手动编辑的章节内容（覆盖章节文件）。

        流程：
        1. 写入 chapter_prose(chapter) 文件
        2. 同步 _tracking-state.json 的 last_updated_chapter（让 UI 知道最新进度）
        3. 不调 update_after_writing（手动编辑不走 LLM 提取）

        Returns:
            200 + {"chapter": ..., "char_count": ..., "output_path": "..."}
            404 + 错误信息
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")

        prose_path = project.chapter_prose(chapter)
        prose_path.parent.mkdir(parents=True, exist_ok=True)
        prose_path.write_text(content, encoding="utf-8")

        # 同步 tracking state（不更新角色/伏笔/时间线，因为没有 LLM 提取）
        tracker = Tracker(root / "_tracking-state.json")
        if tracker.exists():
            state = tracker.read()
            if state.last_updated_chapter is None or chapter > state.last_updated_chapter:
                state.last_updated_chapter = chapter
                state.last_updated_at = datetime.now(tz=UTC)
                tracker.write(state)

        logger.info(
            "V0.34 save: 第 %s 章已手动保存 %d 字到 %s",
            chapter,
            len(content),
            prose_path,
        )
        return {
            "chapter": chapter,
            "char_count": len(content),
            "output_path": str(prose_path),
        }

    # V0.34：AI 扩写（从当前字数继续写）
    @app.post("/api/chapter/{chapter}/expand")
    async def expand_chapter(
        chapter: int,
        request: Request,
        project_root: str = Form("."),
        skill: str = Form("story-long-write"),
        min_chars: int = Form(1000),
    ) -> dict[str, Any]:
        """V0.34：AI 扩写 — 从当前章节末尾继续写 N 字（基于 V0.32 智能恢复）。

        流程：
        1. 读取 chapter_prose(chapter) 当前内容
        2. 调 pipeline.write_chapter(resume_from_chars=len(current))
        3. 走 LLM → 流式 SSE 输出（与 V0.32 一致）

        注意：实际流式输出在 /api/write/stream/model；本端点仅作为元数据检查。
        实际扩写请用 POST /api/write/stream/model + resume_from_chars。
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter} not found. Use /api/write/stream/model first.",
            )
        current_content = prose_path.read_text(encoding="utf-8")
        return {
            "chapter": chapter,
            "current_chars": len(current_content),
            "expand_endpoint": "/api/write/stream/model",
            "form_params": {
                "chapter": chapter,
                "project_root": str(root).replace("\\", "/"),
                "skill": skill,
                "min_chars": min_chars,
                "resume_from_chars": len(current_content),
            },
            "hint": "POST 表单到 /api/write/stream/model 触发扩写",
        }

    # V0.38：AI 重写指定区段
    @app.post("/api/chapter/{chapter}/rewrite")
    async def rewrite_section(
        chapter: int,
        start: int = Form(...),
        end: int = Form(...),
        instruction: str = Form("改写得更生动自然"),
        project_root: str = Form("."),
        model: str | None = Form(None),
    ) -> dict[str, Any]:
        """V0.38：LLM 改写章节中指定字符范围 [start, end)。

        Args:
            start: 起始字符位置（0-based）
            end: 结束字符位置（exclusive）
            instruction: 改写指令（默认"改写得更生动自然"）

        Returns:
            dict 含 original / rewritten / start / end / chapter / model

        注意：本端点只生成 LLM 改写结果，不直接修改文件。
        前端应在用户确认后调 /api/chapter/{n}/save 应用修改。
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter} not found",
            )
        full_content = prose_path.read_text(encoding="utf-8")
        total = len(full_content)
        if start < 0 or end > total or start >= end:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid range [{start}:{end}] for content length {total}",
            )
        selected = full_content[start:end]
        before = full_content[:start]
        after = full_content[end:]

        # 调 LLM 改写
        from novel2all.cli.main import get_llm_for_model

        llm = get_llm_for_model(model)
        system = (
            "你是一位专业的中文小说编辑。根据用户指令改写指定段落，"
            "保持原文风格、人称和情节连续性，只输出改写后的段落文本本身（不含任何前后缀）。"
        )
        user_prompt = (
            f"##原文（{len(selected)} 字）\n{selected}\n\n"
            f"##改写要求\n{instruction}\n\n"
            "##输出要求\n只输出改写后的段落文本，不要加任何说明、注释、引号或前后缀。"
        )
        try:
            rewritten = await llm.complete(
                prompt=user_prompt, system=system, max_tokens=2000, temperature=0.7
            )
        except Exception as e:
            logger.exception("V0.38 rewrite_section: LLM call failed")
            raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e
        rewritten_clean = rewritten.strip()
        logger.info(
            "V0.38 rewrite: 第 %s 章 [%s:%s] %s字 → %s字",
            chapter,
            start,
            end,
            len(selected),
            len(rewritten_clean),
        )
        return {
            "chapter": chapter,
            "start": start,
            "end": end,
            "original": selected,
            "rewritten": rewritten_clean,
            "before_len": len(before),
            "after_len": len(after),
            "model": model or "default",
        }

    # V0.38：在指定位置插入 AI 生成的内容
    @app.post("/api/chapter/{chapter}/insert")
    async def insert_at_position(
        chapter: int,
        position: int = Form(...),
        instruction: str = Form("自然衔接上下文的过渡段落"),
        project_root: str = Form("."),
        model: str | None = Form(None),
        context_chars: int = Form(500),
    ) -> dict[str, Any]:
        """V0.38：LLM 在 position 处生成可插入的内容（前后各取 context_chars 字上下文）。

        Returns:
            dict 含 position / inserted / chapter / model

        注意：本端点只生成 LLM 插入内容，不直接修改文件。
        前端应在用户确认后调 /api/chapter/{n}/save 应用修改。
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter} not found",
            )
        full_content = prose_path.read_text(encoding="utf-8")
        total = len(full_content)
        if position < 0 or position > total:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid position {position} for content length {total}",
            )
        # 取上下文
        ctx_start = max(0, position - context_chars)
        ctx_end = min(total, position + context_chars)
        before_ctx = full_content[ctx_start:position]
        after_ctx = full_content[position:ctx_end]

        from novel2all.cli.main import get_llm_for_model

        llm = get_llm_for_model(model)
        system = (
            "你是一位专业的中文小说编辑。在小说指定位置插入自然衔接的段落，"
            "保持文风一致、人称一致、情节连续，只输出要插入的新段落文本本身（不含任何前后缀）。"
        )
        user_prompt = (
            f"##插入位置前的上下文（前 {len(before_ctx)} 字）\n{before_ctx}\n"
            f"[在此处插入新内容]\n"
            f"##插入位置后的上下文（后 {len(after_ctx)} 字）\n{after_ctx}\n\n"
            f"##插入要求\n{instruction}\n\n"
            "##输出要求\n只输出要插入的新段落文本，不要加任何说明、注释、引号或前后缀。"
        )
        try:
            inserted = await llm.complete(
                prompt=user_prompt, system=system, max_tokens=2000, temperature=0.7
            )
        except Exception as e:
            logger.exception("V0.38 insert_at_position: LLM call failed")
            raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e
        inserted_clean = inserted.strip()
        logger.info(
            "V0.38 insert: 第 %s 章 pos=%s → %s字",
            chapter,
            position,
            len(inserted_clean),
        )
        return {
            "chapter": chapter,
            "position": position,
            "inserted": inserted_clean,
            "before_ctx_len": len(before_ctx),
            "after_ctx_len": len(after_ctx),
            "model": model or "default",
        }

    @app.get("/api/outlines")
    async def list_outlines(project_root: str = ".") -> list[dict]:
        """列出项目下已有细纲。"""
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            return []
        outline_dir = project.chapter_outline(1).parent
        if not outline_dir.exists():
            return []
        import re

        result: list[dict] = []
        for f in sorted(outline_dir.glob("细纲_第*章.md")):
            m = re.search(r"第(\d+)章", f.name)
            if not m:
                continue
            ch = int(m.group(1))
            result.append({"chapter": ch, "filename": f.name})
        return result

    @app.get("/api/write/stream")
    async def write_chapter_stream(
        request: Request,  # V0.29.3：lifespan 单例 provider（FastAPI 自动注入）
        chapter: int = Query(..., description="章节号"),
        project_root: str = Query(".", description="项目根目录"),
        skill: str = Query("story-long-write", description="使用的 skill"),
        min_chars: int = Query(2000, description="最低字数"),
        skip_pre_write: bool = Query(False, description="跳过 pre-write check"),
    ) -> StreamingResponse:
        """SSE 流式写作端点。

        V0.29.3：request 参数注入（用于获取 app.state.provider 单例）
        事件序列：
          - started: pipeline 启动
          - pre_write_check: pre-write check 结果（如有）
          - chunk: LLM 输出片段（多次，实时）
          - progress: 阶段切换
          - post_write_check: post-write check 结果
          - done: 完成（含 output_path, content_chars）
          - error: 出错
        """

        # V0.29.3：闭包捕获 request（FastAPI 不会自动注入到 inner async generator）
        async def event_stream() -> AsyncIterator[str]:
            # V0.29.3：用 lifespan 管理的单例 provider（cache 跨请求连续）
            llm: LLMProvider = request.app.state.provider
            root = Path(project_root).resolve()
            project = ProjectStructure(root=root)
            if not project.exists():
                yield sse_event(
                    "error",
                    {"message": f"项目未初始化: {root}. 请先跑 novel2all setup."},
                )
                return

            # started
            yield sse_event(
                "started",
                {
                    "chapter": chapter,
                    "skill": skill,
                    "min_chars": min_chars,
                    "skip_pre_write": skip_pre_write,
                    "project_root": str(root),
                },
            )

            # 构造 pipeline（用 lifespan 管理的单例 llm）
            try:
                manager = MemoryManager(project_root=root, llm=llm)
                skills_dir = Path(__file__).parent.parent / "skills"
                skill_registry = SkillRegistry(skills_dir)
                skill_registry.discover()
                pipeline = WritingPipeline(
                    manager=manager,
                    skill_registry=skill_registry,
                    llm=llm,
                    project=project,
                )
            except Exception as e:
                yield sse_event("error", {"message": f"Pipeline 初始化失败: {e}"})
                return

            # 用 asyncio.Queue 桥接 sync stream_callback → async generator
            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            collected: list[str] = []

            def on_chunk(text: str) -> None:
                collected.append(text)
                # 同步函数中塞入异步队列
                chunk_queue.put_nowait(text)

            async def run_pipeline() -> None:
                """在 task 中跑 pipeline，同时把 chunk 事件 yield 给前端。"""
                try:
                    await pipeline.write_chapter(
                        chapter=chapter,
                        outline_path=project.chapter_outline(chapter),
                        skill_name=skill,
                        stream_callback=on_chunk,
                        min_chars=min_chars,
                        skip_pre_write_check=skip_pre_write,
                    )
                finally:
                    # 即使 pipeline 异常也要 put sentinel，让 event_stream 能退出
                    await chunk_queue.put(None)

            try:
                # 后台跑 pipeline
                pipeline_task = asyncio.create_task(run_pipeline())

                # 实时消费 chunk 队列
                while True:
                    chunk = await chunk_queue.get()
                    if chunk is None:
                        break  # pipeline 完成
                    yield sse_event("chunk", {"text": chunk})

                # 等待 pipeline 完成并取结果
                result = await pipeline_task

                # pre_write_check 事件（如有）
                if result.pre_write_issues:
                    yield sse_event(
                        "pre_write_check",
                        {"issues": [issue.model_dump() for issue in result.pre_write_issues]},
                    )

                # 阶段事件
                yield sse_event(
                    "progress",
                    {"phase": "save", "message": f"已写文件: {result.output_path}"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "extract", "message": "提取角色/伏笔/时间线"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "merge", "message": "合并到 tracking state"},
                )

                # post_write_check
                if result.post_write_issues:
                    yield sse_event(
                        "post_write_check",
                        {"issues": [issue.model_dump() for issue in result.post_write_issues]},
                    )

                # done
                yield sse_event(
                    "done",
                    {
                        "output_path": str(result.output_path),
                        "content_chars": result.content_chars,
                        "post_issue_count": len(result.post_write_issues),
                        "pre_issue_count": len(result.pre_write_issues),
                    },
                )

            except OutlineNotFoundError as e:
                yield sse_event("error", {"message": str(e), "code": "outline_not_found"})
            except BlockingIssuesError as e:
                yield sse_event(
                    "error",
                    {
                        "message": f"pre-write check 发现 {len(e.issues)} 个 critical 问题",
                        "code": "blocking_issues",
                        "issues": [issue.model_dump() for issue in e.issues],
                    },
                )
            except Exception as e:
                # 检查是否是 pipeline_task 异常
                if pipeline_task.done() and pipeline_task.exception():
                    exc = pipeline_task.exception()
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(exc).__name__}: {exc}"},
                    )
                else:
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(e).__name__}: {e}"},
                    )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # 防止 nginx 等缓冲
            },
        )

    return app
