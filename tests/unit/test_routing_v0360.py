"""V0.36 路由调整测试。

V0.35 benchmark 验证 minimax 与 deepseek-flash 字数持平（差异 < 0.5%），
但 flash 便宜 2.5 倍。V0.36 把 WRITING 默认从 minimax 切回 flash。

本文件验证：
1. DEFAULT_TASK_ROUTES 配置正确
2. ModelRouter.select() 行为正确
3. 与 minimax 相关的功能仍可用（显式 model="minimax/MiniMax-M3"）
4. 5 任务全部路由到 flash（统一简化）
5. Fallback 仍为 v4-pro
"""

from __future__ import annotations

import pytest

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.provider_router import (
    DEFAULT_TASK_FALLBACKS,
    DEFAULT_TASK_ROUTES,
    ModelRouter,
    TaskType,
)


# === V0.23.1：offpeak fixture（强制 is_peak_hour = False） ===
@pytest.fixture
def offpeak(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 is_peak_hour() 返回 False（off-peak）。

    背景：DeepSeek 高峰时段是北京 9-12、14-18 工作日，CI 在任何时区跑都不可控。
    价格测试假设 offpeak 价格（input 1.0/M, output 4.0/M），但运行在 peak 时段会
    返回 2x 数字。fixture mock 让测试确定性。
    """
    monkeypatch.setattr("novel2all.core.provider_router.is_peak_hour", lambda: False)


# === 1. DEFAULT_TASK_ROUTES 配置验证 ===


class TestV036DefaultRoutes:
    """V0.36：5 个 task 统一路由到 deepseek-flash（V0.35 benchmark 验证）。"""

    def test_all_tasks_route_to_flash(self) -> None:
        """V0.36：所有 5 个 task 默认走 deepseek-flash。"""
        for task in TaskType:
            assert DEFAULT_TASK_ROUTES[task] == "deepseek/deepseek-flash", (
                f"V0.36: {task.value} 应默认路由到 deepseek-flash，实际 = {DEFAULT_TASK_ROUTES[task]}"
            )

    def test_writing_no_longer_minimax(self) -> None:
        """V0.36：WRITING 不再默认 minimax（V0.27 假设被 V0.35 推翻）。"""
        assert DEFAULT_TASK_ROUTES[TaskType.WRITING] != "minimax/MiniMax-M3"

    def test_writing_is_flash(self) -> None:
        """V0.36：WRITING 显式为 deepseek-flash。"""
        assert DEFAULT_TASK_ROUTES[TaskType.WRITING] == "deepseek/deepseek-flash"

    def test_fallback_unchanged(self) -> None:
        """V0.36：所有 task 的 fallback 仍为 v4-pro（高质但慢）。"""
        for task in TaskType:
            assert DEFAULT_TASK_FALLBACKS[task] == "deepseek/deepseek-v4-pro", (
                f"{task.value} fallback 应为 v4-pro"
            )


# === 2. ModelRouter 行为验证 ===


class TestV036RouterBehavior:
    """V0.36：ModelRouter 正确路由到 flash。"""

    @pytest.fixture
    def router(self) -> ModelRouter:
        return ModelRouter(LLMConfig())

    def test_select_writing_returns_flash(self, router: ModelRouter) -> None:
        """V0.36：select(WRITING) 返回 deepseek-flash。"""
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-flash"

    def test_resolve_writing_returns_flash_v4pro(self, router: ModelRouter) -> None:
        """V0.36：resolve(WRITING) 返回 (flash, v4-pro)。"""
        primary, fallback = router.resolve(TaskType.WRITING)
        assert primary == "deepseek/deepseek-flash"
        assert fallback == "deepseek/deepseek-v4-pro"


# === 3. minimax 仍可用（显式 model=）===


class TestV036MinimaxStillAvailable:
    """V0.36：minimax 仍注册在 MODEL_CONFIG（用户可显式调用）。"""

    def test_minimax_still_in_model_config(self) -> None:
        """minimax/MiniMax-M3 仍在 MODEL_CONFIG（V0.27 实施未删除）。"""
        from novel2all.core.provider_router import get_model_config

        cfg = get_model_config("minimax/MiniMax-M3")
        assert cfg is not None
        assert cfg.api_base == "https://api.minimax.cn/anthropic"
        assert cfg.api_key_env == "MINIMAX_API_KEY"

    def test_explicit_minimax_call_still_works(self) -> None:
        """V0.36：显式 model='minimax/MiniMax-M3' 仍可调用（anthropic compat 分流）。"""
        provider = LLMProvider(LLMConfig())
        # 不调真实 API，只验证 _resolve_model 和 _is_anthropic_compat
        model = provider._resolve_model(task=TaskType.WRITING, explicit_model="minimax/MiniMax-M3")
        assert model == "minimax/MiniMax-M3"
        assert provider._is_anthropic_compat(model) is True


# === 4. 成本估算验证（V0.36 flash 是 WRITING 默认）===


class TestV036CostEstimate:
    """V0.36：WRITING 成本估算使用 flash 价格（不再是 minimax）。"""

    @pytest.fixture
    def router(self) -> ModelRouter:
        return ModelRouter(LLMConfig())

    def test_writing_cost_uses_flash_pricing(self, router: ModelRouter, offpeak) -> None:
        """V0.36：WRITING 成本 = flash 价格（input=1.0/M, output=4.0/M）。"""
        # 5K input + 3K output
        # input: 5000 × 1.0 / 1M = 0.005
        # output: 3000 × 4.0 / 1M = 0.012
        # total: 0.017
        cost = router.cost_estimate(TaskType.WRITING, 5000, 3000)
        assert cost == pytest.approx(0.017, abs=1e-6)

    def test_writing_cost_50_chapters(self, router: ModelRouter, offpeak) -> None:
        """V0.36：50 章小说 WRITING 总成本估算（V0.27 vs V0.36 对比）。

        V0.27 (minimax): 50 × 0.0462 = ¥2.31
        V0.36 (flash): 50 × 0.017 = ¥0.85
        节省：¥1.46（63%）
        """
        per_chapter = router.cost_estimate(TaskType.WRITING, 5000, 3000)
        total_50 = per_chapter * 50
        # V0.36 节省 60%+
        v027_minimax_cost = 0.0462 * 50
        assert total_50 < v027_minimax_cost * 0.5, (
            f"V0.36 应比 V0.27 节省 > 50%，实际 V0.36=¥{total_50:.2f} vs V0.27=¥{v027_minimax_cost:.2f}"
        )


# === 5. 路由决策历史记录（V0.36 文档化）===


class TestV036DecisionHistory:
    """V0.36：路由决策历史可在测试中查到（防止以后又回退）。"""

    def test_writing_route_history_in_code(self) -> None:
        """V0.36 决策应反映在 DEFAULT_TASK_ROUTES 注释中。"""
        import inspect

        from novel2all.core import provider_router

        # 找到 DEFAULT_TASK_ROUTES 源码
        source = inspect.getsource(provider_router)
        assert "V0.36" in source, "DEFAULT_TASK_ROUTES 注释应提到 V0.36"
        assert "WRITING" in source and "flash" in source, "应明确 V0.36 把 WRITING 切到 flash"

    def test_v036_test_file_exists(self) -> None:
        """V0.36 测试文件本身应存在（防止后续回归）。"""
        import importlib

        # 自身模块
        mod = importlib.import_module("tests.unit.test_routing_v0360")
        assert mod is not None


# === 6. CI/回归保护：禁止再改回 minimax ===


class TestV036RegressionGuard:
    """V0.36 回归保护：DEFAULT_TASK_ROUTES[WRITING] 不应是 minimax。

    这个测试是**显式**的回归保护。如果未来有人误改回 minimax，
    这个测试会失败，强制 review V0.35 benchmark 数据。
    """

    def test_writing_default_must_not_be_minimax(self) -> None:
        """V0.36 回归保护：WRITING 默认值禁止 minimax（V0.35 benchmark 已证明 flash 不输）。"""
        writing_default = DEFAULT_TASK_ROUTES[TaskType.WRITING]
        assert writing_default != "minimax/MiniMax-M3", (
            "V0.36 回归！WRITING 不应回到 minimax（V0.35 benchmark 已证明不必要）。"
            "如果要恢复 minimax，必须先重跑 benchmark 并更新 docs/llm-providers-truth.md §16"
        )
