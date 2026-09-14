"""V0.30.6 C3：自适应路由测试。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from novel2all.core.adaptive_router import (
    AdaptiveRouter,
    AdaptiveStrategy,
    ModelStats,
)
from novel2all.core.provider_router import TaskType

# === Fixtures ===


@pytest.fixture
def router(tmp_path: Path) -> AdaptiveRouter:
    """V0.30.6 C3：临时 SQLite AdaptiveRouter。"""
    return AdaptiveRouter(
        default_model="deepseek/deepseek-flash",
        db_path=tmp_path / "routing.db",
    )


# === Test 1: Recording ===


class TestRecording:
    """V0.30.6 C3：record_run 记录 LLM 调用结果。"""

    def test_record_run_increments_db(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：record_run 后 get_stats 有数据。"""
        router.record_run(
            TaskType.WRITING, "deepseek/deepseek-flash", success=True, latency_ms=3000
        )
        stats = router.get_stats(TaskType.WRITING, "deepseek/deepseek-flash")
        assert stats is not None
        assert stats.samples == 1

    def test_record_multiple_runs_aggregates(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：多次 record 聚合统计。"""
        for i in range(5):
            router.record_run(
                TaskType.WRITING,
                "deepseek/deepseek-flash",
                success=i % 2 == 0,
                latency_ms=3000 + i * 100,
            )
        stats = router.get_stats(TaskType.WRITING, "deepseek/deepseek-flash")
        assert stats.samples == 5
        # 5 次中 3 次成功（i=0,2,4）
        assert stats.success_rate == 0.6

    def test_record_quality_score_aggregates(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：quality_score 平均计算。"""
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=3000, quality_score=8.0)
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=3000, quality_score=9.0)
        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats.avg_quality == 8.5

    def test_record_without_quality_uses_default(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：无 quality_score → avg_quality = 5.0（中位数）。"""
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=3000)
        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats.avg_quality == 5.0


# === Test 2: Statistics ===


class TestStatistics:
    """V0.30.6 C3：get_stats 计算正确。"""

    def test_get_stats_no_data_returns_none(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：无数据 → None。"""
        assert router.get_stats(TaskType.WRITING, "nobody") is None

    def test_get_stats_window_size(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：window_size 限制只取最近 N 次。"""
        # 写 100 次，但 window_size=10
        router.window_size = 10
        for i in range(100):
            success = i >= 50  # 后 50 次成功
            router.record_run(TaskType.WRITING, "m1", success=success, latency_ms=3000)
        stats = router.get_stats(TaskType.WRITING, "m1")
        assert stats.samples == 10  # 只取最近 10 次
        assert stats.success_rate == 1.0  # 后 10 次都成功

    def test_get_all_stats_for_task(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：列 task 下所有模型的统计。"""
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=3000, quality_score=8.0)
        router.record_run(TaskType.WRITING, "m2", success=True, latency_ms=4000, quality_score=7.0)
        router.record_run(TaskType.SUMMARIZATION, "m1", success=True, latency_ms=1000)  # 不同 task

        stats = router.get_all_stats_for_task(TaskType.WRITING)
        assert "m1" in stats
        assert "m2" in stats
        assert len(stats) == 2


# === Test 3: Selection ===


class TestSelection:
    """V0.30.6 C3：select() 选最佳模型。"""

    def test_cold_start_returns_default(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：无数据 → default_model。"""
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-flash"

    def test_cold_start_below_min_samples_returns_default(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：样本 < min_samples → default。"""
        # 只记 3 次（min_samples=5）
        for _ in range(3):
            router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=2000)
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-flash"

    def test_above_min_samples_picks_best(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：≥ min_samples → 选最高分。"""
        # m1: 慢 + 高质量
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "m1", success=True, latency_ms=5000, quality_score=9.0
            )
        # m2: 快 + 低质量
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "m2", success=True, latency_ms=1000, quality_score=6.0
            )

        # BEST_AVG: 综合分 = 0.5*1.0 + 0.2*speed + 0.3*quality
        # m1: 0.5*1.0 + 0.2*(1-5000/30000) + 0.3*0.9 = 0.5 + 0.167 + 0.27 = 0.937
        # m2: 0.5*1.0 + 0.2*(1-1000/30000) + 0.3*0.6 = 0.5 + 0.193 + 0.18 = 0.873
        # m1 略胜
        assert router.select(TaskType.WRITING) == "m1"

    def test_strategy_best_speed_picks_fastest(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：BEST_SPEED 策略选最快模型。"""
        router.strategy = AdaptiveStrategy.BEST_SPEED
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "slow_model", success=True, latency_ms=10000, quality_score=10.0
            )
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "fast_model", success=True, latency_ms=1000, quality_score=5.0
            )
        assert router.select(TaskType.WRITING) == "fast_model"

    def test_strategy_best_quality_picks_highest(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：BEST_QUALITY 策略选最高质量。"""
        router.strategy = AdaptiveStrategy.BEST_QUALITY
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "low_q", success=True, latency_ms=1000, quality_score=5.0
            )
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "high_q", success=True, latency_ms=10000, quality_score=9.5
            )
        assert router.select(TaskType.WRITING) == "high_q"

    def test_strategy_best_success_picks_most_reliable(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：BEST_SUCCESS 策略选最高成功率。"""
        router.strategy = AdaptiveStrategy.BEST_SUCCESS
        # m1: 50% 成功
        for i in range(10):
            router.record_run(TaskType.WRITING, "m1", success=i % 2 == 0, latency_ms=1000)
        # m2: 100% 成功
        for _ in range(10):
            router.record_run(TaskType.WRITING, "m2", success=True, latency_ms=5000)
        assert router.select(TaskType.WRITING) == "m2"


# === Test 4: Integration with ModelRouter ===


class TestIntegration:
    """V0.30.6 C3：与 V0.23 ModelRouter 集成测试。"""

    def test_adaptive_select_replaces_static_routes(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：select() 返回的模型可用于覆盖 V0.23 路由。"""
        # 假设 V0.23 默认 WRITING → deepseek/deepseek-chat
        # 但历史数据显示 deepseek/deepseek-flash 更好
        for _ in range(10):
            router.record_run(
                TaskType.WRITING,
                "deepseek/deepseek-flash",
                success=True,
                latency_ms=2000,
                quality_score=9.0,
            )
        # AdaptiveRouter 选 flash，V0.23 路由会选 chat → flash 胜
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-flash"

    def test_per_task_independent_selection(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：不同 task 独立选择。"""
        # WRITING: m1 优
        for _ in range(10):
            router.record_run(
                TaskType.WRITING, "m1", success=True, latency_ms=1000, quality_score=9.0
            )
            router.record_run(
                TaskType.WRITING, "m2", success=True, latency_ms=5000, quality_score=6.0
            )
        # SUMMARIZATION: m2 优
        for _ in range(10):
            router.record_run(
                TaskType.SUMMARIZATION, "m2", success=True, latency_ms=2000, quality_score=9.0
            )
            router.record_run(
                TaskType.SUMMARIZATION, "m1", success=True, latency_ms=4000, quality_score=5.0
            )

        assert router.select(TaskType.WRITING) == "m1"
        assert router.select(TaskType.SUMMARIZATION) == "m2"


# === Test 5: Maintenance ===


class TestMaintenance:
    """V0.30.6 C3：DB 维护（清理 / reset）。"""

    def test_cleanup_old_runs(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：清理 90 天前的旧 runs。"""
        # 写 1 条 records
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1000)

        # 手动改时间戳为 100 天前
        import sqlite3

        with sqlite3.connect(str(router.db_path)) as conn:
            conn.execute("UPDATE model_runs SET ts = ?", (time.time() - 100 * 86400,))

        deleted = router.cleanup_old_runs(max_age_seconds=90 * 86400)
        assert deleted == 1

        # 再查：应无数据
        assert router.get_stats(TaskType.WRITING, "m1") is None

    def test_clear_removes_all(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：clear() 清空所有历史。"""
        router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1000)
        router.record_run(TaskType.WRITING, "m2", success=True, latency_ms=1000)

        router.clear()
        assert router.get_stats(TaskType.WRITING, "m1") is None
        assert router.get_stats(TaskType.WRITING, "m2") is None

    def test_clear_resets_cold_start(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：clear 后 select 回到 cold-start（默认模型）。"""
        for _ in range(10):
            router.record_run(TaskType.WRITING, "m1", success=True, latency_ms=1000)
        assert router.select(TaskType.WRITING) == "m1"

        router.clear()
        # 清空后 → cold-start → default_model
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-flash"


# === Test 6: Scoring Functions ===


class TestScoring:
    """V0.30.6 C3：_compute_score 各种策略。"""

    def test_score_best_avg_balanced(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：best_avg 加权综合分。"""
        router.strategy = AdaptiveStrategy.BEST_AVG
        # 100% 成功 + 极快 + 满分质量
        score = router._compute_score(success_rate=1.0, avg_latency_ms=0, avg_quality=10.0)
        # w1*1.0 + w2*1.0 + w3*1.0 = 1.0
        assert score == pytest.approx(1.0)

    def test_score_best_avg_low_quality(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：低质量拉低综合分。"""
        router.strategy = AdaptiveStrategy.BEST_AVG
        score = router._compute_score(success_rate=1.0, avg_latency_ms=1000, avg_quality=2.0)
        # 0.5*1.0 + 0.2*(1-1000/30000) + 0.3*0.2 = 0.5 + 0.193 + 0.06 = 0.753
        assert 0.7 < score < 0.8

    def test_score_best_speed_extreme(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：BEST_SPEED 极端值。"""
        router.strategy = AdaptiveStrategy.BEST_SPEED
        # 0ms → 1.0
        assert router._compute_score(1.0, 0, 0) == 1.0
        # 30s → 0.0
        assert router._compute_score(1.0, 30000, 0) == 0.0
        # 60s → 0.0（不会负数）
        assert router._compute_score(1.0, 60000, 0) == 0.0

    def test_score_best_quality_normalized(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：BEST_QUALITY 归一化到 0-1。"""
        router.strategy = AdaptiveStrategy.BEST_QUALITY
        assert router._compute_score(1.0, 1000, 0) == 0.0
        assert router._compute_score(1.0, 1000, 5) == 0.5
        assert router._compute_score(1.0, 1000, 10) == 1.0


# === Test 7: ModelStats.to_dict ===


class TestModelStats:
    """V0.30.6 C3：ModelStats 序列化。"""

    def test_to_dict_fields(self) -> None:
        """V0.30.6 C3：to_dict 含所有字段。"""
        stats = ModelStats(
            model="m1",
            task=TaskType.WRITING,
            samples=10,
            success_rate=0.9,
            avg_latency_ms=2500.0,
            avg_quality=8.5,
            score=0.85,
        )
        d = stats.to_dict()
        assert d["model"] == "m1"
        assert d["task"] == "writing"
        assert d["samples"] == 10
        assert d["success_rate"] == 0.9
        assert d["avg_quality"] == 8.5
        assert d["score"] == 0.85


# === Test 8: Concurrency ===


class TestConcurrency:
    """V0.30.6 C3：并发安全。"""

    def test_concurrent_record_runs(self, router: AdaptiveRouter) -> None:
        """V0.30.6 C3：多线程并发 record_run 无丢失（threading.Lock 保护）。"""
        import threading

        def record(i: int) -> None:
            for _ in range(10):
                router.record_run(TaskType.WRITING, f"m{i % 3}", success=True, latency_ms=1000)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 每个模型应至少被记录 5*10/3 ≈ 17 次（实际不均）
        stats_m0 = router.get_stats(TaskType.WRITING, "m0")
        stats_m1 = router.get_stats(TaskType.WRITING, "m1")
        stats_m2 = router.get_stats(TaskType.WRITING, "m2")
        assert (stats_m0.samples + stats_m1.samples + stats_m2.samples) == 50
