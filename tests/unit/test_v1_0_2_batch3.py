"""V1.0.2 Batch 3：5 个 P2-P3 bug 修复测试。

覆盖：
  B1  Cache key 缺 max_tokens / top_p / api_base（数据正确性 P1）
  B2  风格/设定更新后 cache 不失效（数据正确性 P1）
  B3  AdaptiveRouter record_run race condition（数据完整性 P1）
  B4  Per-user LLM rate limit（财务风险 P2）
  B5  EPUB 导出大文件 OOM（生产稳定性 P2）

每个 bug 测试独立 class + 多个 case（happy path + edge + integration）。
"""

from __future__ import annotations

import asyncio
import os
import threading
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
from novel2all.core.settings_hash import compute_settings_hash
from novel2all.web.app import create_app

# === Fixtures（项目根目录带 _tracking-state.json + 正文/第001章.md）===


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """V1.0.2 Batch 3：临时项目根目录（含 _tracking-state.json + 正文/）。"""
    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(
        project_name="测试项目",
        genre="玄幻",
        style_anchor="古风古韵",
        total_chapters_target=10,
    )
    prose_dir = tmp_path / "正文"
    prose_dir.mkdir(exist_ok=True)
    (prose_dir / "第001章.md").write_text(
        "# 第 1 章\n\n林雷觉醒血脉，苍茫镇为之震动。\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fresh_provider() -> LLMProvider:
    """V1.0.2 Batch 3：独立的 LLMProvider（含 MemoryLRUBackend + PromptCacheTracker）。"""
    config = LLMConfig(cache_enabled=True, default_model="mock/model")
    provider = LLMProvider.__new__(LLMProvider)
    provider.config = config
    provider._cache = MemoryLRUBackend(max_size=config.cache_max_size, ttl_seconds=0)
    provider._prompt_tracker = PromptCacheTracker()
    provider._resolve_model = lambda *, task, explicit_model: explicit_model or "mock/model"
    return provider


# ============================================================================
# B1: Cache key 缺 max_tokens / top_p / api_base
# ============================================================================


class TestB1CacheKeyExtended:
    """V1.0.2 B1：cache key 包含 max_tokens / top_p / api_base（修复数据正确性 bug）。

    背景：
    - 同 prompt + 不同 max_tokens（如 1000 vs 4000）的 LLM 实际返回不同（截断位置）
    - 但旧 cache key 只看 (model, sys_hash, user_hash, temperature) → 撞 cache
    - 同 prompt + 不同 api_base（同模型不同 endpoint）→ 撞 cache

    修复：_make_cache_key 接收 keyword-only 参数 max_tokens/top_p/api_base，
    缺省 None → 空字符串 hash（保证 backward compat）。
    """

    def test_same_prompt_different_max_tokens_different_keys(
        self, fresh_provider: LLMProvider
    ) -> None:
        """B1：max_tokens=1000 vs 4000 必须产生不同 cache key。"""
        key_1k = fresh_provider._make_cache_key("model", "sys", "user", 0.7, max_tokens=1000)
        key_4k = fresh_provider._make_cache_key("model", "sys", "user", 0.7, max_tokens=4000)
        assert key_1k != key_4k, "max_tokens 应区分 cache key"
        # 验证字段位置（_make_cache_key 返回 8-tuple）
        assert len(key_1k) == 8
        assert key_1k[4] == 1000
        assert key_4k[4] == 4000

    def test_same_prompt_different_top_p_different_keys(self, fresh_provider: LLMProvider) -> None:
        """B1：top_p=0.5 vs 0.9 必须产生不同 cache key。"""
        key_a = fresh_provider._make_cache_key("model", "sys", "user", 0.7, top_p=0.5)
        key_b = fresh_provider._make_cache_key("model", "sys", "user", 0.7, top_p=0.9)
        assert key_a != key_b, "top_p 应区分 cache key"
        assert key_a[5] == 0.5
        assert key_b[5] == 0.9

    def test_same_prompt_different_api_base_different_keys(
        self, fresh_provider: LLMProvider
    ) -> None:
        """B1：api_base="https://api.a.com" vs "https://api.b.com" 必须产生不同 cache key。"""
        key_a = fresh_provider._make_cache_key(
            "model", "sys", "user", 0.7, api_base="https://api.a.com"
        )
        key_b = fresh_provider._make_cache_key(
            "model", "sys", "user", 0.7, api_base="https://api.b.com"
        )
        assert key_a != key_b, "api_base 应区分 cache key"
        # 字段 6 是 api_base hash
        assert key_a[6] != key_b[6]

    def test_same_prompt_same_params_same_key(self, fresh_provider: LLMProvider) -> None:
        """B1：完全相同参数（含 max_tokens/top_p/api_base）必须产生相同 cache key。"""
        kwargs = {"max_tokens": 2000, "top_p": 0.7, "api_base": "https://api.x.com"}
        key1 = fresh_provider._make_cache_key("model", "sys", "user", 0.7, **kwargs)
        key2 = fresh_provider._make_cache_key("model", "sys", "user", 0.7, **kwargs)
        assert key1 == key2

    def test_backward_compat_4_positional_args(self, fresh_provider: LLMProvider) -> None:
        """B1：旧 4 positional args 调用方式必须仍工作（向后兼容）。"""
        # 旧测试用例：test_cache_key_uses_sha256 期待此签名仍可调用
        key1 = fresh_provider._make_cache_key("model", "system", "user", 0.7)
        key2 = fresh_provider._make_cache_key("model", "system", "user", 0.7)
        key3 = fresh_provider._make_cache_key("model", "different", "user", 0.7)
        key4 = fresh_provider._make_cache_key("model", None, "user", 0.7)
        key5 = fresh_provider._make_cache_key("model", "", "user", 0.7)

        assert key1 == key2
        assert key1 != key3  # 不同 system → 不同 key
        assert key4 == key5  # None 和 "" system 视为相同

    def test_max_tokens_none_normalized_to_zero(self, fresh_provider: LLMProvider) -> None:
        """B1：max_tokens=None 归一化为 0（占位），与显式 0 产生相同 key。"""
        key_none = fresh_provider._make_cache_key("model", "sys", "user", 0.7, max_tokens=None)
        key_zero = fresh_provider._make_cache_key("model", "sys", "user", 0.7, max_tokens=0)
        assert key_none == key_zero
        # 与省略参数（向后兼容路径）也一致
        key_omit = fresh_provider._make_cache_key("model", "sys", "user", 0.7)
        assert key_none == key_omit

    def test_cache_hit_miss_with_max_tokens_variation(self, fresh_provider: LLMProvider) -> None:
        """B1：complete() 用 max_tokens=1000 写 cache，max_tokens=4000 读 → cache miss。"""
        # 模拟 litellm.acompletion
        from types import SimpleNamespace

        import litellm

        async def fake_acompletion(**kwargs: Any) -> Any:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 1) max_tokens=1000 → cache miss → 调 API
            asyncio.run(fresh_provider.complete(prompt="p", model="mock/model", max_tokens=1000))
            assert fresh_provider._cache._misses == 1
            assert fresh_provider._cache._hits == 0

            # 2) max_tokens=4000 → cache miss（不同 key）→ 调 API
            asyncio.run(fresh_provider.complete(prompt="p", model="mock/model", max_tokens=4000))
            assert fresh_provider._cache._misses == 2
            assert fresh_provider._cache._hits == 0

            # 3) max_tokens=1000 再调 → cache hit
            asyncio.run(fresh_provider.complete(prompt="p", model="mock/model", max_tokens=1000))
            assert fresh_provider._cache._hits == 1
            assert fresh_provider._cache._misses == 2
        finally:
            litellm.acompletion = original

    def test_complete_passes_top_p_to_litellm(self, fresh_provider: LLMProvider) -> None:
        """B1：complete() top_p=0.8 应传给 litellm.acompletion kwargs。"""
        from types import SimpleNamespace

        import litellm

        captured_kwargs: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            asyncio.run(
                fresh_provider.complete(prompt="p", model="mock/model", top_p=0.8, max_tokens=100)
            )
            # top_p 应在 kwargs 中
            assert captured_kwargs.get("top_p") == 0.8
        finally:
            litellm.acompletion = original

    def test_complete_omits_top_p_when_none(self, fresh_provider: LLMProvider) -> None:
        """B1：complete() top_p=None 时不应传 top_p 给 litellm（用模型默认）。"""
        from types import SimpleNamespace

        import litellm

        captured_kwargs: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            asyncio.run(fresh_provider.complete(prompt="p", model="mock/model", max_tokens=100))
            # top_p 不应在 kwargs 中（None → 不传）
            assert "top_p" not in captured_kwargs
        finally:
            litellm.acompletion = original


# ============================================================================
# B2: 风格/设定更新后 cache 不失效
# ============================================================================


class TestB2SettingsHashInvalidation:
    """V1.0.2 B2：项目设定文件 hash 进入 cache key — 改文风/角色后旧 cache 自动失效。"""

    def test_compute_settings_hash_none(self) -> None:
        """B2：project_root=None → 16 个 '0'（向后兼容）。"""
        h = compute_settings_hash(None)
        assert h == "0" * 16

    def test_compute_settings_hash_empty_project(self, tmp_path: Path) -> None:
        """B2：项目目录为空 → 16 个 '0'（无任何设定文件）。"""
        h = compute_settings_hash(tmp_path)
        assert h == "0" * 16

    def test_compute_settings_hash_changes_on_chuangzuo_shezhi(self, tmp_path: Path) -> None:
        """B2：修改 创作设定.md 后 hash 变化。"""
        (tmp_path / "创作设定.md").write_text("玄幻风格", encoding="utf-8")
        h1 = compute_settings_hash(tmp_path)
        (tmp_path / "创作设定.md").write_text("都市风格", encoding="utf-8")
        h2 = compute_settings_hash(tmp_path)
        assert h1 != h2

    def test_compute_settings_hash_changes_on_wenfeng(self, tmp_path: Path) -> None:
        """B2：修改 设定/文风.md 后 hash 变化。"""
        (tmp_path / "设定").mkdir()
        (tmp_path / "设定" / "文风.md").write_text("古风古韵", encoding="utf-8")
        h1 = compute_settings_hash(tmp_path)
        (tmp_path / "设定" / "文风.md").write_text("现代白话", encoding="utf-8")
        h2 = compute_settings_hash(tmp_path)
        assert h1 != h2

    def test_compute_settings_hash_changes_on_role_file(self, tmp_path: Path) -> None:
        """B2：修改 设定/角色/*.md 后 hash 变化。"""
        (tmp_path / "设定" / "角色").mkdir(parents=True)
        (tmp_path / "设定" / "角色" / "林雷.md").write_text("性格：坚毅", encoding="utf-8")
        h1 = compute_settings_hash(tmp_path)
        (tmp_path / "设定" / "角色" / "林雷.md").write_text("性格：柔弱", encoding="utf-8")
        h2 = compute_settings_hash(tmp_path)
        assert h1 != h2

    def test_compute_settings_hash_stable_for_same_content(self, tmp_path: Path) -> None:
        """B2：相同内容 → 相同 hash（可重复性）。"""
        (tmp_path / "创作设定.md").write_text("玄幻", encoding="utf-8")
        h1 = compute_settings_hash(tmp_path)
        h2 = compute_settings_hash(tmp_path)
        assert h1 == h2

    def test_compute_settings_hash_role_files_sorted(self, tmp_path: Path) -> None:
        """B2：角色文件按文件名排序后 hash（glob 顺序不确定但要稳定）。"""
        (tmp_path / "设定" / "角色").mkdir(parents=True)
        # 不同 glob 顺序：先创 A 再创 B
        (tmp_path / "设定" / "角色" / "A.md").write_text("content_A", encoding="utf-8")
        (tmp_path / "设定" / "角色" / "B.md").write_text("content_B", encoding="utf-8")
        h1 = compute_settings_hash(tmp_path)

        # 删除 A 再创建（内容相同）→ 应产生相同 hash
        (tmp_path / "设定" / "角色" / "A.md").unlink()
        (tmp_path / "设定" / "角色" / "A.md").write_text("content_A", encoding="utf-8")
        h2 = compute_settings_hash(tmp_path)
        assert h1 == h2

    def test_settings_hash_in_cache_key_differentiates(
        self, fresh_provider: LLMProvider, tmp_path: Path
    ) -> None:
        """B2：不同 settings_hash 产生不同 cache key。"""
        (tmp_path / "创作设定.md").write_text("玄幻风格", encoding="utf-8")
        h1 = compute_settings_hash(tmp_path)
        (tmp_path / "创作设定.md").write_text("都市风格", encoding="utf-8")
        h2 = compute_settings_hash(tmp_path)
        assert h1 != h2

        key1 = fresh_provider._make_cache_key("model", "sys", "user", 0.7, settings_hash=h1)
        key2 = fresh_provider._make_cache_key("model", "sys", "user", 0.7, settings_hash=h2)
        assert key1 != key2

    def test_complete_with_project_root_uses_settings_hash(
        self, fresh_provider: LLMProvider, tmp_project: Path
    ) -> None:
        """B2 集成：complete(project_root=...) 后改文风 → 旧 cache 自动失效。"""
        from types import SimpleNamespace

        import litellm

        call_count = [0]

        async def fake_acompletion(**kwargs: Any) -> Any:
            call_count[0] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R_{call_count[0]}"))]
            )

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 1) 写 cache（基于当前设定）
            asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_project, max_tokens=100
                )
            )
            assert call_count[0] == 1
            assert fresh_provider._cache._misses == 1

            # 2) 同一调用 → cache hit
            asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_project, max_tokens=100
                )
            )
            assert call_count[0] == 1
            assert fresh_provider._cache._hits == 1

            # 3) 修改 创作设定.md → cache 应 miss
            (tmp_project / "创作设定.md").write_text("新风格", encoding="utf-8")
            asyncio.run(
                fresh_provider.complete(
                    prompt="p", model="mock/model", project_root=tmp_project, max_tokens=100
                )
            )
            assert call_count[0] == 2  # 新调用一次
            assert fresh_provider._cache._misses == 2  # miss 计数 +1
            assert fresh_provider._cache._hits == 1  # hit 计数不变
        finally:
            litellm.acompletion = original


# ============================================================================
# B3: AdaptiveRouter record_run race condition
# ============================================================================


class TestB3AdaptiveRouterAtomic:
    """V1.0.2 B3：record_run 用 INSERT ... ON CONFLICT DO UPDATE 原子聚合，消除 race condition。"""

    def test_record_run_increments_samples(self, tmp_path: Path) -> None:
        """B3：record_run 后 samples = 1。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1000)
        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 1

    def test_concurrent_record_runs_no_loss(self, tmp_path: Path) -> None:
        """B3：10 线程 × 20 次 = 200 次 record_run → samples 必须是 200（不丢计数）。

        这是 V1.0.2 修复的核心断言：旧版 read-modify-write 在并发下
        会因 SELECT/UPDATE 间被覆盖而丢计数。
        """
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        def worker() -> None:
            for _ in range(20):
                router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1000)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 200, f"race condition lost samples: got {stats.samples}"
        # 平均 latency 应是 1000（每次都传 1000）
        assert stats.avg_latency_ms == 1000.0
        # 全部 success → success_rate = 1.0
        assert stats.success_rate == 1.0

    def test_concurrent_mixed_models(self, tmp_path: Path) -> None:
        """B3：多线程多模型并发 → 每个 model 各自 samples 不丢。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        def worker(model_name: str) -> None:
            for _ in range(10):
                router.record_run(TaskType.WRITING, model_name, success=True, latency_ms=500)

        threads = []
        for m in ["m1", "m2", "m3"]:
            for _ in range(3):
                threads.append(threading.Thread(target=worker, args=(m,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for m in ["m1", "m2", "m3"]:
            stats = router.get_stats(TaskType.WRITING, m)
            assert stats is not None
            # 3 线程 × 10 次 = 30
            assert stats.samples == 30, f"{m}: got {stats.samples}"

    def test_avg_latency_correct_after_concurrent(self, tmp_path: Path) -> None:
        """B3：并发 record_run 后 avg_latency 应等于真实平均。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        def worker(latency: int) -> None:
            for _ in range(10):
                router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=latency)

        # 5 线程 × 10 次 = 50 次，latency 分别为 100/200/300/400/500 → 平均 300
        threads = [
            threading.Thread(target=worker, args=(latency,))
            for latency in (100, 200, 300, 400, 500)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 50
        assert stats.avg_latency_ms == pytest.approx(300.0, abs=0.1)

    def test_success_rate_correct(self, tmp_path: Path) -> None:
        """B3：success_rate 正确反映 success/fail 比例。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")

        # 50% 成功
        for _ in range(50):
            router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1000)
        for _ in range(50):
            router.record_run(TaskType.WRITING, "m1", success=False, latency_ms=2000)

        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.samples == 100
        assert stats.success_rate == 0.5

    def test_quality_score_aggregation(self, tmp_path: Path) -> None:
        """B3：quality_score 累加正确（avg_quality = sum / samples）。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")
        for score in (8.0, 9.0, 7.0):
            router.record_run(
                TaskType.WRITING, "m1", success=True, latency_ms=1000, quality_score=score
            )
        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats is not None
        assert stats.avg_quality == pytest.approx(8.0, abs=0.01)

    def test_unique_index_exists(self, tmp_path: Path) -> None:
        """B3：idx_model_runs_task_model UNIQUE INDEX 应在 schema 中。"""
        router = AdaptiveRouter(db_path=tmp_path / "r.db")
        import sqlite3

        with sqlite3.connect(str(router.db_path)) as conn:
            cur = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND name='idx_model_runs_task_model'"
            )
            row = cur.fetchone()
            assert row is not None
            assert "UNIQUE" in row[1]


# ============================================================================
# B4: Per-user LLM rate limit
# ============================================================================


class TestB4LLMRateLimit:
    """V1.0.2 B4：per-user LLM rate limit（按 token 估算）。"""

    def test_basic_check(self) -> None:
        """B4：check() 正确累计并返回剩余 token。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=1000)
        remaining = limiter.check(user_id=1, est_tokens=200)
        assert remaining == 800
        remaining = limiter.check(user_id=1, est_tokens=300)
        assert remaining == 500

    def test_exceed_quota_raises(self) -> None:
        """B4：超 quota → raise LLMRateLimitExceeded（含完整错误信息）。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=1000)
        limiter.check(user_id=1, est_tokens=500)
        limiter.check(user_id=1, est_tokens=300)
        # 此时用了 800，剩 200；请求 300 → 超额
        with pytest.raises(LLMRateLimitExceeded) as exc_info:
            limiter.check(user_id=1, est_tokens=300)
        exc = exc_info.value
        assert exc.user_id == 1
        assert exc.used == 800
        assert exc.limit == 1000
        assert exc.requested == 300
        assert "user 1" in str(exc)
        assert "800/1000" in str(exc)

    def test_different_users_independent_quotas(self) -> None:
        """B4：不同用户独立 quota。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=1000)
        limiter.check(user_id=1, est_tokens=900)
        # user 1 剩 100，user 2 仍可满 quota
        remaining = limiter.check(user_id=2, est_tokens=900)
        assert remaining == 100

    def test_get_used(self) -> None:
        """B4：get_used() 返回当前 1h 用量。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=1000)
        limiter.check(user_id=1, est_tokens=200)
        limiter.check(user_id=1, est_tokens=300)
        assert limiter.get_used(user_id=1) == 500
        # 未调用的用户 → 0
        assert limiter.get_used(user_id=999) == 0

    def test_reset_specific_user(self) -> None:
        """B4：reset(user_id) 只清该用户。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=1000)
        limiter.check(user_id=1, est_tokens=500)
        limiter.check(user_id=2, est_tokens=500)
        limiter.reset(user_id=1)
        assert limiter.get_used(user_id=1) == 0
        assert limiter.get_used(user_id=2) == 500

    def test_reset_all_users(self) -> None:
        """B4：reset() 清所有用户。"""
        limiter = LLMRateLimiter(max_tokens_per_hour=1000)
        limiter.check(user_id=1, est_tokens=500)
        limiter.check(user_id=2, est_tokens=500)
        limiter.reset()
        assert limiter.get_used(user_id=1) == 0
        assert limiter.get_used(user_id=2) == 0

    def test_env_var_configuration(self) -> None:
        """B4：LLM_RATE_LIMIT_PER_HOUR 环境变量覆盖默认。"""
        os.environ["LLM_RATE_LIMIT_PER_HOUR"] = "5000"
        try:
            limiter = LLMRateLimiter()
            assert limiter.max_tokens_per_hour == 5000
        finally:
            del os.environ["LLM_RATE_LIMIT_PER_HOUR"]

    def test_estimate_tokens(self) -> None:
        """B4：estimate_tokens 启发式（4 字符/token）。"""
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0
        assert estimate_tokens("hi") == 1  # 2 字符 → 1 token
        assert estimate_tokens("hello world") == 3  # 11 字符 → 3 token
        assert estimate_tokens("中" * 100) == 25  # 100 字符 → 25 token

    def test_negative_est_tokens_raises(self) -> None:
        """B4：est_tokens < 0 → ValueError。"""
        limiter = LLMRateLimiter()
        with pytest.raises(ValueError):
            limiter.check(user_id=1, est_tokens=-1)

    def test_global_limiter_singleton(self) -> None:
        """B4：get_global_llm_rate_limiter() 返回单例。"""
        reset_global_llm_rate_limiter()
        g1 = get_global_llm_rate_limiter()
        g2 = get_global_llm_rate_limiter()
        assert g1 is g2

    @pytest.mark.asyncio
    async def test_complete_blocks_when_user_exceeds_quota(self, tmp_path: Path) -> None:
        """B4 集成：complete(user_id=...) → 超额时抛 LLMRateLimitExceeded。"""
        from types import SimpleNamespace

        import litellm

        reset_global_llm_rate_limiter()
        # 强制一个低 limit
        os.environ["LLM_RATE_LIMIT_PER_HOUR"] = "500"
        try:
            limiter = get_global_llm_rate_limiter()
            assert limiter.max_tokens_per_hour == 500

            config = LLMConfig(cache_enabled=False, default_model="mock/model")
            provider = LLMProvider.__new__(LLMProvider)
            provider.config = config
            provider._cache = MemoryLRUBackend(max_size=config.cache_max_size, ttl_seconds=0)
            provider._prompt_tracker = PromptCacheTracker()
            provider._resolve_model = lambda *, task, explicit_model: explicit_model or "mock/model"

            # Patch litellm.acompletion 防止真调用
            async def fake_acompletion(**kwargs: Any) -> Any:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="R"))]
                )

            original = litellm.acompletion
            litellm.acompletion = fake_acompletion
            try:
                # 调一次占用 ~1 + 100 = 101 tokens
                await provider.complete(
                    prompt="hello", model="mock/model", user_id=42, max_tokens=100
                )
                # 第二次 max_tokens=500 → 估算 ~1 + 500 = 501 → 超 500 配额
                with pytest.raises(LLMRateLimitExceeded) as exc_info:
                    await provider.complete(
                        prompt="hello", model="mock/model", user_id=42, max_tokens=500
                    )
                assert exc_info.value.user_id == 42
            finally:
                litellm.acompletion = original
        finally:
            del os.environ["LLM_RATE_LIMIT_PER_HOUR"]
            reset_global_llm_rate_limiter()

    def test_complete_user_id_none_skips_rate_limit(self, fresh_provider: LLMProvider) -> None:
        """B4 向后兼容：user_id=None → 不限流（CLI/测试场景）。"""
        from types import SimpleNamespace

        import litellm

        async def fake_acompletion(**kwargs: Any) -> Any:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 不传 user_id → 不限流（即使 token 估算超过默认值也无影响）
            for _ in range(100):
                asyncio.run(
                    fresh_provider.complete(
                        prompt="x" * 100000, model="mock/model", max_tokens=4096
                    )
                )
            # 全 100 次都成功（不限流）
        finally:
            litellm.acompletion = original


# ============================================================================
# B5: EPUB 导出大文件 OOM
# ============================================================================


class TestB5EpubOomPrevention:
    """V1.0.2 B5：EPUB 导出大文件 OOM 防护（fail-fast）。"""

    def test_small_chapter_accepted(self) -> None:
        """B5：< 5 MB 单章可正常导出。"""
        small = Chapter(chapter_num=1, title="小章", content="正常内容")
        result = EPUBExporter().export_chapter(small)
        assert len(result) > 0

    def test_huge_single_chapter_rejected(self) -> None:
        """B5：> 5 MB 单章 → ChapterTooLargeError。"""
        huge_content = "中" * (CHAPTER_TOO_LARGE_BYTES // 3 + 100)
        huge = Chapter(chapter_num=99, title="巨大", content=huge_content)
        assert huge.content_size_bytes > CHAPTER_TOO_LARGE_BYTES

        with pytest.raises(ChapterTooLargeError) as exc_info:
            EPUBExporter().export_chapter(huge)
        exc = exc_info.value
        assert exc.chapter_num == 99
        assert exc.size_bytes > CHAPTER_TOO_LARGE_BYTES
        assert "too large" in str(exc)

    def test_huge_chapter_in_list_rejected_fail_fast(self) -> None:
        """B5：含 huge chapter 的 list → fail-fast on first oversize。"""
        small = Chapter(chapter_num=1, title="小", content="x")
        huge_content = "中" * (CHAPTER_TOO_LARGE_BYTES // 3 + 100)
        huge = Chapter(chapter_num=2, title="巨大", content=huge_content)
        chapters = [small, huge, small]

        with pytest.raises(ChapterTooLargeError):
            EPUBExporter().export_chapters(chapters)

    def test_total_book_size_limit(self) -> None:
        """B5：多章总和 > 100 MB → BookTooLargeError。"""
        # 每章 ~4MB（< 5MB 单章上限），26 章 × 4MB ≈ 104MB（> 100MB 总限）
        medium_content = "中" * (4 * 1024 * 1024 // 3)
        chapters = [
            Chapter(chapter_num=i, title=f"c{i}", content=medium_content) for i in range(1, 27)
        ]
        total = sum(c.content_size_bytes for c in chapters)
        assert total > BOOK_TOO_LARGE_BYTES

        with pytest.raises(BookTooLargeError) as exc_info:
            EPUBExporter().export_chapters(chapters)
        exc = exc_info.value
        assert exc.total_bytes > BOOK_TOO_LARGE_BYTES
        assert "too large" in str(exc)

    def test_empty_chapter_list_rejected(self) -> None:
        """B5：空 chapter list → ValueError。"""
        with pytest.raises(ValueError):
            EPUBExporter().export_chapters([])

    def test_content_size_bytes_utf8_accurate(self) -> None:
        """B5：content_size_bytes 是 UTF-8 编码字节数（与 EPUB 占用一致）。"""
        # 中文 UTF-8 = 3 bytes/字符
        ch = Chapter(chapter_num=1, title="t", content="中" * 100)
        assert ch.content_size_bytes == 300
        # ASCII = 1 byte/字符
        ch2 = Chapter(chapter_num=1, title="t", content="a" * 100)
        assert ch2.content_size_bytes == 100

    def test_constants_match_spec(self) -> None:
        """B5：CHAPTER_TOO_LARGE_BYTES = 5 MB, BOOK_TOO_LARGE_BYTES = 100 MB。"""
        assert CHAPTER_TOO_LARGE_BYTES == 5 * 1024 * 1024
        assert BOOK_TOO_LARGE_BYTES == 100 * 1024 * 1024

    def test_web_endpoint_returns_400_for_huge_chapter(self, tmp_path: Path) -> None:
        """B5 集成：web /api/chapter/{n}/export?format=epub → 400 + 友好 detail。"""
        os.environ.pop("NOVEL2ALL_DEBUG", None)
        os.environ.pop("DEBUG", None)
        try:
            app = create_app()
            tracker = Tracker(tmp_path / "_tracking-state.json")
            tracker.init(project_name="test", total_chapters_target=10)
            prose_dir = tmp_path / "正文"
            prose_dir.mkdir()
            huge_content = "# 第1章 超长\n\n" + ("中" * (5 * 1024 * 1024 // 3 + 100))
            (prose_dir / "第001章.md").write_text(huge_content, encoding="utf-8")

            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(f"/api/chapter/1/export?format=epub&project_root={tmp_path}")
                assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
                body = resp.json()
                assert "too large" in body["detail"]
                # 含 size 信息
                assert "5" in body["detail"]
        finally:
            pass

    def test_md_and_txt_export_not_size_limited(self) -> None:
        """B5：Markdown / TXT exporter 不受 5 MB 单章限制（仅 EPUB 受限）。"""
        huge_content = "中" * (CHAPTER_TOO_LARGE_BYTES // 3 + 100)
        huge = Chapter(chapter_num=1, title="巨大", content=huge_content)
        # MarkdownExporter / TXTExporter 不应有 size 检查（设计：md/txt 流式无 OOM 风险）
        md_result = MarkdownExporter().export_chapter(huge)
        assert len(md_result) > CHAPTER_TOO_LARGE_BYTES  # 没拒绝
        txt_result = TXTExporter().export_chapter(huge)
        assert len(txt_result) > 0  # 没拒绝
