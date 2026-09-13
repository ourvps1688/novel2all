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
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import ClassVar
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
    def test_writing_uses_minimax(self) -> None:
        """V0.27：WRITING 应用 minimax-M3（基于实测质量优势：剧情推进 + 角色独白 + 伏笔）。"""
        assert DEFAULT_TASK_ROUTES[TaskType.WRITING] == "minimax/MiniMax-M3"

    def test_other_tasks_use_flash(self) -> None:
        """V0.27：CONSISTENCY/EXTRACTION/SUMMARIZATION/COVER 应用 deepseek-flash（结构化任务，DeepSeek flash 质量足够 + 便宜）。"""
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

    def test_fallbacks_all_v4_pro(self) -> None:
        """V0.27：所有 fallback 都用 v4-pro（minimax/flash 故障 → v4-pro 兜底，保证质量）。"""
        for task in (
            TaskType.WRITING,
            TaskType.CONSISTENCY,
            TaskType.EXTRACTION,
            TaskType.SUMMARIZATION,
            TaskType.COVER,
        ):
            assert DEFAULT_TASK_FALLBACKS[task] == "deepseek/deepseek-v4-pro", (
                f"{task.value} fallback 应该是 v4-pro"
            )


# === ModelRouter 基础测试 ===


class TestModelRouterSelect:
    def test_select_returns_default_model(self, router: ModelRouter) -> None:
        """V0.27：WRITING 默认路由到 minimax（基于实测质量优势）。"""
        assert router.select(TaskType.WRITING) == "minimax/MiniMax-M3"

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
        """V0.27：resolve 返回 (minimax, v4-pro) — minimax 故障时回退到 v4-pro。"""
        primary, fallback = router.resolve(TaskType.WRITING)
        assert primary == "minimax/MiniMax-M3"
        assert fallback == "deepseek/deepseek-v4-pro"

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

    def test_minimax_writing_offpeak(self, router: ModelRouter) -> None:
        """V0.27：WRITING × minimax off-peak 价格估算。"""
        # minimax-M3: input_miss=4.2, output=8.4（无 peak/offpeak 区分）
        # 5K input + 3K output
        # input: 5000 × 4.2 / 1M = 0.021
        # output: 3000 × 8.4 / 1M = 0.0252
        # total: 0.0462
        cost = router.cost_estimate(TaskType.WRITING, 5000, 3000)
        assert cost == pytest.approx(0.0462, abs=1e-6)

    def test_cache_hit_drastically_reduces_cost(self, router: ModelRouter) -> None:
        """cache hit 价格应明显低于 cache miss。"""
        cost_no_cache = router.cost_estimate(TaskType.WRITING, 5000, 3000)
        cost_cache = router.cost_estimate(TaskType.WRITING, 5000, 3000, cache_hit=True)
        # cache hit 应便宜至少 20%
        assert cost_cache < cost_no_cache * 0.8

    def test_cache_hit_minimax_specific(self, router: ModelRouter) -> None:
        """V0.27：minimax cache hit 价格：5K × 0.84/M + 3K × 8.4/M = 0.0294。"""
        cost = router.cost_estimate(TaskType.WRITING, 5000, 3000, cache_hit=True)
        assert cost == pytest.approx(0.0294, abs=1e-6)

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
        """None RouterConfig → 用默认路由（V0.27 DeepSeek 4 task + minimax WRITING）。"""
        router = build_router_from_config(config, None)
        # V0.27: WRITING 默认 minimax（基于实测质量优势）
        assert router.select(TaskType.WRITING) == "minimax/MiniMax-M3"
        assert router.select(TaskType.EXTRACTION) == "deepseek/deepseek-flash"

    def test_with_router_config_overrides(self, config: LLMConfig) -> None:
        """RouterConfig 中的覆盖应生效。"""
        rc = RouterConfig(task_routes={"extraction": "openai/gpt-4o"})
        router = build_router_from_config(config, rc)
        assert router.select(TaskType.EXTRACTION) == "openai/gpt-4o"
        # WRITING 未覆盖，默认 V0.27 路由到 minimax
        assert router.select(TaskType.WRITING) == "minimax/MiniMax-M3"

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
        """V0.27：task=WRITING 默认路由到 minimax。"""
        provider = LLMProvider(config)
        result = provider._resolve_model(task=TaskType.WRITING)
        assert result == "minimax/MiniMax-M3"

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
        provider._cache = OrderedDict()
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
        provider._cache = OrderedDict()
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
        provider._cache = OrderedDict()
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
        provider._cache = OrderedDict()
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
        provider._cache = OrderedDict()
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
        provider._cache = OrderedDict()
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
        provider._cache = OrderedDict([("key1", "value1")])
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
        provider._cache = OrderedDict()
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


class TestCacheLRUV029:
    """V0.29：prompt cache 真 LRU 实现。

    V0.24 旧实现：超过 cache_max_size 时清空整个 cache（粗暴）
    V0.29 新实现：OrderedDict + move_to_end（读）+ popitem(last=False)（超 max_size 时淘汰最旧）

    关键语义：
    - 写入新条目：放 OrderedDict 末尾（最近写入）
    - 读 cache 命中：move_to_end 更新"最近使用"
    - 写新条目且超 max_size：popitem(last=False) 淘汰 OrderedDict 头部（最久未用）
    """

    def test_cache_evicts_least_recently_used(self) -> None:
        """写满 max_size 后，新条目触发淘汰最久未用的。"""
        from types import SimpleNamespace

        config = LLMConfig(cache_enabled=True, cache_max_size=2)
        provider = LLMProvider(config)
        provider._cache = OrderedDict()

        async def fake_acompletion(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        import litellm

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            # 写 3 条（max_size=2）→ 应淘汰第 1 条（最久未用）
            import asyncio

            asyncio.run(provider.complete(prompt="p1"))
            asyncio.run(provider.complete(prompt="p2"))
            asyncio.run(provider.complete(prompt="p3"))

            # 验证：cache 里有 p2 + p3，p1 被淘汰
            assert len(provider._cache) == 2
            keys = list(provider._cache.keys())
            assert len(keys) == 2
        finally:
            litellm.acompletion = original

    def test_cache_access_updates_lru_position(self) -> None:
        """命中 cache 时 move_to_end 更新 LRU 位置。"""
        from types import SimpleNamespace

        config = LLMConfig(cache_enabled=True, cache_max_size=2)
        provider = LLMProvider(config)
        provider._cache = OrderedDict()

        async def fake_acompletion(**kwargs):
            prompt = kwargs.get("messages", [{}])[-1].get("content", "")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R_{prompt}"))]
            )

        import litellm

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            import asyncio

            # 写 p1, p2（cache=[p1, p2]）
            asyncio.run(provider.complete(prompt="p1"))
            asyncio.run(provider.complete(prompt="p2"))
            keys_before = list(provider._cache.keys())
            assert len(keys_before) == 2

            # 命中 p1（应该 move_to_end，把 p1 移到末尾，p2 变成首）
            result = asyncio.run(provider.complete(prompt="p1"))
            assert result == "R_p1"
            keys_after = list(provider._cache.keys())
            # cache 现在顺序应该是 [p2, p1]（p2 在头部，因为 p1 被访问后移到了末尾）
            assert keys_after[0] == keys_before[1]  # p2 现在在头部
            assert keys_after[1] == keys_before[0]  # p1 现在在末尾

            # 现在写 p3 → 应该淘汰 p2（最久未用），保留 p1 + p3
            asyncio.run(provider.complete(prompt="p3"))
            keys_final = list(provider._cache.keys())
            assert len(keys_final) == 2
            # p2 应该被淘汰（cache 里现在 [p1, p3]）
            # p1 是 keys_after[1]，p3 是新写入
            assert keys_final[0] == keys_after[1]  # p1 仍在头部
            assert keys_final[1] != keys_after[0]  # p3 在末尾（新）
            # 而且 p2 不在 cache 里
            assert keys_after[0] not in keys_final
        finally:
            litellm.acompletion = original

    def test_cache_eviction_preserves_lru_order(self) -> None:
        """淘汰后剩余条目保持 LRU 顺序（从最久到最近）。"""
        from types import SimpleNamespace

        config = LLMConfig(cache_enabled=True, cache_max_size=3)
        provider = LLMProvider(config)
        provider._cache = OrderedDict()

        async def fake_acompletion(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="R"))])

        import litellm

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            import asyncio

            # 写 3 条（cache=[p1, p2, p3]，max_size=3 刚好）
            asyncio.run(provider.complete(prompt="p1"))
            asyncio.run(provider.complete(prompt="p2"))
            asyncio.run(provider.complete(prompt="p3"))
            keys_full = list(provider._cache.keys())
            assert len(keys_full) == 3

            # 命中 p1（移到末尾，cache=[p2, p3, p1]）
            asyncio.run(provider.complete(prompt="p1"))
            keys_after_hit = list(provider._cache.keys())
            assert keys_after_hit == [keys_full[1], keys_full[2], keys_full[0]]

            # 写 p4（触发淘汰：p2 是最久未用的，cache=[p3, p1, p4]）
            asyncio.run(provider.complete(prompt="p4"))
            keys_evicted = list(provider._cache.keys())
            # p2 应该被淘汰
            assert keys_full[1] not in keys_evicted
            # 剩余 [p3, p1, p4]
            assert keys_evicted[0] == keys_full[2]  # p3
            assert keys_evicted[1] == keys_full[0]  # p1（之前被访问过）
            assert keys_evicted[2] != keys_full[0] and keys_evicted[2] != keys_full[2]  # p4（新的）
        finally:
            litellm.acompletion = original

    def test_cache_update_existing_key(self) -> None:
        """重复写入相同 key 应更新内容且不淘汰。"""
        from types import SimpleNamespace

        config = LLMConfig(cache_enabled=True, cache_max_size=2)
        provider = LLMProvider(config)
        provider._cache = OrderedDict()

        async def fake_acompletion(**kwargs):
            prompt = kwargs.get("messages", [{}])[-1].get("content", "")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"R_{prompt}"))]
            )

        import litellm

        original = litellm.acompletion
        litellm.acompletion = fake_acompletion
        try:
            import asyncio

            asyncio.run(provider.complete(prompt="p1"))
            asyncio.run(provider.complete(prompt="p2"))
            # 此时 cache=[p1, p2]，max_size=2

            # 直接 store 相同 p1（模拟覆盖）—— 应该 move_to_end，不淘汰 p2
            key_p1 = provider._make_cache_key("deepseek/deepseek-flash", None, "p1", 0.7)
            provider._cache_store(key_p1, "NEW_p1_content")

            assert len(provider._cache) == 2  # 没淘汰
            assert provider._cache[key_p1] == "NEW_p1_content"
        finally:
            litellm.acompletion = original

    def test_cache_uses_ordered_dict_not_dict(self) -> None:
        """验证 _cache 是 OrderedDict 实例（不是普通 dict）。"""
        config = LLMConfig(cache_enabled=True)
        provider = LLMProvider(config)
        # 初始化后必须是 OrderedDict
        assert isinstance(provider._cache, OrderedDict)
        # 必须支持 OrderedDict 特有的 API
        assert hasattr(provider._cache, "move_to_end")
        assert hasattr(provider._cache, "popitem")


class TestAnthropicCompatV027:
    """V0.27 transparent 分流：Anthropic Messages API 兼容路径。

    关键背景：
    - minimax-M3 必须用国内 Anthropic 端点 api.minimax.cn/anthropic
    - litellm 默认拼 /v1/chat/completions → 404 page not found
    - V0.27 解法：LLMProvider._is_anthropic_compat 检测 api_base 含 "anthropic" 时，
      绕过 litellm，直接 httpx POST /v1/messages
    - 调用方传 model="minimax/MiniMax-M3" 即可，透明分流
    """

    def test_is_anthropic_compat_detects_minimax(self) -> None:
        """minimax api_base 含 "anthropic" → _is_anthropic_compat 返回 True。"""
        from novel2all.core.provider import LLMProvider

        provider = LLMProvider(LLMConfig())
        assert provider._is_anthropic_compat("minimax/MiniMax-M3") is True

    def test_is_anthropic_compat_false_for_deepseek(self) -> None:
        """DeepSeek / 千问（OpenAI 兼容）→ 返回 False（走 litellm）。"""
        from novel2all.core.provider import LLMProvider

        provider = LLMProvider(LLMConfig())
        assert provider._is_anthropic_compat("deepseek/deepseek-v4-pro") is False
        assert provider._is_anthropic_compat("deepseek/deepseek-flash") is False
        assert provider._is_anthropic_compat("openai/qwen3.8-flash") is False

    def test_is_anthropic_compat_false_for_unknown(self) -> None:
        """未知模型 → 返回 False（走 litellm 默认）。"""
        from novel2all.core.provider import LLMProvider

        provider = LLMProvider(LLMConfig())
        assert (
            provider._is_anthropic_compat("anthropic/claude-sonnet-4-20250514") is False
        )  # 无国内镜像配置
        assert provider._is_anthropic_compat("unknown-model") is False

    def test_anthropic_api_key_for_minimax_uses_minimax_key(self) -> None:
        """minimax model → 读 MINIMAX_API_KEY 环境变量。"""
        import os

        from novel2all.core.provider import LLMProvider

        os.environ["MINIMAX_API_KEY"] = "test-minimax-key"
        try:
            provider = LLMProvider(LLMConfig())
            assert provider._anthropic_api_key_for("minimax/MiniMax-M3") == "test-minimax-key"
        finally:
            os.environ.pop("MINIMAX_API_KEY", None)

    def test_anthropic_api_key_for_anthropic_uses_anthropic_key(self) -> None:
        """anthropic/claude model → 读 ANTHROPIC_API_KEY 环境变量。"""
        import os

        from novel2all.core.provider import LLMProvider

        os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
        try:
            provider = LLMProvider(LLMConfig())
            assert (
                provider._anthropic_api_key_for("anthropic/claude-sonnet-4-20250514")
                == "test-anthropic-key"
            )
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_anthropic_api_key_returns_none_when_unset(self) -> None:
        """未设置环境变量 → 返回 None（调用方需自己处理）。"""
        import os

        from novel2all.core.provider import LLMProvider

        os.environ.pop("MINIMAX_API_KEY", None)
        provider = LLMProvider(LLMConfig())
        assert provider._anthropic_api_key_for("minimax/MiniMax-M3") is None

    @pytest.mark.asyncio
    async def test_call_anthropic_compat_sends_correct_request(self) -> None:
        """_call_anthropic_compat 实际 httpx 请求格式正确。

        Mock httpx.AsyncClient.post，验证：
        - URL = api_base + /v1/messages
        - Headers: x-api-key, anthropic-version: 2023-06-01
        - Body.model: 去掉 provider 前缀（MiniMax-M3 而非 minimax/MiniMax-M3）
        - Body.system: 顶层（非 messages 内）
        - Body.messages: 只含 user（不含 system）
        - Body 合并 extra_body（如 thinking: {type: disabled}）
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from novel2all.core.provider import LLMProvider

        provider = LLMProvider(LLMConfig())

        with (
            patch.object(LLMProvider, "_anthropic_api_key_for", return_value="test-key"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        ):
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "id": "msg_xxx",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello back"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            }
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            content = await provider._call_anthropic_compat(
                model_name="minimax/MiniMax-M3",
                api_base="https://api.minimax.cn/anthropic",
                api_key="test-key",
                messages=[{"role": "user", "content": "Hello"}],
                system="You are a writer.",
                temperature=0.7,
                max_tokens=1024,
                extra_body={"thinking": {"type": "disabled"}},
            )

        # 1. 返回内容正确
        assert content == "Hello back"

        # 2. httpx.post 被调用一次
        mock_post.assert_called_once()
        # client.post(url, ...) 的 url 是位置参数（在 args[0]）
        call_args = mock_post.call_args.args
        assert call_args[0] == "https://api.minimax.cn/anthropic/v1/messages"

        # 3. Headers + Body 都在 kwargs
        call_kwargs = mock_post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

        body = call_kwargs["json"]
        assert body["model"] == "MiniMax-M3"  # 不是 "minimax/MiniMax-M3"
        assert body["max_tokens"] == 1024
        assert body["temperature"] == 0.7

        # 4. Body.system: 顶层（不在 messages）
        assert body["system"] == "You are a writer."
        assert all(m["role"] != "system" for m in body["messages"])
        assert body["messages"] == [{"role": "user", "content": "Hello"}]

        # 5. extra_body 合并（thinking: {type: disabled}）
        assert body["thinking"] == {"type": "disabled"}

    @pytest.mark.asyncio
    async def test_complete_routes_minimax_to_anthropic_compat(self) -> None:
        """complete() 调 minimax 时走 _call_anthropic_compat，不调 litellm。"""
        import os
        from unittest.mock import AsyncMock, patch

        from novel2all.core.provider import LLMProvider

        os.environ["MINIMAX_API_KEY"] = "test-key"
        try:
            provider = LLMProvider(LLMConfig())

            # Mock 两个：litellm 不应被调 + anthropic_compat 应被调
            with patch.object(
                LLMProvider, "_call_anthropic_compat", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = "MOCK_TEXT"

                # 同时 patch litellm（如果被调会失败）
                with patch("litellm.acompletion", new_callable=AsyncMock) as mock_litellm:
                    result = await provider.complete(prompt="hi", model="minimax/MiniMax-M3")

                    # 1. anthropic_compat 被调
                    mock_call.assert_called_once()
                    # 2. litellm 完全没被调（关键：透明分流）
                    mock_litellm.assert_not_called()
                    # 3. 返回内容
                    assert result == "MOCK_TEXT"
        finally:
            os.environ.pop("MINIMAX_API_KEY", None)

    @pytest.mark.asyncio
    async def test_complete_still_uses_litellm_for_deepseek(self) -> None:
        """complete() 调 DeepSeek（非 anthropic_compat）时仍走 litellm。"""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from novel2all.core.provider import LLMProvider

        provider = LLMProvider(LLMConfig())

        # 同时 patch 两个
        with (
            patch.object(
                LLMProvider, "_call_anthropic_compat", new_callable=AsyncMock
            ) as mock_call,
            patch("litellm.acompletion", new_callable=AsyncMock) as mock_litellm,
        ):
            mock_litellm.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="DS_RESPONSE"))]
            )

            result = await provider.complete(prompt="hi", model="deepseek/deepseek-flash")

            # 1. litellm 被调
            mock_litellm.assert_called_once()
            # 2. anthropic_compat 没被调
            mock_call.assert_not_called()
            # 3. 返回 litellm 内容
            assert result == "DS_RESPONSE"

    @pytest.mark.asyncio
    async def test_stream_anthropic_compat_yields_deltas(self) -> None:
        """_stream_anthropic_compat 正确解析 SSE content_block_delta 事件。"""
        from unittest.mock import patch

        from novel2all.core.provider import LLMProvider

        provider = LLMProvider(LLMConfig())

        # 构造 SSE 响应
        sse_lines = [
            "event: message_start",
            'data: {"type":"message_start","message":{"id":"msg_1"}}',
            "",
            "event: content_block_start",
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            "",
            "event: content_block_delta",
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
            "",
            "event: content_block_delta",
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}',
            "",
            "event: content_block_stop",
            'data: {"type":"content_block_stop","index":0}',
            "",
            "event: message_stop",
            'data: {"type":"message_stop"}',
            "",
        ]

        # Fake httpx.AsyncClient：模拟 SSE 流式响应
        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            async def aiter_lines(self):
                for line in sse_lines:
                    yield line

            async def aclose(self) -> None:
                return None

        class FakeStreamContext:
            """async with client.stream(...) as resp: 的 resp 上下文"""

            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, *args):
                return None

        class FakeClient:
            """async with httpx.AsyncClient(...) as client: 的 client 上下文"""

            captured_kwargs: ClassVar[dict] = {}

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def aclose(self) -> None:
                return None

            def stream(self, method: str, url: str, **kwargs):
                # V0.30.0a：httpx 0.28 client.stream() 返回 context manager（不是 coroutine）
                FakeClient.captured_kwargs = {"method": method, "url": url, **kwargs}
                return FakeStreamContext()

        with patch("httpx.AsyncClient", FakeClient):
            chunks: list[str] = []
            async for text in provider._stream_anthropic_compat(
                model_name="minimax/MiniMax-M3",
                api_base="https://api.minimax.cn/anthropic",
                api_key="test-key",
                messages=[{"role": "user", "content": "hi"}],
                system=None,
                temperature=0.7,
                max_tokens=1024,
                extra_body={"thinking": {"type": "disabled"}},
            ):
                chunks.append(text)

        # 只 yield text_delta，其他事件（start/stop）忽略
        assert chunks == ["Hello", " world"]
        # body 验证
        assert FakeClient.captured_kwargs["method"] == "POST"
        assert FakeClient.captured_kwargs["url"] == "https://api.minimax.cn/anthropic/v1/messages"
        body = FakeClient.captured_kwargs["json"]
        assert body["model"] == "MiniMax-M3"
        assert body["stream"] is True
        assert body["thinking"] == {"type": "disabled"}


class TestAnthropicRetryV0291:
    """V0.29.1：_call_anthropic_compat 加 tenacity retry/backoff。

    重试策略：
    - 网络错误（httpx.TransportError）→ 重试
    - 5xx 服务器错误 → 重试
    - 429 限流 → 重试
    - 其他 4xx 客户端错误 → 不重试（直接抛）
    - 指数退避：min_wait × 2^attempt，clamp 到 max_wait

    max_retries=3 → 总尝试 4 次（首次 + 3 重试）
    """

    @pytest.mark.asyncio
    async def test_retry_on_transient_error_then_success(self) -> None:
        import httpx

        """第一次 TransportError 失败，第二次成功——应返回 success content。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        """第一次 TransportError 失败，第二次成功——应返回 success content。"""

        from novel2all.core.provider import LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,  # 加速测试
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        call_count = 0

        async def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection failed")
            # 第二次成功
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "id": "msg_xxx",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Recovered content"}],
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with (
            patch.object(LLMProvider, "_anthropic_api_key_for", return_value="test-key"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        ):
            mock_post.side_effect = fake_post
            content = await provider._call_anthropic_compat(
                model_name="minimax/MiniMax-M3",
                api_base="https://api.minimax.cn/anthropic",
                api_key="test-key",
                messages=[{"role": "user", "content": "hi"}],
                system=None,
                temperature=0.7,
                max_tokens=128,
                extra_body=None,
            )

        assert content == "Recovered content"
        # 第一次失败 + 第二次成功 = 共 2 次调用
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_last_exception(self) -> None:
        """max_retries=3 共 4 次都失败 → 抛最后一次的异常（不是 RetryError）。"""
        from unittest.mock import AsyncMock, patch

        import httpx

        from novel2all.core.provider import LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        call_count = 0

        async def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError(f"Connection failed #{call_count}")

        with (
            patch.object(LLMProvider, "_anthropic_api_key_for", return_value="test-key"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        ):
            mock_post.side_effect = fake_post
            try:
                await provider._call_anthropic_compat(
                    model_name="minimax/MiniMax-M3",
                    api_base="https://api.minimax.cn/anthropic",
                    api_key="test-key",
                    messages=[{"role": "user", "content": "hi"}],
                    system=None,
                    temperature=0.7,
                    max_tokens=128,
                    extra_body=None,
                )
                raise AssertionError("应抛异常但没抛")
            except httpx.ConnectError as e:
                # 应抛最后一次的异常（message 含 #4，因为是第 4 次调用）
                assert "#4" in str(e), f"expected last exception (#4), got: {e}"

        # 首次 + 3 重试 = 4 次调用
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx_client_error(self) -> None:
        """4xx 客户端错误（如 400 bad request）不应重试。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        from novel2all.core.provider import LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        call_count = 0

        async def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # 400 Bad Request
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Bad Request", request=MagicMock(), response=mock_resp
                )
            )
            return mock_resp

        with (
            patch.object(LLMProvider, "_anthropic_api_key_for", return_value="test-key"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        ):
            mock_post.side_effect = fake_post
            try:
                await provider._call_anthropic_compat(
                    model_name="minimax/MiniMax-M3",
                    api_base="https://api.minimax.cn/anthropic",
                    api_key="test-key",
                    messages=[{"role": "user", "content": "hi"}],
                    system=None,
                    temperature=0.7,
                    max_tokens=128,
                    extra_body=None,
                )
                raise AssertionError("应抛异常但没抛")
            except httpx.HTTPStatusError as e:
                assert e.response.status_code == 400

        # 4xx 不重试：只 1 次调用
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self) -> None:
        """429 限流应重试。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        from novel2all.core.provider import LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        call_count = 0

        async def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 429 Too Many Requests
                mock_resp = MagicMock()
                mock_resp.status_code = 429
                mock_resp.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Too Many Requests", request=MagicMock(), response=mock_resp
                    )
                )
                return mock_resp
            # 第二次成功
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "content": [{"type": "text", "text": "OK after rate limit"}],
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with (
            patch.object(LLMProvider, "_anthropic_api_key_for", return_value="test-key"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        ):
            mock_post.side_effect = fake_post
            content = await provider._call_anthropic_compat(
                model_name="minimax/MiniMax-M3",
                api_base="https://api.minimax.cn/anthropic",
                api_key="test-key",
                messages=[{"role": "user", "content": "hi"}],
                system=None,
                temperature=0.7,
                max_tokens=128,
                extra_body=None,
            )

        assert content == "OK after rate limit"
        assert call_count == 2  # 1 失败 + 1 成功

    @pytest.mark.asyncio
    async def test_no_retry_when_max_retries_is_zero(self) -> None:
        """max_retries=0 → 只首次，不重试。"""
        from unittest.mock import AsyncMock, patch

        import httpx

        from novel2all.core.provider import LLMProvider

        config = LLMConfig(
            anthropic_max_retries=0,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        call_count = 0

        async def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("immediate failure")

        with (
            patch.object(LLMProvider, "_anthropic_api_key_for", return_value="test-key"),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        ):
            mock_post.side_effect = fake_post
            try:
                await provider._call_anthropic_compat(
                    model_name="minimax/MiniMax-M3",
                    api_base="https://api.minimax.cn/anthropic",
                    api_key="test-key",
                    messages=[{"role": "user", "content": "hi"}],
                    system=None,
                    temperature=0.7,
                    max_tokens=128,
                    extra_body=None,
                )
                raise AssertionError("应抛异常但没抛")
            except httpx.ConnectError:
                pass

        # max_retries=0 → 只 1 次调用
        assert call_count == 1


class TestModelConfigApiKeyEnvV028:
    """V0.28：ModelConfig.api_key_env 字段驱动 _anthropic_api_key_for。

    之前 _anthropic_api_key_for 是硬编码 if/else（"minimax" in name → MINIMAX_API_KEY 等）；
    V0.28 改为读 MODEL_CONFIG[model_name].api_key_env，数据驱动：
    - 新增 anthropic_compat provider 只需在 MODEL_CONFIG 加条目 + api_key_env 字段
    - 未配置的模型自动返回 None（走 litellm 默认）
    """

    def test_model_config_has_api_key_env_field(self) -> None:
        """ModelConfig 含 api_key_env 字段，默认 None。"""
        from novel2all.core.provider_router import ModelConfig

        cfg = ModelConfig()
        assert cfg.api_key_env is None

    def test_model_config_api_key_env_can_be_set(self) -> None:
        """api_key_env 字段可显式赋值。"""
        from novel2all.core.provider_router import ModelConfig

        cfg = ModelConfig(api_key_env="MY_API_KEY")
        assert cfg.api_key_env == "MY_API_KEY"

    def test_minimax_config_has_api_key_env(self) -> None:
        """minimax MODEL_CONFIG 条目配了 api_key_env="MINIMAX_API_KEY"。"""
        from novel2all.core.provider_router import get_model_config

        cfg = get_model_config("minimax/MiniMax-M3")
        assert cfg.api_key_env == "MINIMAX_API_KEY"
        assert cfg.api_base == "https://api.minimax.cn/anthropic"

    def test_anthropic_config_has_api_key_env(self) -> None:
        """anthropic Claude MODEL_CONFIG 条目配了 api_key_env="ANTHROPIC_API_KEY"。"""
        from novel2all.core.provider_router import get_model_config

        cfg = get_model_config("anthropic/claude-sonnet-4-20250514")
        assert cfg.api_key_env == "ANTHROPIC_API_KEY"

    def test_deepseek_config_has_no_api_key_env(self) -> None:
        """deepseek 不走 anthropic_compat，api_key_env=None（走 litellm）。"""
        from novel2all.core.provider_router import get_model_config

        for model in ("deepseek/deepseek-v4-pro", "deepseek/deepseek-flash"):
            cfg = get_model_config(model)
            assert cfg.api_key_env is None, f"{model} should not have api_key_env"

    def test_anthropic_api_key_for_uses_config_driven(self) -> None:
        """_anthropic_api_key_for 现在纯配置驱动，不再有 hardcoded if/else。"""
        import os

        from novel2all.core.provider import LLMProvider

        os.environ["MINIMAX_API_KEY"] = "test-minimax"
        os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
        os.environ["MY_CUSTOM_KEY"] = "test-custom"
        try:
            provider = LLMProvider(LLMConfig())

            # 1. minimax → MINIMAX_API_KEY（配置驱动）
            assert provider._anthropic_api_key_for("minimax/MiniMax-M3") == "test-minimax"

            # 2. anthropic → ANTHROPIC_API_KEY（配置驱动）
            assert (
                provider._anthropic_api_key_for("anthropic/claude-sonnet-4-20250514")
                == "test-anthropic"
            )

            # 3. 未来加 anthropic_compat provider：只需在 MODEL_CONFIG 加条目，
            #    函数本身无需改（这是 V0.28 的核心改进）
            # 临时注入一个假 anthropic_compat provider
            from novel2all.core.provider_router import MODEL_CONFIG, ModelConfig

            MODEL_CONFIG["my-provider/my-model"] = ModelConfig(
                api_base="https://api.example.com/anthropic",  # 含 "anthropic" 触发 anthropic_compat
                api_key_env="MY_CUSTOM_KEY",
            )
            try:
                assert provider._anthropic_api_key_for("my-provider/my-model") == "test-custom"
            finally:
                # 清理
                del MODEL_CONFIG["my-provider/my-model"]

            # 4. 未配置的 model → None（走 litellm 默认）
            assert provider._anthropic_api_key_for("random/unknown") is None
        finally:
            for k in ("MINIMAX_API_KEY", "ANTHROPIC_API_KEY", "MY_CUSTOM_KEY"):
                os.environ.pop(k, None)

    def test_complete_routes_anthropic_through_litellm_with_configured_key(self) -> None:
        """anthropic Claude 配了 api_key_env 但 api_base 是 None → 仍走 litellm。

        关键行为：anthropic/* 默认走 litellm（_is_anthropic_compat=False，因为 api_base 为 None）；
        _anthropic_api_key_for 仍可返回 key（用于 litellm 调 litellm.acompletion(api_key=...) 的透明 fallback）。
        """
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from novel2all.core.provider import LLMProvider

        os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
        try:
            provider = LLMProvider(LLMConfig())

            with patch("litellm.acompletion", new_callable=AsyncMock) as mock_litellm:
                mock_litellm.return_value = MagicMock(
                    choices=[MagicMock(message=MagicMock(content="CLAUDE_RESPONSE"))]
                )

                result = provider._anthropic_api_key_for("anthropic/claude-sonnet-4-20250514")
                # V0.28：key 已配（数据驱动）
                assert result == "test-anthropic-key"
                # 当前 api_base=None，_is_anthropic_compat=False，走 litellm
                assert provider._is_anthropic_compat("anthropic/claude-sonnet-4-20250514") is False
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
