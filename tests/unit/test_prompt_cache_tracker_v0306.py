"""V0.30.6 C1：PromptCacheTracker + LLMProvider 集成测试。"""

from __future__ import annotations

import pytest

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.prompt_cache_tracker import PromptCacheTracker

# === Test 1: PromptCacheTracker 基础功能 ===

class TestPromptCacheTrackerBasics:
    """V0.30.6 C1：PromptCacheTracker 单元测试（无 LLMProvider 依赖）。"""

    def test_initial_state(self) -> None:
        """V0.30.6 C1：新 tracker 全零。"""
        t = PromptCacheTracker()
        assert t.prefix_hits == 0
        assert t.prefix_misses == 0
        assert t.total == 0
        assert t.hit_rate == 0.0
        assert t.unique_sys_prompts == 0
        assert t.cost_saved_cny == 0.0
        assert t.potential_savings_cny == 0.0

    def test_record_first_sys_hash_is_miss(self) -> None:
        """V0.30.6 C1：首次 sys_hash → miss（prefix_misses=1, returns False）。"""
        t = PromptCacheTracker()
        result = t.record("hash_a")
        assert result is False
        assert t.prefix_hits == 0
        assert t.prefix_misses == 1
        assert t.unique_sys_prompts == 1

    def test_record_reused_sys_hash_is_hit(self) -> None:
        """V0.30.6 C1：复用 sys_hash → hit（prefix_hits+=1, returns True）。"""
        t = PromptCacheTracker()
        t.record("hash_a")
        result = t.record("hash_a")
        assert result is True
        assert t.prefix_hits == 1
        assert t.prefix_misses == 1
        assert t.unique_sys_prompts == 1

    def test_hit_rate_calculation(self) -> None:
        """V0.30.6 C1：hit_rate = hits / total（0.0-1.0 范围）。"""
        t = PromptCacheTracker()
        t.record("a")  # miss
        t.record("a")  # hit
        t.record("a")  # hit
        t.record("a")  # hit
        # hits=3, misses=1, total=4, rate=0.75
        assert t.hit_rate == 0.75

    def test_cost_saved_cny_calculation(self) -> None:
        """V0.30.6 C1：cost_saved_cny = hits × (miss-hit) × tokens / 1M。

        默认配置：(1.00 - 0.02) × 5000 / 1M = 0.0049 CNY/call
        10 hits → 0.049 CNY
        """
        t = PromptCacheTracker()
        for _ in range(10):
            t.record("hash_x")  # 第一次 miss, 之后 9 次 hit
        # 实际：首次 miss，9 次 hit
        assert t.prefix_misses == 1
        assert t.prefix_hits == 9
        expected = 9 * (1.00 - 0.02) * 5000 / 1_000_000
        assert t.cost_saved_cny == pytest.approx(round(expected, 6))

    def test_potential_savings_cny(self) -> None:
        """V0.30.6 C1：potential_savings = total × saved_per_call（理论上界）。"""
        t = PromptCacheTracker()
        for _ in range(10):
            t.record("hash_y")
        expected = 10 * (1.00 - 0.02) * 5000 / 1_000_000
        assert t.potential_savings_cny == pytest.approx(round(expected, 6))

    def test_to_dict_structure(self) -> None:
        """V0.30.6 C1：to_dict() 含所有 expected 字段。"""
        t = PromptCacheTracker()
        t.record("a")
        t.record("a")
        d = t.to_dict()
        assert d["enabled"] is True
        assert d["prefix_hits"] == 1
        assert d["prefix_misses"] == 1
        assert d["total"] == 2
        assert d["hit_rate"] == 0.5
        assert d["unique_sys_prompts"] == 1
        assert "cost_saved_cny" in d
        assert "potential_savings_cny" in d
        assert "model" in d
        assert d["model"]["cache_hit_price_cny_per_m"] == 0.02

    def test_reset_clears_all(self) -> None:
        """V0.30.6 C1：reset() 清零所有状态。"""
        t = PromptCacheTracker()
        t.record("a")
        t.record("a")
        t.record("b")
        t.reset()
        assert t.prefix_hits == 0
        assert t.prefix_misses == 0
        assert t.unique_sys_prompts == 0
        assert t.hit_rate == 0.0

    def test_unique_sys_hashes_tracking(self) -> None:
        """V0.30.6 C1：unique_sys_prompts 正确去重。"""
        t = PromptCacheTracker()
        t.record("a")
        t.record("a")
        t.record("b")
        t.record("a")
        t.record("c")
        t.record("c")
        assert t.unique_sys_prompts == 3


# === Test 2: LLMProvider 集成 ===

class TestLLMProviderPromptCacheIntegration:
    """V0.30.6 C1：LLMProvider 自动跟踪 prompt prefix cache。"""

    def test_provider_has_prompt_tracker(self) -> None:
        """V0.30.6 C1：LLMProvider 实例化后自动创建 _prompt_tracker。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        assert hasattr(provider, "_prompt_tracker")
        assert isinstance(provider._prompt_tracker, PromptCacheTracker)

    def test_provider_prompt_cache_stats_method(self) -> None:
        """V0.30.6 C1：prompt_cache_stats() 返回 tracker.to_dict()。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        stats = provider.prompt_cache_stats()
        assert "prefix_hits" in stats
        assert "prefix_misses" in stats
        assert "total" in stats
        assert "hit_rate" in stats

    def test_provider_cache_stats_includes_prompt_prefix(self) -> None:
        """V0.30.6 C1：cache_stats() 含 prompt_prefix 子字典。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        stats = provider.cache_stats()
        assert "prompt_prefix" in stats
        assert "prefix_hits" in stats["prompt_prefix"]

    def test_provider_reset_prompt_cache_stats(self) -> None:
        """V0.30.6 C1：reset_prompt_cache_stats() 清零统计。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        provider._prompt_tracker.record("a")
        provider._prompt_tracker.record("a")
        assert provider._prompt_tracker.prefix_hits == 1
        provider.reset_prompt_cache_stats()
        assert provider._prompt_tracker.prefix_hits == 0
        assert provider._prompt_tracker.prefix_misses == 0

    def test_provider_make_cache_key_records_sys_hash(self) -> None:
        """V0.30.6 C1：_make_cache_key() 后自动记录 sys_hash。

        注意：cache_enabled=False 时不调 cache，但 prompt tracker 仍记录。
        这是设计：prompt prefix tracking 与 response cache 解耦。
        """
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        initial_hits = provider._prompt_tracker.prefix_hits
        initial_misses = provider._prompt_tracker.prefix_misses

        # 模拟两次相同 system + 不同 user 的调用
        provider._make_cache_key("model_x", "system_A", "user_1", 0.7)
        provider._make_cache_key("model_x", "system_A", "user_2", 0.7)
        provider._make_cache_key("model_x", "system_A", "user_3", 0.7)

        # 第一次是 miss，后续都是 hit（因为 sys_hash 相同）
        assert provider._prompt_tracker.prefix_misses == initial_misses + 1
        assert provider._prompt_tracker.prefix_hits == initial_hits + 2


# === Test 3: Web API 端点 ===

class TestPromptCacheStatsEndpoint:
    """V0.30.6 C1：/api/cache/prompt-stats + /api/cache/prompt-stats/reset 端点。"""

    def test_prompt_stats_endpoint(self) -> None:
        """V0.30.6 C1：GET /api/cache/prompt-stats 返回 prompt prefix stats。"""
        from fastapi.testclient import TestClient

        from novel2all.web.app import create_app

        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/cache/prompt-stats")
            assert response.status_code == 200
            data = response.json()
            assert "prefix_hits" in data
            assert "prefix_misses" in data
            assert "hit_rate" in data
            assert "cost_saved_cny" in data
            assert "model" in data

    def test_prompt_stats_reset_endpoint(self) -> None:
        """V0.30.6 C1：POST /api/cache/prompt-stats/reset 重置统计。"""
        from fastapi.testclient import TestClient

        from novel2all.web.app import create_app

        app = create_app()
        with TestClient(app) as client:
            # 先注入数据
            app.state.provider._prompt_tracker.record("test_hash")
            assert app.state.provider._prompt_tracker.prefix_hits >= 0

            # reset
            response = client.post("/api/cache/prompt-stats/reset")
            assert response.status_code == 200
            data = response.json()
            assert data["reset"] is True
            assert data["stats"]["prefix_hits"] == 0
            assert data["stats"]["prefix_misses"] == 0

    def test_cache_stats_endpoint_includes_prompt_prefix(self) -> None:
        """V0.30.6 C1：/api/cache/stats 自动含 prompt_prefix 子字典。"""
        from fastapi.testclient import TestClient

        from novel2all.web.app import create_app

        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/cache/stats")
            assert response.status_code == 200
            data = response.json()
            assert "prompt_prefix" in data
            assert data["prompt_prefix"]["prefix_hits"] >= 0


# === Test 4: 成本计算准确性 ===

class TestCostSavingsCalculation:
    """V0.30.6 C1：cost_saved_cny 数学正确性。"""

    def test_default_config_cost_per_call(self) -> None:
        """V0.30.6 C1：默认配置下每次 prefix hit 节省 ¥0.0049。

        (1.00 - 0.02) × 5000 / 1M = 0.0049 CNY/call
        """
        t = PromptCacheTracker()
        saved = (t.cache_miss_price_cny_per_m - t.cache_hit_price_cny_per_m) * t.avg_input_tokens_per_call / 1_000_000
        assert saved == pytest.approx(0.0049)

    def test_high_hit_rate_savings(self) -> None:
        """V0.30.6 C1：90% 命中率时 1000 calls 节省 ¥4.41。

        1000 calls × 90% hit × 0.0049 = 4.41 CNY
        """
        t = PromptCacheTracker()
        # 100 个 unique sys + 900 次复用
        for i in range(100):
            t.record(f"unique_{i}")
        for i in range(100):
            for _ in range(9):  # 每个复用 9 次
                t.record(f"unique_{i}")
        # 100 unique (miss) + 900 hit
        assert t.prefix_misses == 100
        assert t.prefix_hits == 900
        # 900 × 0.0049 = 4.41
        assert t.cost_saved_cny == pytest.approx(4.41, abs=0.01)



    def test_prompt_cache_panel_endpoint(self) -> None:
        """V0.30.6 C1：GET /page/prompt-cache-panel 返回 HTML 面板。"""
        from fastapi.testclient import TestClient

        from novel2all.web.app import create_app

        app = create_app()
        with TestClient(app) as client:
            response = client.get("/page/prompt-cache-panel")
            assert response.status_code == 200
            html = response.text
            # 验证关键 UI 元素存在
            assert "Prompt Prefix Cache" in html
            assert "data-testid=\"prompt-cache-panel\"" in html
            assert "¥" in html  # 成本金额
            assert "Prefix Hits" in html
            assert "Prefix Misses" in html

    def test_zero_hits_zero_savings(self) -> None:
        """V0.30.6 C1：零命中时 cost_saved_cny = 0。

        100 个不同 sys_hash → 全部 miss → 0 hits → cost_saved = 0
        """
        t = PromptCacheTracker()
        for i in range(100):
            t.record(f"unique_{i}")  # 全部 miss（每个都是首次出现）
        assert t.prefix_hits == 0
        assert t.prefix_misses == 100
        assert t.cost_saved_cny == 0.0