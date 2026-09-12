"""novel2all Web UI（FastAPI + Jinja2 SPA）。

v0.20 提供最简 SPA：项目状态 + skill 列表 + role 列表 + 写作入口。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from novel2all.core.memory import Tracker
from novel2all.core.role import RoleRegistry
from novel2all.core.skill import SkillRegistry


def create_app() -> FastAPI:
    app = FastAPI(title="novel2all Web UI", version="0.20.0")

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

    @app.get("/api/tracking")
    async def get_tracking(project_root: str = ".") -> dict:
        root = Path(project_root).resolve()
        tracker = Tracker(root / "_tracking-state.json")
        if not tracker.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        state = tracker.read()
        return state.model_dump(mode="json")

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
    </style>
</head>
<body>
    <div class="container">
        <h1>📖 novel2all Web UI</h1>

        <div class="card">
            <h2>项目状态</h2>
            <div id="status" class="loading">加载中...</div>
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
            <p>novel2all v0.20 - 完整写作流程见 <code>docs/ROADMAP.md</code></p>
            <p style="margin-top:0.5rem;">CLI 用法：</p>
            <pre style="background:#0f172a; padding:1rem; border-radius:6px; margin-top:0.5rem;">
novel2all setup --name "我的小说" --genre "玄幻" --style "古风古韵"
novel2all status
novel2all skills list
novel2all write chapter 5
novel2all web  # 启动当前界面
            </pre>
        </div>
    </div>

    <script>
        async function load() {
            try {
                // Status
                const status = await fetch('/api/status').then(r => r.json());
                const statusDiv = document.getElementById('status');
                if (!status.initialized) {
                    statusDiv.innerHTML = '<span class="error">项目未初始化</span><br>运行 <code>novel2all setup</code> 初始化';
                } else {
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
                }

                // Skills
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

                // Roles
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
                document.getElementById('status').innerHTML = `<span class="error">加载失败: ${e.message}</span>`;
            }
        }

        load();
    </script>
</body>
</html>
"""
