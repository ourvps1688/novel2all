"""V0.30.0：WebUI 拆前端 SPA + HTMX/Alpine.js + Jinja2Templates 测试。

V0.30.0 核心改动：
- 拆 inline HTML（605 行 INDEX_HTML）到 web/templates/*.html
- 引入 HTMX 2.x + Alpine.js 3.x（本地化到 web/static/）
- 用 Jinja2Templates 渲染 base.html / index.html + 3 partials
- 新增 /page/* 端点（HTMX 用，返回 HTML 片段）
- /api/* 端点保留 JSON（API 兼容 + 测试用）

测试覆盖：
- templates 渲染（base + index + 3 partials）
- /page/* 端点返回 HTML（HTMX swap 兼容）
- /api/* 端点仍返回 JSON
- 静态文件 mount
- 页面整体可访问（GET / 返回 200 + 包含 HTMX/Alpine 引用）
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel2all.web.app import create_app


class TestWebUITemplatesV0300:
    """V0.30.0：Jinja2 模板 + 静态文件基础设施。"""

    def test_create_app_mounts_static_files(self) -> None:
        """create_app() 注册 /static 路由（HTMX + Alpine.js）。"""
        app = create_app()
        # 查找 /static 路由
        static_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/static")]
        assert len(static_routes) > 0, "应注册 /static 路由"

    def test_index_returns_html_with_htmx_alpine(self) -> None:
        """GET / 返回 HTML，含 HTMX + Alpine.js 引用。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            html = response.text
            # 验证 HTMX 引用
            assert "htmx" in html.lower(), "页面应引用 HTMX"
            # 验证 Alpine.js 引用
            assert "alpine" in html.lower(), "页面应引用 Alpine.js"
            # 验证基础结构
            assert "<!DOCTYPE html>" in html
            assert "<title>" in html
            assert "novel2all" in html

    def test_index_uses_jinja2_template(self) -> None:
        """GET / 渲染 base.html + index.html（Jinja2 模板）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/")
            html = response.text
            # base.html 特征
            assert "header" in html
            assert "footer" in html or "main" in html  # base 有 main
            # index.html 特征：HTMX hx-get /page/status
            assert "hx-get" in html
            assert "/page/" in html

    def test_static_files_serve_htmx_and_alpine(self) -> None:
        """GET /static/htmx.min.js 和 /static/alpine.min.js 返回 JS。"""
        app = create_app()
        with TestClient(app) as client:
            htmx_response = client.get("/static/htmx.min.js")
            assert htmx_response.status_code == 200
            assert "javascript" in htmx_response.headers["content-type"]
            assert len(htmx_response.content) > 1000  # 至少 1KB

            alpine_response = client.get("/static/alpine.min.js")
            assert alpine_response.status_code == 200
            assert "javascript" in alpine_response.headers["content-type"]
            assert len(alpine_response.content) > 1000


class TestPageEndpointsV0300:
    """V0.30.0：HTMX 局部更新端点（/page/*）返回 HTML 片段。"""

    def test_page_status_returns_html_partial(self) -> None:
        """GET /page/status 返回 HTML partial（HTMX swap 用）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/status")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            html = response.text
            # status_partial.html 特征
            assert "项目未初始化" in html or "初始化" in html
            # 应该是 fragment（不是完整 HTML 页面）
            assert "<!DOCTYPE html>" not in html, "partial 不应包含 DOCTYPE"

    def test_page_skills_returns_html_partial(self) -> None:
        """GET /page/skills 返回 skills_partial.html。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/skills")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            html = response.text
            assert "<!DOCTYPE html>" not in html
            # skills 列表 UL 结构
            assert "<ul" in html or "未发现 skill" in html

    def test_page_roles_returns_html_partial(self) -> None:
        """GET /page/roles 返回 roles_partial.html。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/roles")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            html = response.text
            assert "<!DOCTYPE html>" not in html
            assert "<ul" in html or "未发现 role" in html

    def test_page_status_with_initialized_project(self, tmp_path) -> None:
        """GET /page/status?project_root=... 加载实际项目数据。"""
        import json

        # 创建临时项目结构（TrackingState 字段是 dict 不是 list）
        tracking_data = {
            "project_name": "TestNovel",
            "genre": "仙侠",
            "style_anchor": "文笔细腻",
            "total_chapters_target": 100,
            "total_word_count_target": 2000000,
            "last_updated_chapter": 5,
            "characters": {},
            "foreshadowing": {},
            "timeline": [],
            "recent_chapter_summaries": {},
        }
        (tmp_path / "_tracking-state.json").write_text(json.dumps(tracking_data), encoding="utf-8")
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/status", params={"project_root": str(tmp_path)})
            assert response.status_code == 200
            html = response.text
            assert "TestNovel" in html
            assert "仙侠" in html
            assert "已初始化" in html


class TestApiEndpointsStillJsonV0300:
    """V0.30.0：/api/* 端点保留 JSON（API 兼容 + 测试用）。"""

    def test_api_status_still_returns_json(self) -> None:
        """/api/status 返回 JSON dict（V0.30.0 之前 API）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/status")
            assert response.status_code == 200
            data = response.json()
            assert "initialized" in data
            assert "project_root" in data

    def test_api_skills_still_returns_json_list(self) -> None:
        """/api/skills 返回 JSON list。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/skills")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # 每个 skill 应有 name + description
            if data:
                assert "name" in data[0]
                assert "description" in data[0]

    def test_api_roles_still_returns_json_list(self) -> None:
        """/api/roles 返回 JSON list。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/roles")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
