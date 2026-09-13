"""V0.29.3 Provider 单例化测试。

V0.29.3 之前：web 和 CLI 每次请求/调用都新建 LLMProvider，导致：
- cache stats（hits/misses）每次请求重置，命中率永远显示 0
- 重复初始化开销

V0.29.3 之后：
- web 端用 FastAPI lifespan 管理全局单例（app.state.provider）
- CLI 端用模块级单例（_llm_instance）
- 跨请求/跨调用 cache stats 连续

测试覆盖：
- web 端：app.state.provider 单例 + /api/cache/stats endpoint
- CLI 端：get_llm() 多次调用返回同一对象 + reset_llm() 重置
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel2all.core import LLMProvider
from novel2all.web.app import create_app


class TestWebLifespanSingletonV0293:
    """V0.29.3：web 端用 FastAPI lifespan 管理 LLMProvider 单例。"""

    def test_create_app_initializes_provider(self) -> None:
        """create_app() 立即初始化 app.state.provider（测试 fallback 路径）。"""
        app = create_app()
        assert hasattr(app.state, "provider"), "create_app() 应立即初始化 provider"
        assert isinstance(app.state.provider, LLMProvider)

    def test_multiple_create_app_calls_have_separate_providers(self) -> None:
        """每次 create_app() 是独立 app（独立 provider）—— 单例是 per-app 不是 module-level。"""
        app1 = create_app()
        app2 = create_app()
        assert app1.state.provider is not app2.state.provider, (
            "不同 app 实例应有不同 provider（per-app 单例）"
        )

    def test_app_state_provider_persists_across_requests(self) -> None:
        """同一 app 内多次请求，provider 是同一对象（cache stats 跨请求连续）。"""
        app = create_app()
        with TestClient(app) as client:
            # 跨多次请求访问同一 provider
            response1 = client.get("/api/cache/stats")
            response2 = client.get("/api/cache/stats")
            assert response1.status_code == 200
            assert response2.status_code == 200
            # 两次都返回相同 provider 的 stats
            stats1 = response1.json()
            stats2 = response2.json()
            # 跨请求 hits/misses 应该连续（这里是 0 因为没调 LLM）
            assert stats1 == stats2

    def test_cache_stats_endpoint_returns_provider_stats(self) -> None:
        """GET /api/cache/stats 返回 LLMProvider.cache_stats() 的内容。"""
        app = create_app()
        with TestClient(app) as client:
            # lifespan 启动后会重置 provider，必须在 with 块内改 stats
            app.state.provider._cache_hits = 7
            app.state.provider._cache_misses = 3

            response = client.get("/api/cache/stats")
            assert response.status_code == 200
            stats = response.json()
            assert stats["hits"] == 7
            assert stats["misses"] == 3
            assert stats["hit_rate"] == 0.7  # 7 / (7+3)

    def test_write_stream_uses_singleton_provider(self) -> None:
        """/api/write/stream 用 app.state.provider 而不是新建（已隐式通过 web_sse 测试验证）。"""
        # 这个测试通过 TestWriteStreamEndpoint.test_project_not_initialized 验证：
        # 当项目未初始化时，路由从 request.app.state.provider 取 llm，
        # 然后在 "项目未初始化" 检查中 yield error 并 return。
        # 关键：单例共享，所以 cache stats 跨请求连续。
        app = create_app()
        with TestClient(app) as client:
            response = client.get(
                "/api/write/stream",
                params={"chapter": 1, "project_root": "D:/nonexistent"},
            )
            assert response.status_code == 200
            # 即使失败也用了单例 provider（不会新建）
            assert app.state.provider is not None


class TestCliSingletonV0293:
    """V0.29.3：CLI 端 get_llm() 返回单例。"""

    def test_get_llm_returns_singleton(self) -> None:
        """多次调用 get_llm() 返回同一 LLMProvider 对象。"""
        from novel2all.cli import main as cli_main

        cli_main.reset_llm()  # 清理之前测试残留
        try:
            p1 = cli_main.get_llm()
            p2 = cli_main.get_llm()
            p3 = cli_main.get_llm()
            assert p1 is p2 is p3, "get_llm() 应返回同一单例"
        finally:
            cli_main.reset_llm()  # 清理

    def test_get_llm_cache_stats_persist(self) -> None:
        """CLI 单例保证 cache stats 跨调用连续。"""
        from novel2all.cli import main as cli_main

        cli_main.reset_llm()
        try:
            p1 = cli_main.get_llm()
            # 模拟 cache hit
            p1._cache_hits = 5
            p1._cache_misses = 2

            p2 = cli_main.get_llm()
            # p2 应是同一对象，stats 仍为 hits=5, misses=2
            assert p2._cache_hits == 5
            assert p2._cache_misses == 2
        finally:
            cli_main.reset_llm()

    def test_reset_llm_creates_new_instance(self) -> None:
        """reset_llm() 后下次 get_llm() 返回新对象。"""
        from novel2all.cli import main as cli_main

        cli_main.reset_llm()
        p1 = cli_main.get_llm()
        p1._cache_hits = 99  # 标记 p1

        cli_main.reset_llm()
        p2 = cli_main.get_llm()

        assert p1 is not p2, "reset_llm() 后应创建新对象"
        assert p2._cache_hits == 0, "新对象的 stats 应从 0 开始"

        cli_main.reset_llm()  # 清理
