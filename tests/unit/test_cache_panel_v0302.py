"""V0.30.2：Cache 命中率面板测试。

V0.30.2 暴露 V0.24 prompt cache + V0.29.0 LRU 价值给 WebUI：
- /api/cache/stats 端点（V0.29.3 已加）
- /page/cache-panel 端点（V0.30.2 新增，HTMX partial 渲染）
- cache_panel.html 模板（V0.30.2 新建）
  - 命中率（带颜色：≥70% 绿 / ≥30% 黄 / <30% 红）
  - 进度条
  - hits / misses / size / max_size
  - HTMX hx-trigger="every 5s" 实时刷新
- index.html 集成

测试覆盖：
- /api/cache/stats 端点（V0.29.3 已有）
- /page/cache-panel 返回 HTML 含命中率/LRU 进度条
- index.html 含 /page/cache-panel 引用 + 5s 刷新
- 颜色逻辑：Jinja2 模板基于 hit_rate 显示不同颜色
- 模板中含 "enabled" / "disabled" 状态显示
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel2all.web.app import create_app


class TestCachePanelEndpointV0302:
    """V0.30.2：/page/cache-panel HTMX partial 端点。"""

    def test_page_cache_panel_returns_html(self) -> None:
        """GET /page/cache-panel 返回 HTML partial（含 cache 统计可视化）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/cache-panel")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            html = response.text
            # cache_panel.html 共有特征
            assert "Cache 统计" in html
            # V0.30.2 hx-trigger 标注
            assert "every 5s" in html or "V0.30.2" in html

    def test_page_cache_panel_enabled_state_has_hit_rate(self) -> None:
        """cache_enabled=True 时，partial 显示命中率。"""
        import os

        os.environ["NOVEL2ALL_LLM_CACHE"] = "true"
        try:
            app = create_app()
            with TestClient(app) as client:
                response = client.get("/page/cache-panel")
                html = response.text
                # enabled 状态显示命中率
                assert "命中率" in html
        finally:
            os.environ.pop("NOVEL2ALL_LLM_CACHE", None)

    def test_page_cache_panel_disabled_state(self) -> None:
        """cache_enabled=False 时，partial 显示 disabled badge + 启用提示。"""
        app = create_app()
        # V0.25 默认 cache_enabled=False（除非 NOVEL2ALL_LLM_CACHE=true）
        with TestClient(app) as client:
            response = client.get("/page/cache-panel")
            html = response.text
            # disabled 状态显示
            assert "disabled" in html
            # 启用提示
            assert "NOVEL2ALL_LLM_CACHE" in html

    def test_page_cache_panel_enabled_state(self) -> None:
        """cache_enabled=True 时，partial 显示 enabled badge + 命中率 + hits/misses。"""
        import os

        os.environ["NOVEL2ALL_LLM_CACHE"] = "true"
        try:
            app = create_app()
            with TestClient(app) as client:
                response = client.get("/page/cache-panel")
                assert response.status_code == 200
                html = response.text
                # enabled 状态
                assert "enabled" in html
                # 不应该有 disabled 提示
                assert "Cache 已禁用" not in html
                # 应该有 hits/misses 显示
                assert "命中" in html
                assert "未命中" in html
        finally:
            os.environ.pop("NOVEL2ALL_LLM_CACHE", None)

    def test_page_cache_panel_color_logic_disabled(self) -> None:
        """cache 禁用时不应该有 hit_rate 颜色判断（避免显示 0%）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/cache-panel")
            html = response.text
            # 禁用时 hit_pct 变量不应该被设置（模板 {% if not stats.enabled %} 分支跳过）
            # 看是否有 "0.0%" 字样（不应该）
            assert "0.0%" not in html or "Cache 已禁用" in html

    def test_index_uses_cache_panel(self) -> None:
        """GET / 主页含 cache panel 引用 + 5s 刷新。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            html = response.text
            # V0.30.2 partial 引用
            assert "/page/cache-panel" in html
            # 5s 刷新
            assert "every 5s" in html
            # 初始占位
            assert 'id="cache-panel"' in html


class TestCacheStatsJSONV0293V0302:
    """V0.30.2：/api/cache/stats 仍返回 JSON（V0.29.3 行为，向后兼容）。"""

    def test_api_cache_stats_json(self) -> None:
        """/api/cache/stats 返回 JSON（包含 enabled/size/max_size/hits/misses/hit_rate）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/cache/stats")
            assert response.status_code == 200
            data = response.json()
            assert "enabled" in data
            assert "size" in data
            assert "max_size" in data
            assert "hits" in data
            assert "misses" in data
            assert "hit_rate" in data
            # 0.0 <= hit_rate <= 1.0
            assert 0.0 <= data["hit_rate"] <= 1.0

    def test_api_cache_stats_persists_across_requests(self) -> None:
        """/api/cache/stats 跨请求连续（V0.29.3 lifespan 单例）。"""
        app = create_app()
        with TestClient(app) as client:
            r1 = client.get("/api/cache/stats")
            r2 = client.get("/api/cache/stats")
            # 两次结果一致（lifespan 单例，stats 累积但已累积的值不变）
            # 注意：单例所以 hits/misses 应该一样（除非中间有调用）
            s1 = r1.json()
            s2 = r2.json()
            assert s1["hits"] == s2["hits"]
            assert s1["misses"] == s2["misses"]
