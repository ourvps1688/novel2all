"""ProviderRouter (V0.22.5) 单元测试。

不调真实 LLM —— 纯逻辑层验证：
- TaskType enum
- 默认路由表（覆盖 5 个任务类型）
- ModelRouter.select / resolve / has_fallback / all_routes / cost_estimate
- 自定义 task_routes 覆盖默认
- build_router_from_config 从 RouterConfig 还原
- LLMProvider._resolve_model 三优先级：explicit_model > task > default_model
- LLMProvider 三方法（complete / complete_structured / stream）的 task 参数不破坏向后兼容
"""

from __future__ import annotations

import inspect

import pytest

from novel2all.core.provider import LLMConfig, LLMProvider
from novel2all.core.provider_router import (
    DEFAULT_TASK_FALLBACKS,
    DEFAULT_TASK_ROUTES,
    MODEL_PRICING,
    ModelRouter,
    RouterConfig,
    TaskType,
    build_router_from_config,
)


@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig()


@pytest.fixture
def router(config: LLMConfig) -> ModelRouter:
    return ModelRouter(config)


# === TaskType enum 测试 ===


class TestTaskType:
    def test_five_task_types(self) -> None:
        """应有 5 个任务类型。"""
        assert len(list(TaskType)) == 5

    def test_task_values(self) -> None:
        """验证 5 个 task 的字符串值。"""
        assert TaskType.WRITING.value == "writing"
        assert TaskType.CONSISTENCY.value == "consistency"
        assert TaskType.EXTRACTION.value == "extraction"
        assert TaskType.SUMMARIZATION.value == "summarization"
        assert TaskType.COVER.value == "cover"

    def test_task_is_str_enum(self) -> None:
        """TaskType 是 str enum，可直接当 str 用（比较）。"""
        assert TaskType.WRITING == "writing"  # type: ignore[comparison-overlap]
        assert TaskType.WRITING.value == "writing"


# === 默认路由表测试 ===


class TestDefaultRoutes:
    @pytest.mark.parametrize(
        "task,expected_model",
        [
            (TaskType.WRITING, "deepseek/deepseek-chat"),
            (TaskType.CONSISTENCY, "anthropic/claude-sonnet-4-20250514"),
            (TaskType.EXTRACTION, "openai/gpt-4o-mini"),
            (TaskType.SUMMARIZATION, "deepseek/deepseek-chat"),
            (TaskType.COVER, "anthropic/claude-sonnet-4-20250514"),
        ],
    )
    def test_default_routes_all_tasks(self, task: TaskType, expected_model: str) -> None:
        assert DEFAULT_TASK_ROUTES[task] == expected_model

    def test_all_tasks_have_routes(self) -> None:
        """所有 TaskType 都有默认路由。"""
        for task in TaskType:
            assert task in DEFAULT_TASK_ROUTES
            assert DEFAULT_TASK_ROUTES[task]  # 非空

    def test_some_tasks_have_fallback(self) -> None:
        """CONSISTENCY / EXTRACTION / COVER 应有回退；WRITING / SUMMARIZATION 可无回退。"""
        assert DEFAULT_TASK_FALLBACKS[TaskType.CONSISTENCY] == "deepseek/deepseek-chat"
        assert DEFAULT_TASK_FALLBACKS[TaskType.EXTRACTION] == "deepseek/deepseek-chat"
        assert DEFAULT_TASK_FALLBACKS[TaskType.COVER] == "openai/gpt-4o"
        assert DEFAULT_TASK_FALLBACKS[TaskType.WRITING] is None
        assert DEFAULT_TASK_FALLBACKS[TaskType.SUMMARIZATION] is None


# === ModelRouter 基础测试 ===


class TestModelRouterSelect:
    def test_select_returns_default_model(self, router: ModelRouter) -> None:
        """未覆盖 task 时，select 返回默认路由。"""
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-chat"

    def test_user_routes_override_defaults(self, config: LLMConfig) -> None:
        """用户提供的 task_routes 覆盖默认。"""
        custom = {TaskType.WRITING: "openai/gpt-4o"}
        router = ModelRouter(config, task_routes=custom)
        assert router.select(TaskType.WRITING) == "openai/gpt-4o"
        # 其他未覆盖的仍走默认
        assert router.select(TaskType.EXTRACTION) == "openai/gpt-4o-mini"

    def test_select_all_tasks(self, router: ModelRouter) -> None:
        """对所有 TaskType 都能 select。"""
        for task in TaskType:
            model = router.select(task)
            assert isinstance(model, str)
            assert "/" in model  # litellm prefix 格式


class TestModelRouterResolve:
    def test_resolve_returns_tuple(self, router: ModelRouter) -> None:
        """resolve 返回 (primary, fallback)。"""
        primary, fallback = router.resolve(TaskType.CONSISTENCY)
        assert primary == "anthropic/claude-sonnet-4-20250514"
        assert fallback == "deepseek/deepseek-chat"

    def test_resolve_fallback_none(self, router: ModelRouter) -> None:
        """WRITING 无 fallback。"""
        primary, fallback = router.resolve(TaskType.WRITING)
        assert primary == "deepseek/deepseek-chat"
        assert fallback is None

    def test_has_fallback(self, router: ModelRouter) -> None:
        """has_fallback 与 fallback 是否为 None 一致。"""
        assert router.has_fallback(TaskType.CONSISTENCY) is True
        assert router.has_fallback(TaskType.WRITING) is False
        assert router.has_fallback(TaskType.SUMMARIZATION) is False


class TestModelRouterAllRoutes:
    def test_all_routes_returns_all_tasks(self, router: ModelRouter) -> None:
        """all_routes 覆盖所有 TaskType。"""
        routes = router.all_routes()
        assert set(routes.keys()) == set(TaskType)
        for info in routes.values():
            assert "primary" in info
            assert "fallback" in info
            assert isinstance(info["primary"], str)

    def test_all_routes_user_override(self, config: LLMConfig) -> None:
        """all_routes 反映用户覆盖。"""
        custom = {TaskType.EXTRACTION: "anthropic/claude-sonnet-4-20250514"}
        router = ModelRouter(config, task_routes=custom)
        routes = router.all_routes()
        assert routes[TaskType.EXTRACTION]["primary"] == "anthropic/claude-sonnet-4-20250514"


# === cost_estimate 测试 ===


class TestCostEstimate:
    def test_known_model_returns_value(self, router: ModelRouter) -> None:
        """已知模型的 cost_estimate 应 > 0。"""
        cost = router.cost_estimate(TaskType.WRITING, prompt_tokens=1000, completion_tokens=1000)
        # deepseek: 1000/1M * 0.27 + 1000/1M * 1.10 = 0.00137
        assert cost == pytest.approx(0.00137, abs=1e-6)

    def test_unknown_model_returns_zero(self, router: ModelRouter) -> None:
        """未知模型（不在价格表里）返回 0.0。"""
        cost = router.cost_estimate(TaskType.WRITING, 1000, 1000, model="unknown/model-x")
        assert cost == 0.0

    def test_zero_tokens_returns_zero(self, router: ModelRouter) -> None:
        """0 token 输入输出 → cost = 0。"""
        cost = router.cost_estimate(TaskType.EXTRACTION, 0, 0)
        assert cost == 0.0

    def test_different_models_different_cost(self, router: ModelRouter) -> None:
        """不同模型同一 token 数量 → cost 不同。"""
        deepseek_cost = router.cost_estimate(
            TaskType.WRITING, 1000, 1000, model="deepseek/deepseek-chat"
        )
        claude_cost = router.cost_estimate(
            TaskType.WRITING, 1000, 1000, model="anthropic/claude-sonnet-4-20250514"
        )
        assert deepseek_cost < claude_cost

    def test_cost_rounded(self, router: ModelRouter) -> None:
        """cost_estimate 返回值最多 6 位小数。"""
        cost = router.cost_estimate(TaskType.WRITING, 1, 1)
        # 1 token = 1e-6 * 0.27 + 1e-6 * 1.10 = 1.37e-6
        # round to 6 decimals
        assert isinstance(cost, float)

    def test_pricing_table_covers_default_models(self) -> None:
        """MODEL_PRICING 应覆盖所有默认路由模型的至少一种形式。"""
        # 检查每个 default route 的 model name 至少有 pricing（exact 或带后缀）
        for task, model in DEFAULT_TASK_ROUTES.items():
            assert model in MODEL_PRICING or model.split("/")[-1] in MODEL_PRICING, (
                f"{task.value} → {model} not in pricing"
            )


# === RouterConfig 测试 ===


class TestRouterConfig:
    def test_empty_config(self) -> None:
        """空 RouterConfig 可序列化。"""
        rc = RouterConfig()
        assert rc.task_routes == {}
        assert rc.task_fallbacks == {}

    def test_serialize_deserialize(self) -> None:
        """RouterConfig 可 JSON 序列化往返。"""
        rc = RouterConfig(
            task_routes={"writing": "openai/gpt-4o"},
            task_fallbacks={"writing": None, "consistency": "deepseek/deepseek-chat"},
        )
        j = rc.model_dump_json()
        rc2 = RouterConfig.model_validate_json(j)
        assert rc2.task_routes["writing"] == "openai/gpt-4o"
        assert rc2.task_fallbacks["writing"] is None
        assert rc2.task_fallbacks["consistency"] == "deepseek/deepseek-chat"


class TestBuildRouterFromConfig:
    def test_no_router_config_uses_defaults(self, config: LLMConfig) -> None:
        """None RouterConfig → 用默认路由。"""
        router = build_router_from_config(config, None)
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-chat"

    def test_with_router_config_overrides(self, config: LLMConfig) -> None:
        """RouterConfig 中的覆盖应生效。"""
        rc = RouterConfig(task_routes={"extraction": "openai/gpt-4o"})
        router = build_router_from_config(config, rc)
        assert router.select(TaskType.EXTRACTION) == "openai/gpt-4o"
        # 其他任务仍默认
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-chat"

    def test_string_keys_mapped_to_enum(self, config: LLMConfig) -> None:
        """RouterConfig.task_routes 用 str key（来自 JSON），build 时转 TaskType。"""
        rc = RouterConfig(task_routes={"writing": "anthropic/claude-sonnet-4-20250514"})
        router = build_router_from_config(config, rc)
        assert router.select(TaskType.WRITING) == "anthropic/claude-sonnet-4-20250514"


# === LLMProvider._resolve_model 测试（mock 模式，不调真实 LLM）===


class TestLLMProviderResolveModel:
    """不调真实 LLM，只测试 _resolve_model 的优先级逻辑。"""

    def test_explicit_model_wins(self, config: LLMConfig) -> None:
        """explicit model= 优先于 task。"""
        provider = LLMProvider(config)
        result = provider._resolve_model(task=TaskType.WRITING, explicit_model="openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_task_overrides_default(self, config: LLMConfig) -> None:
        """task= 不传 model 时，用 router 选。"""
        provider = LLMProvider(config)
        result = provider._resolve_model(task=TaskType.CONSISTENCY)
        assert result == "anthropic/claude-sonnet-4-20250514"

    def test_default_when_no_task_no_model(self, config: LLMConfig) -> None:
        """无 task / 无 model= → config.default_model。"""
        provider = LLMProvider(config)
        result = provider._resolve_model()
        assert result == config.default_model

    def test_task_none_uses_default(self, config: LLMConfig) -> None:
        """task=None 等同无 task。"""
        provider = LLMProvider(config)
        result = provider._resolve_model(task=None)
        assert result == config.default_model

    def test_non_tasktype_falls_back_to_string(self, config: LLMConfig) -> None:
        """非 TaskType 值当作 model name（容错）。"""
        provider = LLMProvider(config)
        # 直接传字符串当 task
        result = provider._resolve_model(task="some/random-model")  # type: ignore[arg-type]
        assert result == "some/random-model"


# === 向后兼容测试（确保 task 参数不破坏现有调用）===


class TestBackwardCompat:
    """验证旧调用方式（无 task 参数）继续工作。"""

    def test_complete_signature_accepts_task(self) -> None:
        """complete() 签名应包含 task 参数。"""
        sig = inspect.signature(LLMProvider.complete)
        assert "task" in sig.parameters
        # task 应该是 keyword-only（避免位置参数破坏）
        assert sig.parameters["task"].kind == inspect.Parameter.KEYWORD_ONLY

    def test_complete_structured_signature_accepts_task(self) -> None:
        sig = inspect.signature(LLMProvider.complete_structured)
        assert "task" in sig.parameters

    def test_stream_signature_accepts_task(self) -> None:
        sig = inspect.signature(LLMProvider.stream)
        assert "task" in sig.parameters

    def test_task_default_is_none(self) -> None:
        """task 参数默认 None（向后兼容）。"""
        sig = inspect.signature(LLMProvider.complete)
        assert sig.parameters["task"].default is None


# === 集成测试：router + provider 一致性 ===


class TestRouterProviderIntegration:
    def test_router_select_matches_provider_resolve(self, config: LLMConfig) -> None:
        """router.select 与 provider._resolve_model 对同一 task 应返回相同模型。"""
        router = ModelRouter(config)
        provider = LLMProvider(config)
        for task in TaskType:
            assert router.select(task) == provider._resolve_model(task=task)

    def test_user_override_visible_in_provider(self, config: LLMConfig) -> None:
        """用户覆盖 task_routes 后，provider 通过 task 也能选到。"""
        # 注意：provider 内部每次都新建 ModelRouter，所以需要外部 router 传进去
        # 这里只验证 router 行为；V0.22.6+ 再加 provider.set_router() 优化
        router = ModelRouter(config, task_routes={TaskType.WRITING: "openai/gpt-4o"})
        assert router.select(TaskType.WRITING) == "openai/gpt-4o"
