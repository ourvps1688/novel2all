"""V0.30.6 C3 收尾：AdaptiveRouter 集成到 LLMProvider._resolve_model 测试。"""

from __future__ import annotations

from pathlib import Path

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.adaptive_router import AdaptiveStrategy
from novel2all.core.provider_router import TaskType

# === Test 1: 初始化 ===

class TestAdaptiveRouterInit:
    """V0.30.6 C3 收尾：init_adaptive_router + 字段。"""

    def test_provider_has_adaptive_router_field(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：LLMProvider 有 _adaptive_router 字段（默认 None）。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        assert hasattr(provider, "_adaptive_router")
        assert provider._adaptive_router is None  # 默认未启用

    def test_init_adaptive_router_creates_router(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：init_adaptive_router() 创建 AdaptiveRouter。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        provider.init_adaptive_router(db_path=tmp_path / "router.db")
        assert provider._adaptive_router is not None

    def test_init_adaptive_router_custom_params(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：init_adaptive_router() 接受自定义参数。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        provider.init_adaptive_router(
            db_path=tmp_path / "router.db",
            default_model="deepseek/deepseek-flash",
            strategy=AdaptiveStrategy.BEST_SPEED,
            min_samples=10,
            window_size=100,
        )
        assert provider._adaptive_router.strategy == AdaptiveStrategy.BEST_SPEED
        assert provider._adaptive_router.min_samples == 10
        assert provider._adaptive_router.window_size == 100


# === Test 2: record_adaptive_run ===

class TestRecordAdaptiveRun:
    """V0.30.6 C3 收尾：record_adaptive_run 集成方法。"""

    def test_record_adaptive_run_with_tasktype(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：record_adaptive_run() 接受 TaskType。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        provider.init_adaptive_router(db_path=tmp_path / "router.db")
        provider._record_adaptive_run(
            TaskType.WRITING, "deepseek/deepseek-flash",
            success=True, latency_ms=3000, quality_score=8.0,
        )
        stats = provider._adaptive_router.get_stats(TaskType.WRITING, "deepseek/deepseek-flash")
        assert stats is not None
        assert stats.samples == 1

    def test_record_adaptive_run_skips_string_task(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：record_adaptive_run() 跳过非 TaskType 输入。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        provider.init_adaptive_router(db_path=tmp_path / "router.db")
        provider._record_adaptive_run(
            "writing", "deepseek/deepseek-flash",  # 字符串 task
            success=True, latency_ms=3000,
        )
        # 不应 crash，也不应记录
        stats = provider._adaptive_router.get_stats(TaskType.WRITING, "deepseek/deepseek-flash")
        assert stats is None  # 无记录

    def test_record_adaptive_run_silent_when_not_initialized(self) -> None:
        """V0.30.6 C3 收尾：未启用 AdaptiveRouter → 静默跳过（不 crash）。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        # 不调用 init_adaptive_router
        provider._record_adaptive_run(
            TaskType.WRITING, "m1",
            success=True, latency_ms=1000,
        )
        # 不应 crash，无记录（_adaptive_router=None）
        assert provider._adaptive_router is None


# === Test 3: _resolve_model 集成 ===

class TestResolveModelWithAdaptive:
    """V0.30.6 C3 收尾：_resolve_model 优先用 AdaptiveRouter。"""

    def test_resolve_without_router_falls_back_to_v23(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：未启用 AdaptiveRouter → fall back to ModelRouter。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        # _adaptive_router = None（默认）
        model = provider._resolve_model(task=TaskType.WRITING)
        # V0.23 默认：WRITING → deepseek/deepseek-flash
        assert "deepseek" in model

    def test_resolve_with_router_cold_start_uses_default(
        self, tmp_path: Path
    ) -> None:
        """V0.30.6 C3 收尾：启用 AdaptiveRouter 但无数据 → cold-start default。"""
        provider = LLMProvider(
            LLMConfig(cache_enabled=False, default_model="deepseek/deepseek-flash")
        )
        provider.init_adaptive_router(db_path=tmp_path / "router.db")
        model = provider._resolve_model(task=TaskType.WRITING)
        assert model == "deepseek/deepseek-flash"

    def test_resolve_with_data_picks_best(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：有历史数据 → 选最高分模型。"""
        provider = LLMProvider(
            LLMConfig(cache_enabled=False, default_model="deepseek/deepseek-flash")
        )
        provider.init_adaptive_router(db_path=tmp_path / "router.db", min_samples=5)

        # m1: 快 + 高质量
        for _ in range(10):
            provider._record_adaptive_run(
                TaskType.WRITING, "m1",
                success=True, latency_ms=2000, quality_score=9.0,
            )
        # m2: 慢 + 低质量
        for _ in range(10):
            provider._record_adaptive_run(
                TaskType.WRITING, "m2",
                success=True, latency_ms=10000, quality_score=5.0,
            )

        model = provider._resolve_model(task=TaskType.WRITING)
        assert model == "m1"

    def test_explicit_model_overrides_adaptive(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：显式 model= 参数绕过 AdaptiveRouter。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        provider.init_adaptive_router(db_path=tmp_path / "router.db", min_samples=5)
        for _ in range(10):
            provider._record_adaptive_run(
                TaskType.WRITING, "m1", success=True, latency_ms=1000, quality_score=9.0,
            )

        # 显式 model 应胜出
        model = provider._resolve_model(task=TaskType.WRITING, explicit_model="custom_model")
        assert model == "custom_model"

    def test_resolve_per_task_independent(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：不同 task 独立选模型。"""
        provider = LLMProvider(
            LLMConfig(cache_enabled=False, default_model="deepseek/deepseek-flash")
        )
        provider.init_adaptive_router(db_path=tmp_path / "router.db", min_samples=5)

        # WRITING: m1 优
        for _ in range(10):
            provider._record_adaptive_run(
                TaskType.WRITING, "m1", success=True, latency_ms=1000, quality_score=9.0,
            )
            provider._record_adaptive_run(
                TaskType.WRITING, "m2", success=True, latency_ms=5000, quality_score=6.0,
            )
        # SUMMARIZATION: m2 优
        for _ in range(10):
            provider._record_adaptive_run(
                TaskType.SUMMARIZATION, "m2", success=True, latency_ms=2000, quality_score=9.0,
            )
            provider._record_adaptive_run(
                TaskType.SUMMARIZATION, "m1", success=True, latency_ms=4000, quality_score=5.0,
            )

        assert provider._resolve_model(task=TaskType.WRITING) == "m1"
        assert provider._resolve_model(task=TaskType.SUMMARIZATION) == "m2"

    def test_resolve_router_failure_falls_back(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：AdaptiveRouter 失败 → fall back to V0.23 ModelRouter。"""
        provider = LLMProvider(LLMConfig(cache_enabled=False))
        # Manually set a broken router
        provider._adaptive_router = "broken_string"  # 非 None 但不合法
        # _resolve_model 应 catch exception 并 fall back
        model = provider._resolve_model(task=TaskType.WRITING)
        assert "deepseek" in model  # 走 ModelRouter 默认

    def test_resolve_no_task_uses_default(self, tmp_path: Path) -> None:
        """V0.30.6 C3 收尾：task=None → config.default_model。"""
        provider = LLMProvider(
            LLMConfig(cache_enabled=False, default_model="my_default")
        )
        provider.init_adaptive_router(db_path=tmp_path / "router.db")
        model = provider._resolve_model()  # task=None
        assert model == "my_default"