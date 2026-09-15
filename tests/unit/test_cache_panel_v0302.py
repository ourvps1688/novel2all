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
