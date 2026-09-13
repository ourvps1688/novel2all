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
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

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

    # V0.29.3：测试 fallback（TestClient 默认不触发 lifespan 上下文）
    # 生产路径走 lifespan；测试路径直接初始化 provider
    # 这样 `app = create_app(); client = TestClient(app)` 也能工作
    if not hasattr(app.state, "provider"):
        load_dotenv(".env", override=False)
        app.state.provider = LLMProvider(LLMConfig())

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

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

    @app.get("/api/cache/stats")
    async def cache_stats(request: Request) -> dict[str, Any]:
        """V0.29.3：返回 lifespan provider 的 cache 统计。

        V0.30 WebUI 暴露此端点做实时命中率面板。
        """
        provider: LLMProvider = request.app.state.provider
        return provider.cache_stats()

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


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>novel2all Web UI</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            line-height: 1.6;
            padding: 2rem;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 2rem; margin-bottom: 1.5rem; color: #67e8f9; }
        h2 { font-size: 1.25rem; margin: 1.5rem 0 0.75rem; color: #93c5fd; }
        h3 { font-size: 1rem; margin: 1rem 0 0.5rem; color: #cbd5e1; font-weight: 600; }
        .card {
            background: #1e293b;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            border: 1px solid #334155;
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; }
        .badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            background: #334155;
            border-radius: 4px;
            font-size: 0.875rem;
            margin-right: 0.5rem;
        }
        .badge.active { background: #10b981; color: #0f172a; }
        .badge.advanced { background: #f59e0b; color: #0f172a; }
        .badge.revealed { background: #8b5cf6; color: #f1f5f9; }
        .badge.abandoned { background: #64748b; color: #f1f5f9; }
        .badge.dead { background: #ef4444; color: #f1f5f9; }
        .skill-item, .role-item {
            background: #0f172a;
            padding: 1rem;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            border-left: 3px solid #06b6d4;
        }
        .item-name { color: #67e8f9; font-weight: bold; }
        .item-desc { color: #94a3b8; font-size: 0.875rem; margin-top: 0.25rem; }
        .loading { color: #fbbf24; }
        .error { color: #f87171; }
        .success { color: #34d399; }
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .stat {
            background: #0f172a;
            padding: 1rem;
            border-radius: 6px;
        }
        .stat-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; }
        .stat-value { font-size: 1.5rem; color: #67e8f9; margin-top: 0.25rem; }

        /* === Step E: 角色 / 伏笔 / 章节详情 === */
        .character-card {
            background: #0f172a;
            padding: 1rem;
            border-radius: 6px;
            border-left: 3px solid #06b6d4;
        }
        .character-card.dead { border-left-color: #ef4444; opacity: 0.7; }
        .character-name { color: #67e8f9; font-weight: bold; font-size: 1.1rem; }
        .character-meta { color: #94a3b8; font-size: 0.85rem; margin-top: 0.5rem; }
        .character-meta strong { color: #cbd5e1; }
        .character-desc { color: #cbd5e1; font-size: 0.9rem; margin-top: 0.5rem; }

        .foreshadowing-item {
            background: #0f172a;
            padding: 1rem;
            border-radius: 6px;
            border-left: 3px solid #06b6d4;
            margin-bottom: 0.5rem;
        }
        .foreshadowing-item.advanced { border-left-color: #f59e0b; }
        .foreshadowing-item.revealed { border-left-color: #8b5cf6; }
        .foreshadowing-item.abandoned { border-left-color: #64748b; opacity: 0.6; }
        .fs-title { color: #cbd5e1; font-weight: 600; }
        .fs-desc { color: #94a3b8; font-size: 0.875rem; margin-top: 0.5rem; }
        .fs-meta { color: #64748b; font-size: 0.75rem; margin-top: 0.5rem; }
        .fs-filter { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
        .fs-filter button {
            background: #334155;
            color: #cbd5e1;
            font-size: 0.875rem;
            padding: 0.4rem 0.8rem;
        }
        .fs-filter button.active { background: #06b6d4; color: #0f172a; }

        .chapter-list-item {
            background: #0f172a;
            padding: 0.75rem;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            border-left: 3px solid #06b6d4;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            transition: background 0.15s;
        }
        .chapter-list-item:hover { background: #1e293b; }
        .chapter-list-item .ch-meta { color: #94a3b8; font-size: 0.875rem; }
        .chapter-list-item .ch-arrow { color: #64748b; }

        /* 章节详情弹窗 */
        .modal-overlay {
            position: fixed; inset: 0;
            background: rgba(0, 0, 0, 0.75);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal-overlay.show { display: flex; }
        .modal {
            background: #1e293b;
            border-radius: 8px;
            border: 1px solid #334155;
            max-width: 800px;
            width: 90%;
            max-height: 80vh;
            display: flex;
            flex-direction: column;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid #334155;
        }
        .modal-title { color: #67e8f9; font-size: 1.25rem; font-weight: bold; }
        .modal-close {
            background: transparent; color: #94a3b8;
            font-size: 1.5rem; padding: 0 0.5rem;
        }
        .modal-close:hover { color: #e2e8f0; background: transparent; }
        .modal-body {
            padding: 1.5rem;
            overflow-y: auto;
            white-space: pre-wrap;
            font-family: ui-monospace, "Cascadia Code", "Consolas", monospace;
            font-size: 0.95rem;
            line-height: 1.8;
            flex: 1;
        }
        .modal-footer {
            padding: 1rem 1.5rem;
            border-top: 1px solid #334155;
            color: #94a3b8;
            font-size: 0.875rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-footer button { font-size: 0.875rem; padding: 0.4rem 0.8rem; }

        .empty-state {
            color: #64748b;
            font-style: italic;
            text-align: center;
            padding: 1.5rem 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📖 novel2all Web UI <span style="font-size:0.875rem; color:#64748b;">v0.21</span></h1>

        <div class="card">
            <h2>项目状态</h2>
            <div id="status" class="loading">加载中...</div>
        </div>

        <div class="card">
            <h2>👥 角色 (<span id="character-count">0</span>)</h2>
            <div id="characters" class="grid"><div class="empty-state">加载中...</div></div>
        </div>

        <div class="card">
            <h2>🔮 伏笔 (<span id="foreshadowing-count">0</span>)</h2>
            <div class="fs-filter" id="fs-filter">
                <button data-filter="all" class="active">全部</button>
                <button data-filter="active">active</button>
                <button data-filter="advanced">advanced</button>
                <button data-filter="revealed">revealed</button>
                <button data-filter="abandoned">abandoned</button>
            </div>
            <div id="foreshadowing"><div class="empty-state">加载中...</div></div>
        </div>

        <div class="card">
            <h2>📝 写章节（实时 SSE）</h2>
            <div style="display:flex; gap:0.75rem; align-items:end; flex-wrap:wrap; margin-bottom:1rem;">
                <div style="display:flex; flex-direction:column; gap:0.25rem;">
                    <label style="font-size:0.75rem; color:#94a3b8; text-transform:uppercase;">章节号</label>
                    <input id="chapter-input" type="number" min="1" value="1" style="width:100px; background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.5rem 0.75rem; border-radius:4px; font-family:inherit; font-size:1rem;" />
                </div>
                <div style="display:flex; flex-direction:column; gap:0.25rem;">
                    <label style="font-size:0.75rem; color:#94a3b8; text-transform:uppercase;">Skill</label>
                    <select id="skill-select" style="width:220px; background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.5rem 0.75rem; border-radius:4px; font-family:inherit; font-size:1rem;">
                        <option value="story-long-write">story-long-write（默认）</option>
                    </select>
                </div>
                <div style="display:flex; flex-direction:column; gap:0.25rem;">
                    <label style="font-size:0.75rem; color:#94a3b8; text-transform:uppercase;">最低字数</label>
                    <input id="min-chars-input" type="number" min="0" value="2000" style="width:100px; background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.5rem 0.75rem; border-radius:4px; font-family:inherit; font-size:1rem;" />
                </div>
                <div style="display:flex; flex-direction:column; gap:0.25rem;">
                    <label style="font-size:0.75rem; color:#94a3b8; text-transform:uppercase;">项目根目录</label>
                    <input id="project-root-input" type="text" value="." style="width:200px; background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:0.5rem 0.75rem; border-radius:4px; font-family:inherit; font-size:1rem;" />
                </div>
                <div style="display:flex; flex-direction:column; gap:0.25rem;">
                    <label style="font-size:0.75rem; color:#94a3b8; text-transform:uppercase;">跳过 pre-write</label>
                    <input id="skip-pre-write-checkbox" type="checkbox" />
                </div>
                <button id="start-btn" onclick="startWriting()" style="background:#06b6d4; color:#0f172a; border:none; padding:0.6rem 1.2rem; border-radius:4px; font-weight:bold; cursor:pointer; font-size:1rem;">开始写</button>
                <button id="stop-btn" onclick="stopWriting()" disabled style="background:#ef4444; color:#f1f5f9; border:none; padding:0.6rem 1.2rem; border-radius:4px; font-weight:bold; cursor:not-allowed; font-size:1rem;">停止</button>
            </div>
            <div id="progress-log" style="background:#0f172a; border:1px solid #334155; border-radius:6px; padding:1rem; margin:1rem 0; font-family:ui-monospace,monospace; font-size:0.875rem; max-height:200px; overflow-y:auto;"></div>
            <div id="chapter-content" style="background:#0f172a; border:1px solid #334155; border-radius:6px; padding:1.5rem; margin-top:1rem; white-space:pre-wrap; font-family:ui-monospace,monospace; font-size:0.95rem; line-height:1.8; min-height:100px; max-height:400px; overflow-y:auto;"></div>
            <div id="writer-result" style="margin-top:1rem;"></div>
        </div>

        <div class="card">
            <h2>📚 已写章节 (<span id="chapter-count">0</span>) — 点击查看详情</h2>
            <div id="chapter-list"><div class="empty-state">加载中...</div></div>
        </div>

        <div class="card">
            <h2>Skills (<span id="skill-count">0</span>)</h2>
            <div id="skills"></div>
        </div>

        <div class="card">
            <h2>Roles (<span id="role-count">0</span>)</h2>
            <div id="roles"></div>
        </div>

        <div class="card">
            <h2>使用说明</h2>
            <pre style="background:#0f172a; padding:1rem; border-radius:6px;">
novel2all setup --name "我的小说" --genre "玄幻" --style "古风古韵"
novel2all status
novel2all write chapter 1
novel2all web  # 启动当前界面（默认 :8000）
            </pre>
        </div>
    </div>

    <!-- 章节详情弹窗 -->
    <div class="modal-overlay" id="chapter-modal">
        <div class="modal">
            <div class="modal-header">
                <div class="modal-title" id="modal-title">章节详情</div>
                <button class="modal-close" onclick="closeModal()">×</button>
            </div>
            <div class="modal-body" id="modal-body">加载中...</div>
            <div class="modal-footer">
                <span id="modal-meta"></span>
                <button onclick="closeModal()">关闭</button>
            </div>
        </div>
    </div>

    <script>
        let currentEventSource = null;
        let collectedText = '';
        let currentTracking = null;
        let currentFsFilter = 'all';

        function logLine(text, cls = 'info') {
            const log = document.getElementById('progress-log');
            const line = document.createElement('div');
            line.style.padding = '0.125rem 0';
            line.className = cls;
            const ts = new Date().toLocaleTimeString();
            line.textContent = `[${ts}] ${text}`;
            log.appendChild(line);
            log.scrollTop = log.scrollHeight;
        }

        function stopWriting() {
            if (currentEventSource) {
                currentEventSource.close();
                currentEventSource = null;
                logLine('已断开 EventSource 连接');
            }
            document.getElementById('start-btn').disabled = false;
            document.getElementById('stop-btn').disabled = true;
        }

        function startWriting() {
            collectedText = '';
            document.getElementById('chapter-content').textContent = '';
            document.getElementById('writer-result').innerHTML = '';
            document.getElementById('progress-log').innerHTML = '';

            const chapter = document.getElementById('chapter-input').value;
            const skill = document.getElementById('skill-select').value;
            const minChars = document.getElementById('min-chars-input').value;
            const projectRoot = document.getElementById('project-root-input').value;
            const skipPreWrite = document.getElementById('skip-pre-write-checkbox').checked;

            const params = new URLSearchParams({
                chapter, skill, min_chars: minChars,
                project_root: projectRoot,
                skip_pre_write: skipPreWrite,
            });
            const url = '/api/write/stream?' + params.toString();
            logLine('连接到 SSE: ' + url);

            if (currentEventSource) currentEventSource.close();
            currentEventSource = new EventSource(url);
            document.getElementById('start-btn').disabled = true;
            document.getElementById('stop-btn').disabled = false;

            currentEventSource.addEventListener('started', (e) => {
                const data = JSON.parse(e.data);
                logLine(`Pipeline 启动: chapter=${data.chapter} skill=${data.skill}`, 'success');
            });
            currentEventSource.addEventListener('pre_write_check', (e) => {
                const data = JSON.parse(e.data);
                logLine(`Pre-write check: ${data.issues.length} 个问题`, data.issues.length > 0 ? 'error' : 'success');
            });
            currentEventSource.addEventListener('chunk', (e) => {
                const data = JSON.parse(e.data);
                collectedText += data.text;
                document.getElementById('chapter-content').textContent = collectedText;
                const el = document.getElementById('chapter-content');
                el.scrollTop = el.scrollHeight;
            });
            currentEventSource.addEventListener('progress', (e) => {
                const data = JSON.parse(e.data);
                logLine(`[${data.phase}] ${data.message}`);
            });
            currentEventSource.addEventListener('post_write_check', (e) => {
                const data = JSON.parse(e.data);
                logLine(`Post-write check: ${data.issues.length} 个问题`, data.issues.length > 0 ? 'error' : 'success');
                if (data.issues.length > 0) {
                    const result = document.getElementById('writer-result');
                    result.innerHTML = '<strong style="color:#fbbf24;">检查问题:</strong><ul>' +
                        data.issues.map(i => `<li><span class="badge">${i.severity}</span> ${i.description}</li>`).join('') +
                        '</ul>';
                }
            });
            currentEventSource.addEventListener('done', (e) => {
                const data = JSON.parse(e.data);
                logLine(`完成: ${data.content_chars} 字 → ${data.output_path}`, 'success');
                const result = document.getElementById('writer-result');
                if (!result.innerHTML) {
                    result.innerHTML = `<span class="success">✓ 写入 ${data.output_path}</span><br>` +
                        `<span style="font-size:0.875rem; color:#94a3b8;">字数: ${data.content_chars}</span>`;
                }
                stopWriting();
                loadAll();
            });
            currentEventSource.addEventListener('error', (e) => {
                let msg = '未知错误';
                if (e.data) {
                    try {
                        const data = JSON.parse(e.data);
                        msg = data.message || msg;
                        if (data.issues) {
                            msg += '\n问题:\n' + data.issues.map(i => `  - [${i.severity}] ${i.description}`).join('\n');
                        }
                    } catch (_) { msg = e.data; }
                }
                logLine(`错误: ${msg}`, 'error');
                document.getElementById('writer-result').innerHTML =
                    `<span class="error">✗ ${msg.replace(/\n/g, '<br>')}</span>`;
                stopWriting();
            });
        }

        // === 章节详情弹窗 ===
        async function openChapterModal(chapter) {
            const projectRoot = document.getElementById('project-root-input').value;
            const modal = document.getElementById('chapter-modal');
            const body = document.getElementById('modal-body');
            const title = document.getElementById('modal-title');
            const meta = document.getElementById('modal-meta');

            title.textContent = `第 ${chapter} 章`;
            body.textContent = '加载中...';
            meta.textContent = '';
            modal.classList.add('show');

            try {
                const resp = await fetch(`/api/chapter/${chapter}/content?project_root=${encodeURIComponent(projectRoot)}`);
                if (!resp.ok) {
                    body.textContent = `加载失败: HTTP ${resp.status}`;
                    return;
                }
                const data = await resp.json();
                title.textContent = `第 ${data.chapter} 章 — ${data.first_line}`;
                body.textContent = data.content;
                meta.textContent = `${data.char_count} 字 · ${data.filename}`;
            } catch (e) {
                body.textContent = `加载失败: ${e.message}`;
            }
        }

        function closeModal() {
            document.getElementById('chapter-modal').classList.remove('show');
        }

        // === 伏笔过滤 ===
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('#fs-filter button').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('#fs-filter button').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentFsFilter = btn.dataset.filter;
                    renderForeshadowing();
                });
            });
        });

        function renderCharacters() {
            const container = document.getElementById('characters');
            if (!currentTracking || !currentTracking.characters || Object.keys(currentTracking.characters).length === 0) {
                container.innerHTML = '<div class="empty-state">还没有角色</div>';
                return;
            }
            const chars = Object.values(currentTracking.characters)
                .sort((a, b) => (b.last_updated_chapter || 0) - (a.last_updated_chapter || 0));
            container.innerHTML = chars.map(c => {
                const isDead = c.alive === false;
                const meta = [];
                if (c.location) meta.push(`📍 ${c.location}`);
                if (c.emotional_state) meta.push(`💭 ${c.emotional_state}`);
                if (c.last_updated_chapter) meta.push(`📅 ch.${c.last_updated_chapter}`);
                return `
                    <div class="character-card ${isDead ? 'dead' : ''}">
                        <div class="character-name">
                            ${c.name}
                            ${isDead ? '<span class="badge dead" style="margin-left:0.5rem;">dead</span>' : ''}
                        </div>
                        <div class="character-meta">${meta.map(m => `<strong>${m}</strong>`).join(' · ')}</div>
                        ${c.description ? `<div class="character-desc">${c.description}</div>` : ''}
                    </div>
                `;
            }).join('');
        }

        function renderForeshadowing() {
            const container = document.getElementById('foreshadowing');
            if (!currentTracking || !currentTracking.foreshadowing || Object.keys(currentTracking.foreshadowing).length === 0) {
                container.innerHTML = '<div class="empty-state">还没有伏笔</div>';
                return;
            }
            const items = Object.values(currentTracking.foreshadowing);
            const filtered = currentFsFilter === 'all'
                ? items
                : items.filter(f => f.status === currentFsFilter);
            if (filtered.length === 0) {
                container.innerHTML = '<div class="empty-state">该状态无伏笔</div>';
                return;
            }
            container.innerHTML = filtered.map(f => {
                const meta = [];
                if (f.planted_chapter) meta.push(`埋设 ch.${f.planted_chapter}`);
                if (f.revealed_chapter) meta.push(`揭示 ch.${f.revealed_chapter}`);
                return `
                    <div class="foreshadowing-item ${f.status}">
                        <div class="fs-title">
                            <span class="badge ${f.status}">${f.status}</span>
                            ${f.id || ''} ${f.title ? '— ' + f.title : ''}
                        </div>
                        ${f.description ? `<div class="fs-desc">${f.description}</div>` : ''}
                        ${meta.length > 0 ? `<div class="fs-meta">${meta.join(' · ')}</div>` : ''}
                    </div>
                `;
            }).join('');
        }

        async function loadAll() {
            const projectRoot = document.getElementById('project-root-input').value;
            await loadStatus(projectRoot);
            await loadTracking(projectRoot);
            await loadChapters(projectRoot);
        }

        async function loadStatus(projectRoot) {
            try {
                const status = await fetch(`/api/status?project_root=${encodeURIComponent(projectRoot)}`).then(r => r.json());
                const statusDiv = document.getElementById('status');
                if (!status.initialized) {
                    statusDiv.innerHTML = '<span class="error">项目未初始化</span><br>运行 <code>novel2all setup</code> 初始化';
                    return;
                }
                statusDiv.innerHTML = `
                    <div class="stat-grid">
                        <div class="stat"><div class="stat-label">项目名</div><div class="stat-value">${status.project_name}</div></div>
                        <div class="stat"><div class="stat-label">题材</div><div class="stat-value">${status.genre || '-'}</div></div>
                        <div class="stat"><div class="stat-label">文风</div><div class="stat-value">${status.style_anchor || '-'}</div></div>
                        <div class="stat"><div class="stat-label">当前章节</div><div class="stat-value">${status.last_updated_chapter}</div></div>
                        <div class="stat"><div class="stat-label">角色数</div><div class="stat-value">${status.character_count}</div></div>
                        <div class="stat"><div class="stat-label">活跃伏笔</div><div class="stat-value">${status.active_foreshadowing_count}</div></div>
                        <div class="stat"><div class="stat-label">时间线</div><div class="stat-value">${status.timeline_count}</div></div>
                        <div class="stat"><div class="stat-label">已有摘要</div><div class="stat-value">${status.summary_count}</div></div>
                    </div>
                `;
            } catch (e) {
                document.getElementById('status').innerHTML = `<span class="error">加载失败: ${e.message}</span>`;
            }
        }

        async function loadTracking(projectRoot) {
            try {
                const tracking = await fetch(`/api/tracking?project_root=${encodeURIComponent(projectRoot)}`).then(r => r.json());
                currentTracking = tracking;
                // 角色
                const charCount = tracking.characters ? Object.keys(tracking.characters).length : 0;
                document.getElementById('character-count').textContent = charCount;
                renderCharacters();
                // 伏笔
                const fsCount = tracking.foreshadowing ? Object.keys(tracking.foreshadowing).length : 0;
                document.getElementById('foreshadowing-count').textContent = fsCount;
                renderForeshadowing();
            } catch (e) {
                document.getElementById('characters').innerHTML = `<div class="empty-state">未初始化项目</div>`;
                document.getElementById('foreshadowing').innerHTML = `<div class="empty-state">未初始化项目</div>`;
            }
        }

        async function loadChapters(projectRoot) {
            try {
                const chapters = await fetch(`/api/chapters?project_root=${encodeURIComponent(projectRoot)}`).then(r => r.json());
                document.getElementById('chapter-count').textContent = chapters.length;
                document.getElementById('chapter-list').innerHTML = chapters.length === 0
                    ? '<div class="empty-state">还没有章节</div>'
                    : chapters.map(c => `
                        <div class="chapter-list-item" onclick="openChapterModal(${c.chapter})">
                            <div>
                                <strong>第 ${c.chapter} 章</strong>
                                <span class="ch-meta"> · ${c.char_count} 字</span>
                                <div class="ch-meta">${c.first_line}</div>
                            </div>
                            <span class="ch-arrow">查看详情 →</span>
                        </div>
                    `).join('');
            } catch (e) {
                document.getElementById('chapter-list').innerHTML = `<div class="empty-state">加载失败: ${e.message}</div>`;
            }
        }

        // 加载 skills / roles
        async function loadSkillsAndRoles() {
            try {
                const skills = await fetch('/api/skills').then(r => r.json());
                document.getElementById('skill-count').textContent = skills.length;
                document.getElementById('skills').innerHTML = skills.map(s => `
                    <div class="skill-item">
                        <div class="item-name">${s.name}</div>
                        <div class="item-desc">${s.description}</div>
                        <div style="margin-top:0.5rem;">
                            ${s.user_invocable ? '<span class="badge">user-invocable</span>' : ''}
                            ${s.model_invocable ? '<span class="badge">model-invocable</span>' : ''}
                        </div>
                    </div>
                `).join('');
                const roles = await fetch('/api/roles').then(r => r.json());
                document.getElementById('role-count').textContent = roles.length;
                document.getElementById('roles').innerHTML = roles.map(r => `
                    <div class="role-item">
                        <div class="item-name">${r.name}</div>
                        <div class="item-desc">${r.description}</div>
                        ${r.preferred_model ? `<div style="margin-top:0.5rem;"><span class="badge">model: ${r.preferred_model}</span></div>` : ''}
                    </div>
                `).join('');
            } catch (e) {
                console.error('skills/roles load failed', e);
            }
        }

        loadAll();
        loadSkillsAndRoles();

        // ESC 关闭弹窗
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });
        // 点击遮罩关闭
        document.getElementById('chapter-modal').addEventListener('click', (e) => {
            if (e.target.id === 'chapter-modal') closeModal();
        });
    </script>
</body>
</html>
"""
