"""novel2all Web UI（FastAPI + SSE SPA）。

v0.20 基础：项目状态 + skill 列表 + role 列表 + tracking state
v0.21 Step 3：SSE 流式写作端点 + 前端实时显示
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.memory import MemoryManager, Tracker
from novel2all.core.pipeline import (
    BlockingIssuesError,
    OutlineNotFoundError,
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

    @app.get("/api/cache/stats")
    async def cache_stats(request: Request) -> dict[str, Any]:
        """V0.29.3：返回 lifespan provider 的 cache 统计。

        V0.30 WebUI 暴露此端点做实时命中率面板。
        """
        provider: LLMProvider = request.app.state.provider
        return provider.cache_stats()

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
    ) -> StreamingResponse:
        """V0.30.1：带 model 参数的流式写作端点（V0.29.3 单例 + V0.30 WebUI 集成）。

        复用了原 /api/write/stream 的逻辑，但接受 Form 参数（HTMX 友好）。
        """
        # V0.30.1：用请求中的 model（不污染单例）
        from novel2all.cli.main import get_llm_for_model

        async def event_stream() -> AsyncIterator[str]:
            llm: LLMProvider = get_llm_for_model(model)
            root = Path(project_root).resolve()
            project = ProjectStructure(root=root)
            if not project.exists():
                yield sse_event(
                    "error",
                    {"message": f"项目未初始化: {root}. 请先跑 novel2all setup."},
                )
                return

            yield sse_event(
                "started",
                {
                    "chapter": chapter,
                    "skill": skill,
                    "model": model or "default",  # V0.30.1: 显示选用的 model
                    "min_chars": min_chars,
                    "skip_pre_write": skip_pre_write,
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
                    )
                finally:
                    await chunk_queue.put(None)

            try:
                pipeline_task = asyncio.create_task(run_pipeline())
                while True:
                    chunk = await chunk_queue.get()
                    if chunk is None:
                        break
                    yield sse_event("chunk", {"text": chunk})

                result = await pipeline_task

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
                "X-Accel-Buffering": "no",
            },
        )

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
