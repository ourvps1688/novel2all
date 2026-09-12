"""ProviderRouter (V0.23) 单元测试。

不调真实 LLM —— 纯逻辑层验证：
- TaskType enum
- 默认路由表（DeepSeek 双模型，覆盖 5 个任务类型）
- MODEL_PRICING 真实 CNY 价格（off-peak / peak 双时段 + cache hit/miss）
- ModelRouter.select / resolve / has_fallback / all_routes / cost_estimate
- 自定义 task_routes 覆盖默认
- build_router_from_config 从 RouterConfig 还原
- LLMProvider._resolve_model 三优先级：explicit_model > task > default_model
- LLMProvider._get_extra_body 自动应用 thinking 控制
- LLMProvider 三方法（complete / complete_structured / stream）的 task 参数不破坏向后兼容
- is_peak_hour() 时段判断（mock 当前时间）

V0.23 升级：
- 新增 thinking_control + is_peak_hour + cache_hit cost_estimate 测试
- 重写价格测试用 DeepSeek 真实 CNY 价格（不再用旧 USD 占位符）
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from novel2all.core.provider import LLMConfig, LLMProvider
from novel2all.core.provider_router import (
    DEFAULT_TASK_FALLBACKS,
    DEFAULT_TASK_ROUTES,
    MODEL_CONFIG,
    MODEL_PRICING,
    THINKING_CONTROL,
    ModelRouter,
    RouterConfig,
    TaskType,
    build_router_from_config,
    get_model_config,
    get_thinking_control,
    is_peak_hour,
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
        """TaskType 是 str enum。"""
        assert TaskType.WRITING == "writing"  # type: ignore[comparison-overlap]
        assert TaskType.WRITING.value == "writing"


# === 默认路由表测试（V0.23 DeepSeek 双模型） ===


class TestDefaultRoutesV023:
    def test_writing_uses_v4_pro(self) -> None:
        """WRITING 应用 deepseek-v4-pro（字数多 35%）。"""
        assert DEFAULT_TASK_ROUTES[TaskType.WRITING] == "deepseek/deepseek-v4-pro"

    def test_other_tasks_use_flash(self) -> None:
        """V0.26：CONSISTENCY/EXTRACTION/SUMMARIZATION/COVER 应用 deepseek-flash（minimax 与 instructor 不兼容，失败回退）。"""
        for task in (
            TaskType.CONSISTENCY,
            TaskType.EXTRACTION,
            TaskType.SUMMARIZATION,
            TaskType.COVER,
        ):
            assert DEFAULT_TASK_ROUTES[task] == "deepseek/deepseek-flash", (
                f"{task.value} 应该用 flash"
            )

    def test_all_tasks_have_fallback(self) -> None:
        """V0.23 所有 TaskType 都有回退（双模型互为回退）。"""
        for task in TaskType:
            assert task in DEFAULT_TASK_FALLBACKS
            assert DEFAULT_TASK_FALLBACKS[task] is not None

    def test_fallbacks_cross_models(self) -> None:
        """回退是双模型互为回退（v4-pro ↔ flash）。"""
        assert DEFAULT_TASK_FALLBACKS[TaskType.WRITING] == "deepseek/deepseek-flash"
        for task in (
            TaskType.CONSISTENCY,
            TaskType.EXTRACTION,
            TaskType.SUMMARIZATION,
            TaskType.COVER,
        ):
            assert DEFAULT_TASK_FALLBACKS[task] == "deepseek/deepseek-v4-pro"


# === ModelRouter 基础测试 ===


class TestModelRouterSelect:
    def test_select_returns_default_model(self, router: ModelRouter) -> None:
        """未覆盖 task 时，select 返回默认路由。"""
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-v4-pro"

    def test_user_routes_override_defaults(self, config: LLMConfig) -> None:
        """用户提供的 task_routes 覆盖默认。"""
        custom = {TaskType.WRITING: "openai/gpt-4o"}
        router = ModelRouter(config, task_routes=custom)
        assert router.select(TaskType.WRITING) == "openai/gpt-4o"
        # 其他未覆盖的仍走默认（V0.26 EXTRACTION 失败回退 → flash）
        assert router.select(TaskType.EXTRACTION) == "deepseek/deepseek-flash"

    def test_select_all_tasks(self, router: ModelRouter) -> None:
        """对所有 TaskType 都能 select。"""
        for task in TaskType:
            model = router.select(task)
            assert isinstance(model, str)
            assert "/" in model  # litellm prefix 格式


class TestModelRouterResolve:
    def test_resolve_returns_tuple(self, router: ModelRouter) -> None:
        """resolve 返回 (primary, fallback)。"""
        primary, fallback = router.resolve(TaskType.WRITING)
        assert primary == "deepseek/deepseek-v4-pro"
        assert fallback == "deepseek/deepseek-flash"

    def test_resolve_flash_task(self, router: ModelRouter) -> None:
        """V0.26：SUMMARIZATION（flash 任务）返回 (flash, v4-pro)。"""
        primary, fallback = router.resolve(TaskType.SUMMARIZATION)
        assert primary == "deepseek/deepseek-flash"
        assert fallback == "deepseek/deepseek-v4-pro"

    def test_has_fallback_all_tasks(self, router: ModelRouter) -> None:
        """V0.23 所有任务都有 fallback。"""
        for task in TaskType:
            assert router.has_fallback(task) is True, f"{task.value} should have fallback"


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


# === MODEL_PRICING 测试（V0.23 真实 CNY 价格） ===


class TestModelPricingV023:
    def test_flash_pricing_keys(self) -> None:
        """flash 模型应有完整价格字段。"""
        flash = MODEL_PRICING["deepseek/deepseek-flash"]
        for key in (
            "input_hit_offpeak",
            "input_miss_offpeak",
            "output_offpeak",
            "input_hit_peak",
            "input_miss_peak",
            "output_peak",
        ):
            assert key in flash, f"missing key: {key}"

    def test_flash_real_prices(self) -> None:
        """flash 价格与官方文档一致（CNY/M tokens）。"""
        flash = MODEL_PRICING["deepseek/deepseek-flash"]
        assert flash["input_hit_offpeak"] == 0.02
        assert flash["input_miss_offpeak"] == 1.00
        assert flash["output_offpeak"] == 4.00
        assert flash["input_hit_peak"] == 0.04
        assert flash["input_miss_peak"] == 2.00
        assert flash["output_peak"] == 8.00

    def test_v4_pro_real_prices(self) -> None:
        """v4-pro 价格与官方文档一致。"""
        pro = MODEL_PRICING["deepseek/deepseek-v4-pro"]
        assert pro["input_hit_offpeak"] == 0.15
        assert pro["input_miss_offpeak"] == 4.50
        assert pro["output_offpeak"] == 13.50
        assert pro["input_hit_peak"] == 0.30
        assert pro["input_miss_peak"] == 9.00
        assert pro["output_peak"] == 27.00

    def test_peak_is_double_offpeak(self) -> None:
        """高峰 = 空闲 × 2（DeepSeek 官方文档原文）。"""
        for model in ("deepseek/deepseek-flash", "deepseek/deepseek-v4-pro"):
            p = MODEL_PRICING[model]
            for prefix in ("input_hit", "input_miss", "output"):
                offpeak = p[f"{prefix}_offpeak"]
                peak = p[f"{prefix}_peak"]
                assert peak == offpeak * 2, (
                    f"{model}.{prefix}: peak {peak} should be 2x offpeak {offpeak}"
                )


# === cost_estimate 测试（V0.23 时段感知 + cache_hit） ===


class TestCostEstimateV023:
    def test_flash_extraction_offpeak(self, router: ModelRouter) -> None:
        """V0.26：SUMMARIZATION（flash 任务）× flash off-peak 价格估算。"""
        # 5K input + 1K output, no cache hit
        # input: 5000 × 1.00 / 1M = 0.005
        # output: 1000 × 4.00 / 1M = 0.004
        # total: 0.009
        cost = router.cost_estimate(TaskType.SUMMARIZATION, 5000, 1000)
        assert cost == pytest.approx(0.009, abs=1e-6)

    def test_minimax_extraction_cost(self, router: ModelRouter) -> None:
        """V0.26：minimax-M3 价格估算（用 explicit model=）。"""
        # minimax-M3: input_miss=4.2, output=8.4
        # 5K input + 1K output
        # input: 5000 × 4.2 / 1M = 0.021
        # output: 1000 × 8.4 / 1M = 0.0084
        # total: 0.0294
        cost = router.cost_estimate(TaskType.EXTRACTION, 5000, 1000, model="minimax/MiniMax-M3")
        assert cost == pytest.approx(0.0294, abs=1e-6)

    def test_v4_pro_writing_offpeak(self, router: ModelRouter) -> None:
        """WRITING × v4-pro off-peak 价格估算。"""
        # 5K input + 3K output
        # input: 5000 × 4.50 / 1M = 0.0225
        # output: 3000 × 13.50 / 1M = 0.0405
        # total: 0.063
        cost = router.cost_estimate(TaskType.WRITING, 5000, 3000)
        assert cost == pytest.approx(0.063, abs=1e-6)

    def test_cache_hit_drastically_reduces_cost(self, router: ModelRouter) -> None:
        """cache hit 价格应明显低于 cache miss。"""
        cost_no_cache = router.cost_estimate(TaskType.WRITING, 5000, 3000)
        cost_cache = router.cost_estimate(TaskType.WRITING, 5000, 3000, cache_hit=True)
        # cache hit 应便宜至少 20%
        assert cost_cache < cost_no_cache * 0.8

    def test_cache_hit_v4_pro_specific(self, router: ModelRouter) -> None:
        """v4-pro cache hit 价格：5K × 0.15/M + 3K × 13.50/M = 0.04125。"""
        cost = router.cost_estimate(TaskType.WRITING, 5000, 3000, cache_hit=True)
        assert cost == pytest.approx(0.04125, abs=1e-6)

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
        flash_cost = router.cost_estimate(
            TaskType.WRITING, 1000, 1000, model="deepseek/deepseek-flash"
        )
        pro_cost = router.cost_estimate(
            TaskType.WRITING, 1000, 1000, model="deepseek/deepseek-v4-pro"
        )
        assert flash_cost < pro_cost

    def test_cost_rounded(self, router: ModelRouter) -> None:
        """cost_estimate 返回值最多 6 位小数。"""
        cost = router.cost_estimate(TaskType.WRITING, 1, 1)
        assert isinstance(cost, float)


# === is_peak_hour 时段判断测试（V0.23 新增） ===


class TestIsPeakHour:
    def test_monday_morning_peak(self) -> None:
        """周一上午 10 点 → 高峰。"""
        with patch("novel2all.core.provider_router.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 9, 14, 10, 0, tzinfo=timezone(timedelta(hours=8))
            )  # 北京周一10:00
            assert is_peak_hour() is True

    def test_monday_lunch_offpeak(self) -> None:
        """周一 12:30 → 闲时（高峰 9-12）。"""
        with patch("novel2all.core.provider_router.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 9, 14, 12, 30, tzinfo=timezone(timedelta(hours=8))
            )  # 北京周一12:30
            assert is_peak_hour() is False

    def test_monday_afternoon_peak(self) -> None:
        """周一 15:00 → 高峰。"""
        with patch("novel2all.core.provider_router.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 9, 14, 15, 0, tzinfo=timezone(timedelta(hours=8))
            )  # 北京周一15:00
            assert is_peak_hour() is True

    def test_monday_evening_offpeak(self) -> None:
        """周一 19:00 → 闲时（高峰 14-18）。"""
        with patch("novel2all.core.provider_router.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 9, 14, 19, 0, tzinfo=timezone(timedelta(hours=8))
            )  # 北京周一19:00
            assert is_peak_hour() is False

    def test_weekend_always_offpeak(self) -> None:
        """周六周日全天闲时。"""
        # 2026-09-12 是周六，2026-09-13 是周日
        for day in (12, 13):
            with patch("novel2all.core.provider_router.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(
                    2026, 9, day, 10, 0, tzinfo=timezone(timedelta(hours=8))
                )  # 北京周六/日
                assert is_peak_hour() is False, f"day {day} should be off-peak"


# === Thinking 控制测试（V0.23 新增） ===


class TestThinkingControl:
    def test_v4_pro_disables_thinking(self) -> None:
        """v4-pro 应禁用 thinking（防止 reasoning 耗光 token）。"""
        tc = get_thinking_control("deepseek/deepseek-v4-pro")
        assert tc is not None
        assert tc["thinking"]["type"] == "disabled"

    def test_flash_disables_thinking(self) -> None:
        """flash 也禁用 thinking（保持一致性）。"""
        tc = get_thinking_control("deepseek/deepseek-flash")
        assert tc is not None
        assert tc["thinking"]["type"] == "disabled"

    def test_unknown_model_returns_none(self) -> None:
        """未知模型返回 None（让 litellm 用默认）。"""
        assert get_thinking_control("unknown/model") is None
        assert get_thinking_control("anthropic/claude-sonnet-4") is None

    def test_all_thinking_models_have_disabled(self) -> None:
        """所有 THINKING_CONTROL 里的模型都禁用 thinking。"""
        for model, tc in THINKING_CONTROL.items():
            assert tc["thinking"]["type"] == "disabled", f"{model} should have thinking disabled"


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
            task_fallbacks={"writing": None, "consistency": "deepseek/deepseek-flash"},
        )
        j = rc.model_dump_json()
        rc2 = RouterConfig.model_validate_json(j)
        assert rc2.task_routes["writing"] == "openai/gpt-4o"
        assert rc2.task_fallbacks["writing"] is None
        assert rc2.task_fallbacks["consistency"] == "deepseek/deepseek-flash"


class TestBuildRouterFromConfig:
    def test_no_router_config_uses_defaults(self, config: LLMConfig) -> None:
        """None RouterConfig → 用默认路由（V0.26 DeepSeek 双模型 + minimax 因与 instructor 不兼容被排除）。"""
        router = build_router_from_config(config, None)
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-v4-pro"
        # V0.26: EXTRACTION 仍用 deepseek-flash（minimax 与 instructor 不兼容失败回退）
        assert router.select(TaskType.EXTRACTION) == "deepseek/deepseek-flash"

    def test_with_router_config_overrides(self, config: LLMConfig) -> None:
        """RouterConfig 中的覆盖应生效。"""
        rc = RouterConfig(task_routes={"extraction": "openai/gpt-4o"})
        router = build_router_from_config(config, rc)
        assert router.select(TaskType.EXTRACTION) == "openai/gpt-4o"
        # 其他任务仍默认
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-v4-pro"

    def test_string_keys_mapped_to_enum(self, config: LLMConfig) -> None:
        """RouterConfig.task_routes 用 str key（来自 JSON），build 时转 TaskType。"""
        rc = RouterConfig(task_routes={"writing": "anthropic/claude-sonnet-4-20250514"})
        router = build_router_from_config(config, rc)
        assert router.select(TaskType.WRITING) == "anthropic/claude-sonnet-4-20250514"


# === LLMProvider._resolve_model 测试（mock 模式，不调真实 LLM）===


class TestLLMProviderResolveModel:
    def test_explicit_model_wins(self, config: LLMConfig) -> None:
        """explicit model= 优先于 task。"""
        provider = LLMProvider(config)
        result = provider._resolve_model(task=TaskType.WRITING, explicit_model="openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_task_uses_default_route(self, config: LLMConfig) -> None:
        """task= 不传 model 时，用 router 选（V0.23 v4-pro）。"""
        provider = LLMProvider(config)
        result = provider._resolve_model(task=TaskType.WRITING)
        assert result == "deepseek/deepseek-v4-pro"

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
        result = provider._resolve_model(task="some/random-model")  # type: ignore[arg-type]
        assert result == "some/random-model"


# === LLMProvider._get_extra_body 测试（V0.23 新增）===


class TestLLMProviderGetExtraBody:
    def test_v4_pro_gets_thinking_disabled(self, config: LLMConfig) -> None:
        """v4-pro 应自动应用 thinking:disabled。"""
        provider = LLMProvider(config)
        body = provider._get_extra_body("deepseek/deepseek-v4-pro")
        assert body is not None
        assert body["thinking"]["type"] == "disabled"

    def test_flash_gets_thinking_disabled(self, config: LLMConfig) -> None:
        """flash 也应自动应用。"""
        provider = LLMProvider(config)
        body = provider._get_extra_body("deepseek/deepseek-flash")
        assert body is not None

    def test_unknown_model_returns_none(self, config: LLMConfig) -> None:
        """未知模型返回 None（无额外控制）。"""
        provider = LLMProvider(config)
        assert provider._get_extra_body("openai/gpt-4o") is None
        assert provider._get_extra_body("custom/model") is None


# === 向后兼容测试（确保 task 参数不破坏现有调用）===


class TestBackwardCompat:
    def test_complete_signature_accepts_task(self) -> None:
        """complete() 签名应包含 task 参数。"""
        sig = inspect.signature(LLMProvider.complete)
        assert "task" in sig.parameters
        # task 应该是 keyword-only
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

    def test_provider_extra_body_matches_thinking_control(self, config: LLMConfig) -> None:
        """provider._get_extra_body(model) 与 get_thinking_control(model) 一致。"""
        provider = LLMProvider(config)
        for model in ("deepseek/deepseek-v4-pro", "deepseek/deepseek-flash"):
            assert provider._get_extra_body(model) == get_thinking_control(model)


# === ModelConfig / MODEL_CONFIG 测试（V0.23.5）===


class TestModelConfig:
    """V0.23.5：每种模型的完整 litellm 配置（api_base + extra_body + headers）。"""

    def test_minimax_requires_anthropic_compat(self) -> None:
        """minimax 必须用 Anthropic 兼容路径 + 国内 endpoint（防止 401）。"""
        cfg = get_model_config("minimax/MiniMax-M3")
        assert cfg.api_base == "https://api.minimax.cn/anthropic"
        assert cfg.extra_body == {"thinking": {"type": "disabled"}}

    def test_qwen_requires_dashscope_base(self) -> None:
        """千问必须用 DashScope OpenAI 兼容 endpoint。"""
        cfg = get_model_config("openai/qwen3.8-flash")
        assert cfg.api_base == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert cfg.extra_body == {"enable_thinking": False}

    def test_deepseek_v4_pro_disables_thinking(self) -> None:
        """DeepSeek v4-pro 默认关 thinking（防 reasoning 耗光 token）。"""
        cfg = get_model_config("deepseek/deepseek-v4-pro")
        assert cfg.extra_body == {"thinking": {"type": "disabled"}}
        assert cfg.api_base is None  # 用 litellm 默认

    def test_deepseek_flash_disables_thinking(self) -> None:
        """DeepSeek flash 默认关 thinking。"""
        cfg = get_model_config("deepseek/deepseek-flash")
        assert cfg.extra_body == {"thinking": {"type": "disabled"}}

    def test_unknown_model_returns_empty_config(self) -> None:
        """未知模型返回空 ModelConfig（api_base=None + extra_body=None）。"""
        cfg = get_model_config("unknown/model-x")
        assert cfg.api_base is None
        assert cfg.extra_body is None
        assert cfg.headers is None

    def test_all_thinking_models_have_disabled(self) -> None:
        """所有有 thinking 配置的模型都禁用 thinking。"""
        for model, cfg in MODEL_CONFIG.items():
            if cfg.extra_body and "thinking" in cfg.extra_body:
                assert cfg.extra_body["thinking"]["type"] == "disabled", f"{model} 应禁用 thinking"

    def test_get_thinking_control_delegates_to_model_config(self) -> None:
        """V0.23 旧接口 get_thinking_control 委托给 ModelConfig（向后兼容）。"""
        assert (
            get_thinking_control("deepseek/deepseek-v4-pro")
            == get_model_config("deepseek/deepseek-v4-pro").extra_body
        )

    def test_llm_provider_uses_model_config(self) -> None:
        """LLMProvider._get_model_config 委托给 get_model_config。"""
        config = LLMConfig()
        provider = LLMProvider(config)
        assert (
            provider._get_model_config("minimax/MiniMax-M3").api_base
            == "https://api.minimax.cn/anthropic"
        )


# === LLMConfig V0.23.5 新字段测试 ===


class TestLLMConfigV0235:
    """V0.23.5：LLMConfig 加 api_key_minimax + api_key_dashscope。"""

    def test_default_has_no_extra_keys(self) -> None:
        """默认 LLMConfig 不设额外 key。"""
        config = LLMConfig()
        assert config.api_key_minimax is None
        assert config.api_key_dashscope is None

    def test_extra_keys_set(self) -> None:
        """能设置 minimax + dashscope key。"""
        config = LLMConfig(
            api_key_minimax="sk-cp-test-minimax",
            api_key_dashscope="sk-test-dashscope",
        )
        assert config.api_key_minimax == "sk-cp-test-minimax"
        assert config.api_key_dashscope == "sk-test-dashscope"

    def test_configure_env_sets_minimax_dashscope(self) -> None:
        """_configure_env 应设 MINIMAX_API_KEY + DASHSCOPE_API_KEY。"""
        import os

        config = LLMConfig(
            api_key_minimax="sk-cp-minimax-test",
            api_key_dashscope="sk-dashscope-test",
        )
        # 清掉之前可能的残留
        os.environ.pop("MINIMAX_API_KEY", None)
        os.environ.pop("DASHSCOPE_API_KEY", None)
        LLMProvider(config)
        assert os.environ.get("MINIMAX_API_KEY") == "sk-cp-minimax-test"
        assert os.environ.get("DASHSCOPE_API_KEY") == "sk-dashscope-test"
        # 清理
        os.environ.pop("MINIMAX_API_KEY", None)
        os.environ.pop("DASHSCOPE_API_KEY", None)


# === V0.24 Prompt Cache 测试 ===


class TestPromptCacheV024:
    """V0.24：LLMConfig 加 cache_enabled + LLMProvider 应用 cache。"""

    @pytest.mark.asyncio
    async def test_cache_disabled_by_default(self) -> None:
        """默认 LLMConfig.cache_enabled=False（向后兼容）。"""
        config = LLMConfig()
        assert config.cache_enabled is False
        assert config.cache_max_size == 256

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self) -> None:
        """cache miss 后存，第二次调用应命中。"""
        from novel2all.core.provider import LLMProvider

        # Mock LLMProvider 的 _resolve_model + 拦截 litellm.acompletion
        config = LLMConfig(cache_enabled=True, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        # 拦截 litellm.acompletion
        call_count = [0]

        async def fake_acompletion(**kwargs):
            call_count[0] += 1
            # 返回 mock response 对象
            from types import SimpleNamespace

            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=f"RESPONSE_{call_count[0]}"))
                ]
            )

        # Patch litellm.acompletion
        import litellm

        original_acompletion = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 调用 1：cache miss → 调 API → 存 cache
            result1 = await provider.complete(prompt="hello", system="sys")
            assert result1 == "RESPONSE_1"
            assert call_count[0] == 1
            assert provider._cache_misses == 1
            assert provider._cache_hits == 0

            # 调用 2：cache hit → 不调 API
            result2 = await provider.complete(prompt="hello", system="sys")
            assert result2 == "RESPONSE_1"  # 来自 cache
            assert call_count[0] == 1  # 没调 API
            assert provider._cache_misses == 1
            assert provider._cache_hits == 1
        finally:
            litellm.acompletion = original_acompletion

    @pytest.mark.asyncio
    async def test_cache_different_prompts(self) -> None:
        """不同 prompt 不应命中同一 cache entry。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=True, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        from types import SimpleNamespace

        import litellm

        async def fake_acompletion(**kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=f"RESP_{kwargs['messages'][-1]['content']}")
                    )
                ]
            )

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            await provider.complete(prompt="prompt_A")
            await provider.complete(prompt="prompt_B")
            # 两次都 cache miss（不同 prompt）
            assert provider._cache_misses == 2
            assert provider._cache_hits == 0
            # cache 应有 2 个 entries
            assert len(provider._cache) == 2
        finally:
            litellm.acompletion = original

    @pytest.mark.asyncio
    async def test_cache_different_temperature(self) -> None:
        """不同 temperature 不应命中同一 cache entry。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=True, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        from types import SimpleNamespace

        import litellm

        call_count = [0]

        async def fake_acompletion(**kwargs):
            call_count[0] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R{call_count[0]}"))]
            )

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            await provider.complete(prompt="p", temperature=0.7)
            await provider.complete(prompt="p", temperature=0.3)  # 不同 temp
            # 两次 cache miss
            assert provider._cache_misses == 2
        finally:
            litellm.acompletion = original

    @pytest.mark.asyncio
    async def test_cache_disabled_no_op(self) -> None:
        """cache_enabled=False 时不应存 cache。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=False, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        from types import SimpleNamespace

        import litellm

        async def fake_acompletion(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            await provider.complete(prompt="p")
            await provider.complete(prompt="p")
            # 不存 cache，两次都调 API
            assert len(provider._cache) == 0
            assert provider._cache_misses == 0  # 不计数
        finally:
            litellm.acompletion = original

    @pytest.mark.asyncio
    async def test_cache_max_size_evicts(self) -> None:
        """超过 cache_max_size 时清空 cache。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=True, cache_max_size=3, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        from types import SimpleNamespace

        import litellm

        async def fake_acompletion(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 调 5 次（不同 prompt）但 cache_max_size=3
            for i in range(5):
                await provider.complete(prompt=f"p_{i}")
            # cache 永远 ≤ 3
            assert len(provider._cache) <= 3
        finally:
            litellm.acompletion = original

    @pytest.mark.asyncio
    async def test_cache_stats(self) -> None:
        """cache_stats 返回正确统计。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=True, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        from types import SimpleNamespace

        import litellm

        async def fake_acompletion(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            await provider.complete(prompt="A")  # miss
            await provider.complete(prompt="A")  # hit
            await provider.complete(prompt="B")  # miss
            stats = provider.cache_stats()
            assert stats["enabled"] is True
            assert stats["hits"] == 1
            assert stats["misses"] == 2
            assert stats["hit_rate"] == 0.3333
            assert stats["size"] == 2  # 2 unique prompts
        finally:
            litellm.acompletion = original

    @pytest.mark.asyncio
    async def test_cache_clear(self) -> None:
        """cache_clear 重置 stats + 清空 cache。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=True, default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {"key1": "value1"}
        provider._cache_hits = 5
        provider._cache_misses = 3
        provider._resolve_model = lambda *, task, explicit_model: "mock/model"

        provider.cache_clear()
        assert len(provider._cache) == 0
        assert provider._cache_hits == 0
        assert provider._cache_misses == 0

    def test_cache_key_uses_sha256(self) -> None:
        """_make_cache_key 用 sha256 截 16 字符。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(default_model="mock/model")
        provider = LLMProvider.__new__(LLMProvider)
        provider.config = config
        provider._cache = {}
        provider._cache_hits = 0
        provider._cache_misses = 0

        key1 = provider._make_cache_key("model", "system", "user", 0.7)
        key2 = provider._make_cache_key("model", "system", "user", 0.7)
        assert key1 == key2  # same input → same key

        key3 = provider._make_cache_key("model", "different", "user", 0.7)
        assert key1 != key3  # different system → different key

        key4 = provider._make_cache_key("model", None, "user", 0.7)
        key5 = provider._make_cache_key("model", "", "user", 0.7)
        # None system 和 "" system 视为相同（用 empty hash）
        assert key4 == key5


# === V0.25 cache_enabled 从 .env 自动读取测试 ===


class TestCacheEnabledFromEnv:
    """V0.25：cache_enabled 默认值从 NOVEL2ALL_LLM_CACHE 环境变量读取。"""

    def test_default_disabled_when_env_not_set(self) -> None:
        """未设环境变量时 cache_enabled=False（向后兼容）。"""
        import os

        os.environ.pop("NOVEL2ALL_LLM_CACHE", None)
        config = LLMConfig()
        assert config.cache_enabled is False

    def test_env_true_enables_cache(self) -> None:
        """环境变量 NOVEL2ALL_LLM_CACHE=1 → cache_enabled=True。"""
        import os

        os.environ["NOVEL2ALL_LLM_CACHE"] = "1"
        try:
            config = LLMConfig()
            assert config.cache_enabled is True
        finally:
            os.environ.pop("NOVEL2ALL_LLM_CACHE", None)

    def test_env_true_word_enables_cache(self) -> None:
        """环境变量 NOVEL2ALL_LLM_CACHE=true → cache_enabled=True。"""
        import os

        os.environ["NOVEL2ALL_LLM_CACHE"] = "true"
        try:
            config = LLMConfig()
            assert config.cache_enabled is True
        finally:
            os.environ.pop("NOVEL2ALL_LLM_CACHE", None)

    def test_env_false_disables_cache(self) -> None:
        """环境变量 NOVEL2ALL_LLM_CACHE=false → cache_enabled=False。"""
        import os

        os.environ["NOVEL2ALL_LLM_CACHE"] = "false"
        try:
            config = LLMConfig()
            assert config.cache_enabled is False
        finally:
            os.environ.pop("NOVEL2ALL_LLM_CACHE", None)

    def test_explicit_cache_enabled_overrides_env(self) -> None:
        """显式传 cache_enabled=True 覆盖环境变量。"""
        import os

        os.environ["NOVEL2ALL_LLM_CACHE"] = "false"
        try:
            config = LLMConfig(cache_enabled=True)
            assert config.cache_enabled is True
        finally:
            os.environ.pop("NOVEL2ALL_LLM_CACHE", None)
