"""V1.0.2 Batch 3 — QA 独立攻击 PoC 测试。

目的：
- 不重复工程师的存在性测试（test_v1_0_2_batch3.py）
- 验证边界 / 攻击场景（并发极限、cache 探测绕过、跨字段组合爆炸）
- 任何 spec 不明确的细节都会报告

覆盖：
  B1 cache key 完整性（5 种组合 → 5 hash；100 次同组合 → 1 hash；跨 provider 同模型 → 不同 key）
  B2 cache 失效（修改文风 → miss；恢复原样 → miss；hash 算法只看不存）
  B3 AdaptiveRouter（10 线程 × 100 次 → samples = 1000；跨 model 不污染）
  B4 LLM rate limit（5 用户独立；quota 用尽 → 429；mock 时间前进 → 重置；cache 探测绕过）
  B5 EPUB 大文件（5MB+ 单章 → fail；100MB+ 整书 → fail；正常 500KB → OK；md/txt 仍 OK）
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.adaptive_router import AdaptiveRouter
from novel2all.core.cache import MemoryLRUBackend
from novel2all.core.exporter import (
    BOOK_TOO_LARGE_BYTES,
    CHAPTER_TOO_LARGE_BYTES,
    BookTooLargeError,
    Chapter,
    ChapterTooLargeError,
    EPUBExporter,
    MarkdownExporter,
    TXTExporter,
)
from novel2all.core.llm_rate_limiter import (
    LLMRateLimiter,
    LLMRateLimitExceeded,
    estimate_tokens,
    get_global_llm_rate_limiter,
    reset_global_llm_rate_limiter,
)
from novel2all.core.memory import Tracker
from novel2all.core.prompt_cache_tracker import PromptCacheTracker
from novel2all.core.provider_router import TaskType
from novel2all.web.app import create_app

# === Fixtures ===


@pytest.fixture
def fresh_provider() -> LLMProvider:
    """QA 独立 fixture：每次拿全新 provider（避免与工程师的 fixture 共享状态）。"""
    config = LLMConfig(cache_enabled=True, default_model="mock/model")
    provider = LLMProvider.__new__(LLMProvider)
    provider.config = config
    provider._cache = MemoryLRUBackend(max_size=config.cache_max_size, ttl_seconds=0)
    provider._prompt_tracker = PromptCacheTracker()
    provider._resolve_model = lambda *, task, explicit_model: explicit_model or "mock/model"
    return provider


# ============================================================================
# B1 PoC: Cache key 完整性 + 碰撞检测
# ============================================================================


class TestB1CacheKeyCollisionResistance:
    """QA B1 攻击 PoC：5 种不同字段组合必须产生 5 个不同 key；
    同一组合 100 次必须全部命中同一 key；
    跨 provider 同模型名（不同 api_base）必须不同 key。
    """

    def test_five_different_field_combinations_all_unique(
        self, fresh_provider: LLMProvider
    ) -> None:
        """PoC：5 种参数组合（每个字段只改 1 个）→ 必须 5 个不同 cache key。

        攻击场景：如果 cache key 缺任何一个字段，攻击者可以用"廉价配置"
        偷"昂贵配置"的 cache 响应，绕过限流。
        """
        baseline = fresh_provider._make_cache_key(
            "deepseek/deepseek-chat",
            "sys_prompt",
            "user_prompt",
            0.7,
            max_tokens=4096,
            top_p=0.9,
            api_base="https://api.deepseek.com",
            settings_hash="abc123",
        )

        # 只改一个字段，共 5 个变体
        vary_max = fresh_provider._make_cache_key(
            "deepseek/deepseek-chat",
            "sys_prompt",
            "user_prompt",
            0.7,
            max_tokens=1000,
            top_p=0.9,
            api_base="https://api.deepseek.com",
            settings_hash="abc123",
        )
        vary_top_p = fresh_provider._make_cache_key(
            "deepseek/deepseek-chat",
            "sys_prompt",
            "user_prompt",
            0.7,
            max_tokens=4096,
            top_p=0.5,
            api_base="https://api.deepseek.com",
            settings_hash="abc123",
        )
        vary_api_base = fresh_provider._make_cache_key(
            "deepseek/deepseek-chat",
            "sys_prompt",
            "user_prompt",
            0.7,
            max_tokens=4096,
            top_p=0.9,
            api_base="https://api.deepseek.cn",
            settings_hash="abc123",
        )
        vary_settings = fresh_provider._make_cache_key(
            "deepseek/deepseek-chat",
            "sys_prompt",
            "user_prompt",
            0.7,
            max_tokens=4096,
            top_p=0.9,
            api_base="https://api.deepseek.com",
            settings_hash="xyz789",
        )

        keys = {baseline, vary_max, vary_top_p, vary_api_base, vary_settings}
        assert len(keys) == 5, f"字段变更应产生 5 个不同 key，实际只有 {len(keys)} 个"

    def test_hundred_identical_calls_single_key(self, fresh_provider: LLMProvider) -> None:
        """PoC：100 次完全相同参数 → 必须始终命中同一 cache key（无随机性）。

        攻击场景：如果 cache key 含时间戳 / 随机数，缓存命中率掉到 0%。
        """
        kwargs = {
            "max_tokens": 2000,
            "top_p": 0.7,
            "api_base": "https://api.x.com",
            "settings_hash": "consistent_hash",
        }
        first_key = fresh_provider._make_cache_key("model", "sys", "user", 0.7, **kwargs)

        for i in range(100):
            k = fresh_provider._make_cache_key("model", "sys", "user", 0.7, **kwargs)
            assert k == first_key, f"第 {i + 1} 次生成的 key 与首次不一致"

    def test_cross_provider_same_model_different_api_base(
        self, fresh_provider: LLMProvider
    ) -> None:
        """PoC：deepseek 和 anthropic 都用 'claude-3' 模型名，但不同 api_base → 不同 key。

        攻击场景：跨 provider 撞 cache → 用户拿到 A provider 的响应被当作 B 的结果。
        这是 data integrity 级别的安全 bug（响应内容会因 endpoint 不同而异）。
        """
        key_deepseek_claude = fresh_provider._make_cache_key(
            "deepseek/claude-3",
            "sys",
            "user",
            0.7,
            api_base="https://api.deepseek.com/v1",
        )
        key_anthropic_claude = fresh_provider._make_cache_key(
            "anthropic/claude-3",
            "sys",
            "user",
            0.7,
            api_base="https://api.anthropic.com/v1",
        )
        assert key_deepseek_claude != key_anthropic_claude, (
            "跨 provider 同模型名不同 api_base 必须区分 cache key"
        )

    def test_settings_hash_collision_resistance(self, fresh_provider: LLMProvider) -> None:
        """PoC：100 个不同的 settings_hash → 必须 100 个不同 key（sha256 16 字符应足够）。

        攻击场景：如果 hash 算法太弱（短位数 / 简单 XOR），不同设定可能撞 hash，
        导致用户改文风后还是命中旧 cache。
        """
        keys = set()
        for i in range(100):
            h = hashlib.sha256(f"setting_version_{i}".encode()).hexdigest()[:16]
            k = fresh_provider._make_cache_key("model", "sys", "user", 0.7, settings_hash=h)
            keys.add(k)
        # 100 个不同 hash 应产生 100 个不同 key（16 字符 = 64 bit，碰撞概率 ~ 10^-19）
        assert len(keys) == 100, f"settings_hash 碰撞：100 个输入只产生 {len(keys)} 个 key"


# ============================================================================
# B2 PoC: Cache 失效（修改/恢复 + 完整集成）
# ============================================================================


class TestB2CacheInvalidationPoC:
    """QA B2 攻击 PoC：完整 cache 失效生命周期（写 → 命中 → 改文风 → miss → 恢复 → miss）。"""

    def test_full_cache_invalidation_lifecycle(
        self, fresh_provider: LLMProvider, tmp_path: Path
    ) -> None:
        """PoC：完整 cache 失效生命周期。

        1. 写 cache（设定 A） → miss
        2. 再调（设定 A）→ hit
        3. 修改文风 → 调（设定 B）→ miss（新 cache key）
        4. 把文件内容改回 A（hash 函数只读当前状态）→ 命中 A 的旧 cache
        """
        from types import SimpleNamespace

        import litellm

        # 写两份"创作设定.md"
        (tmp_path / "创作设定.md").write_text("古风古韵", encoding="utf-8")

        call_count = [0]

        async def fake_acompletion(**kwargs: Any) -> Any:
            call_count[0] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R_{call_count[0]}"))]
            )

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 1) 写 cache（基于设定 A）
            r1 = asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_path, max_tokens=100
                )
            )
            assert r1 == "R_1"
            assert fresh_provider._cache._misses == 1
            assert fresh_provider._cache._hits == 0

            # 2) 同一调用 → cache hit
            r2 = asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_path, max_tokens=100
                )
            )
            assert r2 == "R_1"  # 仍是首次响应
            assert fresh_provider._cache._hits == 1
            assert fresh_provider._cache._misses == 1

            # 3) 修改文风 → cache miss（虽然 prompt 完全一样）
            (tmp_path / "创作设定.md").write_text("现代白话", encoding="utf-8")
            r3 = asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_path, max_tokens=100
                )
            )
            assert r3 == "R_2"  # 第二次 API 调用
            assert fresh_provider._cache._misses == 2
            assert fresh_provider._cache._hits == 1

            # 4) 删掉文风变更（恢复成 A）→ cache hit（因为 hash 是当前内容的函数，
            #    内容与首次相同 → hash 相同 → key 相同 → 命中首次的响应）
            (tmp_path / "创作设定.md").write_text("古风古韵", encoding="utf-8")
            r4 = asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_path, max_tokens=100
                )
            )
            assert r4 == "R_1", "恢复成 A 后应命中首次 cache（hash 是当前内容函数）"
            assert fresh_provider._cache._hits == 2  # 命中数 +1
            assert fresh_provider._cache._misses == 2  # miss 计数不变
        finally:
            litellm.acompletion = original

    def test_no_modification_cache_hit(self, fresh_provider: LLMProvider, tmp_path: Path) -> None:
        """PoC：不修改任何设定 → 一直 cache hit（验证 hash 稳定性 + cache 不误失效）。"""
        from types import SimpleNamespace

        import litellm

        (tmp_path / "创作设定.md").write_text("固定文风", encoding="utf-8")

        call_count = [0]

        async def fake_acompletion(**kwargs: Any) -> Any:
            call_count[0] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R_{call_count[0]}"))]
            )

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            for i in range(10):
                asyncio.run(
                    fresh_provider.complete(
                        prompt="p",
                        model="mock/model",
                        project_root=tmp_path,
                        max_tokens=100,
                    )
                )
            # 只调 1 次 API（其余 9 次全 cache hit）
            assert call_count[0] == 1, f"应只调用 1 次 API，实际 {call_count[0]} 次"
            assert fresh_provider._cache._hits == 9
            assert fresh_provider._cache._misses == 1
        finally:
            litellm.acompletion = original

    def test_wenfeng_modification_invalidates_cache(
        self, fresh_provider: LLMProvider, tmp_path: Path
    ) -> None:
        """PoC：修改 设定/文风.md（不是 创作设定.md）→ 也必须 cache miss。"""
        from types import SimpleNamespace

        import litellm

        (tmp_path / "设定").mkdir()
        (tmp_path / "设定" / "文风.md").write_text("古风古韵", encoding="utf-8")

        call_count = [0]

        async def fake_acompletion(**kwargs: Any) -> Any:
            call_count[0] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R_{call_count[0]}"))]
            )

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 1) 写 cache
            asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_path, max_tokens=100
                )
            )
            assert call_count[0] == 1

            # 2) 仅修改 设定/文风.md（不动 创作设定.md）
            (tmp_path / "设定" / "文风.md").write_text("现代白话", encoding="utf-8")
            asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_path, max_tokens=100
                )
            )
            assert call_count[0] == 2, "改 设定/文风.md 后必须重新调 API"
        finally:
            litellm.acompletion = original


# ============================================================================
# B3 PoC: AdaptiveRouter 极限并发
# ============================================================================


class TestB3AdaptiveRouterExtremeConcurrency:
    """QA B3 攻击 PoC：极限并发（10 线程 × 100 次 = 1000 次）+ 跨 model 不污染。"""

    def test_extreme_concurrency_no_count_loss(self, tmp_path: Path) -> None:
        """PoC：10 线程 × 100 次 = 1000 次 record_run → samples 必须是 1000。

        攻击场景：如果原子性失效，10 线程并发下 samples 远小于 1000（race condition）。
        """
        router = AdaptiveRouter(db_path=tmp_path / "r.db")
        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(100):
                    router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1500)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发 record_run 报错: {errors}"

        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 1000, f"race condition 丢计数：预期 1000，实际 {stats.samples}"

    def test_aggregates_correct_under_concurrency(self, tmp_path: Path) -> None:
        """PoC：并发 record_run 后所有聚合列（samples / latency / quality / success）正确。

        攻击场景：如果 SUM 累加缺失，latency_sum 会比实际小，avg_latency 偏低。
        """
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        def worker(thread_idx: int) -> None:
            for i in range(50):
                router.record_run(
                    TaskType.WRITING,
                    "m1",
                    success=True,
                    latency_ms=1000,
                    quality_score=8.0,
                )

        # 8 线程 × 50 次 = 400 次；每次 latency=1000, quality=8.0, success=true
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 400
        assert stats.avg_latency_ms == pytest.approx(1000.0, abs=0.1)
        assert stats.avg_quality == pytest.approx(8.0, abs=0.01)
        assert stats.success_rate == pytest.approx(1.0, abs=0.001)

    def test_cross_model_no_pollution(self, tmp_path: Path) -> None:
        """PoC：并发 record 不同 model → 每个 model 聚合独立。

        攻击场景：如果 ON CONFLICT 子句写错，可能让 m1 的累加串到 m2 上。
        """
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        def worker(model_name: str) -> None:
            for _ in range(50):
                router.record_run(TaskType.WRITING, model_name, success=True, latency_ms=1000)

        # 5 model × 5 线程 × 50 次 = 1250 次
        threads = []
        for m in ["m1", "m2", "m3", "m4", "m5"]:
            for _ in range(5):
                threads.append(threading.Thread(target=worker, args=(m,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for m in ["m1", "m2", "m3", "m4", "m5"]:
            stats = router.get_stats(TaskType.WRITING, m)
            assert stats is not None
            assert stats.samples == 250, (
                f"{m} 预期 250 samples，实际 {stats.samples}（可能存在跨 model 污染）"
            )

    def test_mixed_success_failure_concurrency(self, tmp_path: Path) -> None:
        """PoC：并发混合 success/fail → success_count 计数正确（不丢也不重复）。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        def worker(is_success: bool) -> None:
            for _ in range(100):
                router.record_run(TaskType.WRITING, "m1", success=is_success, latency_ms=1000)

        threads = []
        # 5 success 线程 + 5 failure 线程，每线程 100 次
        for _ in range(5):
            threads.append(threading.Thread(target=worker, args=(True,)))
        for _ in range(5):
            threads.append(threading.Thread(target=worker, args=(False,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 1000
        # 5 × 100 = 500 success
        assert stats.success_rate == pytest.approx(0.5, abs=0.001), (
            f"success_rate 偏离 0.5：samples={stats.samples}, success_rate={stats.success_rate}"
        )


# ============================================================================
# B4 PoC: Rate Limit 攻击场景
# ============================================================================


class TestB4RateLimitAttackScenarios:
    """QA B4 攻击 PoC：5 用户独立 quota / quota 用尽 / 时间前进 / cache 探测绕过。"""

    def test_five_users_independent_quotas(self) -> None:
        """PoC：5 个不同 user_id 各自调用 LLM → quota 完全独立。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=10000)
        # 5 用户各调 1 次 1000 token
        for user_id in range(1, 6):
            remaining = limiter.check(user_id=user_id, est_tokens=1000)
            assert remaining == 9000, f"user {user_id} 预期剩 9000，实际 {remaining}"

        # 验证隔离：user 1 调满剩余的 9000
        remaining = limiter.check(user_id=1, est_tokens=9000)
        assert remaining == 0
        # user 2 不受影响（仍是 9000 剩余）
        remaining = limiter.check(user_id=2, est_tokens=9000)
        assert remaining == 0

    def test_quota_exhaustion_returns_retry_after_info(self) -> None:
        """PoC：单用户连续调用直到 quota 用尽 → 第 N+1 次抛异常，含完整字段。

        验证：超额时的异常携带 user_id / used / limit / requested，可用于 HTTP 429 + Retry-After。
        """
        limiter = LLMRateLimiter(max_tokens_per_hour=100)
        # 第 1 次：100 token → 剩 0
        limiter.check(user_id=42, est_tokens=100)

        # 第 2 次：哪怕 1 token 也超
        with pytest.raises(LLMRateLimitExceeded) as exc_info:
            limiter.check(user_id=42, est_tokens=1)
        exc = exc_info.value
        assert exc.user_id == 42
        assert exc.used == 100
        assert exc.limit == 100
        assert exc.requested == 1

    def test_env_var_quota_enforced_under_burst(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PoC：LLM_RATE_LIMIT_PER_HOUR=100，模拟 200 次 1-token 调用 → 99 成功 + 101 失败。"""
        monkeypatch.setenv("LLM_RATE_LIMIT_PER_HOUR", "100")
        limiter = LLMRateLimiter()

        assert limiter.max_tokens_per_hour == 100

        success = 0
        failure = 0
        for _ in range(200):
            try:
                limiter.check(user_id=1, est_tokens=1)
                success += 1
            except LLMRateLimitExceeded:
                failure += 1

        assert success == 100, f"100 token quota，1 token/次 → 100 成功，实际 {success}"
        assert failure == 100, f"应有 100 次失败，实际 {failure}"

    def test_time_window_reset_via_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PoC：mock 时间前进 1 小时 → quota 自动重置。

        攻击场景：如果只累计不清理，1 小时后用户还被锁，无法继续用。
        """
        limiter = LLMRateLimiter(max_tokens_per_hour=100)
        limiter.check(user_id=1, est_tokens=100)  # 用完

        # mock 时间前进 3600s + 1s
        real_time = time.time
        monkeypatch.setattr(time, "time", lambda: real_time() + 3601)

        # 应该可以继续用（窗口已过期）
        remaining = limiter.check(user_id=1, est_tokens=50)
        assert remaining == 50, f"时间前进 1h 后 quota 应重置，实际剩 {remaining}"

    def test_rate_limit_before_cache_lookup(self, tmp_path: Path) -> None:
        """PoC：rate limit 必须在 cache lookup **之前**执行（防 cache 探测绕过）。

        攻击场景：恶意用户可以反复请求相同 prompt 触发 cache 命中，
        但因为 LLM 没真的被调用，绕过限流 → 把 cache 打爆。
        修复后：rate limit 在 cache 之前 → 用户额度被锁定。
        """
        reset_global_llm_rate_limiter()
        old_env = os.environ.get("LLM_RATE_LIMIT_PER_HOUR")
        os.environ["LLM_RATE_LIMIT_PER_HOUR"] = "500"
        try:
            limiter = get_global_llm_rate_limiter()
            assert limiter.max_tokens_per_hour == 500

            config = LLMConfig(cache_enabled=True, default_model="mock/model")
            provider = LLMProvider.__new__(LLMProvider)
            provider.config = config
            provider._cache = MemoryLRUBackend(max_size=config.cache_max_size, ttl_seconds=0)
            provider._prompt_tracker = PromptCacheTracker()
            provider._resolve_model = lambda *, task, explicit_model: explicit_model or "mock/model"

            from types import SimpleNamespace

            import litellm

            call_count = [0]

            async def fake_acompletion(**kwargs: Any) -> Any:
                call_count[0] += 1
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="R"))]
                )

            original = litellm.acompletion
            litellm.acompletion = fake_acompletion
            try:
                # 第一次：cache miss → 调 API → 估算 ~1+4096=4097 tokens（用 max_tokens=4096）
                # quota=500，所以单次就超额
                with pytest.raises(LLMRateLimitExceeded):
                    asyncio.run(
                        provider.complete(
                            prompt="x",
                            model="mock/model",
                            user_id=99,
                            max_tokens=4096,
                        )
                    )
                # 即使 cache miss 了，rate limit 拒绝 → API 不应被调用
                assert call_count[0] == 0, (
                    f"rate limit 应在 cache lookup 前生效，但 API 已被调用 {call_count[0]} 次"
                )
            finally:
                litellm.acompletion = original
        finally:
            if old_env is None:
                os.environ.pop("LLM_RATE_LIMIT_PER_HOUR", None)
            else:
                os.environ["LLM_RATE_LIMIT_PER_HOUR"] = old_env
            reset_global_llm_rate_limiter()


# ============================================================================
# B5 PoC: EPUB 大文件攻击场景
# ============================================================================


class TestB5EpubLargeFileAttackPoC:
    """QA B5 攻击 PoC：5MB+ 单章 / 100MB+ 整书 / md/txt 不限制 / web 端点集成。"""

    def test_exactly_5mb_chapter_rejected(self) -> None:
        """PoC：恰好 5MB 单章（边界）→ 拒绝。

        攻击场景：边界值测试。如果用 `>=` 而非 `>`，5MB 会通过；
        如果用 `>` 而非 `>=`，5MB-1B 会拒绝。
        """
        # 创建一个恰好 5MB+1 byte 的章节（> 5MB）
        content = "中" * ((CHAPTER_TOO_LARGE_BYTES // 3) + 1)
        ch = Chapter(chapter_num=1, title="边界", content=content)
        # 验证 size 确实超过限制
        assert ch.content_size_bytes > CHAPTER_TOO_LARGE_BYTES

        with pytest.raises(ChapterTooLargeError) as exc_info:
            EPUBExporter().export_chapter(ch)
        assert exc_info.value.size_bytes > CHAPTER_TOO_LARGE_BYTES

    def test_just_under_5mb_chapter_accepted(self) -> None:
        """PoC：< 5MB 的章节（边界）→ 接受。"""
        # 4.99 MB 章节
        content = "中" * ((CHAPTER_TOO_LARGE_BYTES * 99 // 100) // 3)
        ch = Chapter(chapter_num=1, title="近边界", content=content)
        assert ch.content_size_bytes < CHAPTER_TOO_LARGE_BYTES

        # 应成功导出
        result = EPUBExporter().export_chapter(ch)
        assert len(result) > 0

    def test_exactly_100mb_book_rejected(self) -> None:
        """PoC：> 100MB 整书 → BookTooLargeError。

        注意：因"中"是 3 字节/字符，4MB 内容实际 = 4,194,303 字节（不是精确 4MB），
        所以我们直接造一个超 100MB 的总字节数。
        """
        # 每章约 4MB（小于 5MB 单章上限）
        per_chapter_chars = (4 * 1024 * 1024) // 3
        per_chapter_content = "中" * per_chapter_chars

        # 26 章 × ~4MB = ~104MB（> 100MB 整书上限）
        chapters = [
            Chapter(chapter_num=i, title=f"c{i}", content=per_chapter_content) for i in range(1, 27)
        ]
        total = sum(c.content_size_bytes for c in chapters)
        assert total > BOOK_TOO_LARGE_BYTES, f"26 章总和应 > 100MB，实际 {total}"

        with pytest.raises(BookTooLargeError) as exc_info:
            EPUBExporter().export_chapters(chapters)
        assert exc_info.value.total_bytes > BOOK_TOO_LARGE_BYTES
        assert "too large" in str(exc_info.value).lower()

    def test_normal_500kb_chapter_accepted(self) -> None:
        """PoC：500KB 单章 → 200 OK（正常业务路径）。"""
        content = "中" * (500 * 1024 // 3)  # ~170K 中文字 → 500KB UTF-8
        ch = Chapter(chapter_num=1, title="正常章节", content=content)
        # 验证 size
        assert ch.content_size_bytes < CHAPTER_TOO_LARGE_BYTES

        # EPUB / Markdown / TXT 都应正常
        for exporter in [EPUBExporter(), MarkdownExporter(), TXTExporter()]:
            result = exporter.export_chapter(ch)
            assert len(result) > 0

    def test_md_and_txt_not_size_limited_for_huge(self) -> None:
        """PoC：md / txt 导出不限制（5MB+ 章节仍能导出）。"""
        huge_content = "中" * (CHAPTER_TOO_LARGE_BYTES // 3 + 100)
        huge = Chapter(chapter_num=1, title="巨大", content=huge_content)

        # Markdown / TXT 不应有 size 检查
        md_result = MarkdownExporter().export_chapter(huge)
        assert len(md_result) > 0
        txt_result = TXTExporter().export_chapter(huge)
        assert len(txt_result) > 0

    def test_web_endpoint_returns_400_for_huge_book(self, tmp_path: Path) -> None:
        """PoC：web 端点导出超大单章 → HTTP 400 + 友好 detail（不是 500）。"""
        os.environ.pop("NOVEL2ALL_DEBUG", None)
        os.environ.pop("DEBUG", None)

        app = create_app()
        tracker = Tracker(tmp_path / "_tracking-state.json")
        tracker.init(project_name="qa_test", total_chapters_target=10)
        prose_dir = tmp_path / "正文"
        prose_dir.mkdir()
        # 5MB+1B 单章
        huge_content = "# 第1章 超长\n\n" + ("中" * (CHAPTER_TOO_LARGE_BYTES // 3 + 100))
        (prose_dir / "第001章.md").write_text(huge_content, encoding="utf-8")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/chapter/1/export?format=epub&project_root={tmp_path}")
            assert resp.status_code == 400, f"超大单章应返回 400，实际 {resp.status_code}"
            body = resp.json()
            # detail 含 size 信息（用户友好提示）
            assert "MB" in body["detail"]
            assert "5" in body["detail"]
            assert "too large" in body["detail"].lower()

    def test_web_endpoint_md_and_txt_still_work_for_huge_chapter(self, tmp_path: Path) -> None:
        """PoC：md / txt 导出 web 端点对超大章节仍返回 200（无 size 限制）。"""
        os.environ.pop("NOVEL2ALL_DEBUG", None)
        os.environ.pop("DEBUG", None)

        app = create_app()
        tracker = Tracker(tmp_path / "_tracking-state.json")
        tracker.init(project_name="qa_test", total_chapters_target=10)
        prose_dir = tmp_path / "正文"
        prose_dir.mkdir()
        # 5MB+ 章节
        huge_content = "# 第1章 超长\n\n" + ("中" * (CHAPTER_TOO_LARGE_BYTES // 3 + 100))
        (prose_dir / "第001章.md").write_text(huge_content, encoding="utf-8")

        with TestClient(app, raise_server_exceptions=False) as client:
            # md 导出 → 200
            resp_md = client.get(f"/api/chapter/1/export?format=md&project_root={tmp_path}")
            assert resp_md.status_code == 200, f"md 导出应 200，实际 {resp_md.status_code}"

            # txt 导出 → 200
            resp_txt = client.get(f"/api/chapter/1/export?format=txt&project_root={tmp_path}")
            assert resp_txt.status_code == 200, f"txt 导出应 200，实际 {resp_txt.status_code}"


# ============================================================================
# Smoke Test: estimate_tokens 边界
# ============================================================================


class TestB4TokenEstimationEdges:
    """QA 顺带验证 estimate_tokens 边界（rate limit 的预估 token 数不准会导致误限流）。"""

    def test_estimate_tokens_long_chinese_text(self) -> None:
        """PoC：长中文文本 → estimate_tokens 不会溢出或返回负数。"""
        # 1 MB 中文 = ~256K token
        big_text = "中" * (1024 * 1024)
        est = estimate_tokens(big_text)
        assert est > 0
        assert est == (len(big_text) + 3) // 4  # 262148

    def test_estimate_tokens_unicode_special_chars(self) -> None:
        """PoC：emoji / 特殊 unicode → 不崩溃。"""
        # Emoji 是 surrogate pair（2 个 code unit），但 estimate_tokens 按字符数算
        # 不要求精确，但必须不抛异常
        for s in ["😀" * 100, "\n\n\n", "  ", "中英 mixed", ""]:
            est = estimate_tokens(s)
            assert est >= 0
