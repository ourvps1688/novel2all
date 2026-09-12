"""LLM Provider Router（V0.23）。

按任务类型（TaskType）选择合适的 LLM 模型，并支持回退。

V0.23 升级（基于 docs/llm-providers-truth.md + scripts/benchmark_llm.py 真实数据）：
- 默认路由：DeepSeek 双模型覆盖 5 个 TaskType
  - WRITING → deepseek-v4-pro（字数多 35%，旗舰创作）
  - CONSISTENCY / EXTRACTION / SUMMARIZATION / COVER → deepseek-flash（便宜 3.6 倍 + 快 2 倍）
- MODEL_PRICING：DeepSeek 真实 CNY 价格（off-peak / peak 双时段 + cache hit/miss）
- 新增 is_peak_hour() 时段判断（DeepSeek 高峰：周一至周五 9-12、14-18 北京时间）
- 新增 THINIKING_CONTROL 模型特殊配置（v4-pro 默认关 thinking 避免 reasoning 耗光 token）

设计目标：
- 把"模型选择"和"模型调用"解耦
- 一份 LLMConfig 既能控制 default 模型，又能按任务覆盖
- 失败回退 + 真实成本估算 + 时段感知

典型用法：
    from novel2all.core.provider import LLMConfig, LLMProvider
    from novel2all.core.provider_router import TaskType, ModelRouter

    config = LLMConfig(default_model="deepseek/deepseek-flash", ...)
    router = ModelRouter(config)
    provider = LLMProvider(config)

    # 按任务选模型
    model = router.select(TaskType.WRITING)  # → "deepseek/deepseek-v4-pro"
    primary, fallback = router.resolve(TaskType.EXTRACTION)  # → (flash, v4-pro)

    # 成本估算（自动时段感知）
    cost = router.cost_estimate(
        TaskType.WRITING, prompt_tokens=5000, completion_tokens=3000
    )

    # LLMProvider 集成（V0.22.5+）：
    response = await provider.complete(prompt=..., task=TaskType.WRITING)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel

from novel2all.core.provider import LLMConfig


class TaskType(str, Enum):
    """任务类型。

    每个任务对应不同的模型偏好：
    - WRITING：长篇写作（需要长输出 + 中文能力）
    - CONSISTENCY：一致性检查（需要深度推理）
    - EXTRACTION：结构化提取（需要 JSON schema + 速度）
    - SUMMARIZATION：摘要压缩（中等长度输出）
    - COVER：封面/视觉（暂未启用，留位）
    """

    WRITING = "writing"
    CONSISTENCY = "consistency"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    COVER = "cover"


# === DeepSeek 高峰时段（北京时间）===
# 高峰：周一至周五 9:00-12:00、14:00-18:00（其余为空闲时段）


def is_peak_hour() -> bool:
    """判断当前是否处于 DeepSeek 高峰时段（北京时间）。

    高峰时段价格为 off-peak 的 2 倍。V0.23 用于自动选取定价档位。

    Returns:
        True if 高峰时段；False if 闲时

    时段定义（DeepSeek 官方文档）：
    - 高峰：周一至周五 9:00-12:00、14:00-18:00（北京时间）
    - 闲时：其余时段（含周末全天）
    """
    # 优先用 zoneinfo（标准库）；fallback 到固定 UTC+8 偏移
    now: datetime
    tz_obj: Any  # ZoneInfo | timezone (兼容两种类型)
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+

        tz_obj = ZoneInfo("Asia/Shanghai")
    except Exception:
        # zoneinfo 找不到 tzdata（Windows 常见），退化用 UTC+8 固定偏移
        tz_obj = timezone(timedelta(hours=8))
    now = datetime.now(tz=tz_obj)
    if now.weekday() >= 5:  # 周六周日全天 off-peak
        return False
    hour = now.hour
    return (9 <= hour < 12) or (14 <= hour < 18)


# === 默认路由表（V0.27 真实质量决策）===
# 数据来源：
# 1. scripts/benchmark_results.md（2026-09-13 跑的真实数据）
# 2. scripts/test_quality_compare.py 实测质量对比（用户人工鉴别确认 minimax 显著更优）
#
# V0.27 关键决策：WRITING 切到 minimax-M3
# - minimax 实测 845 字 vs DeepSeek flash 550 字（不是空话：多出 295 字包含剧情推进 + 角色独白 + 伏笔）
# - 代价：minimax 慢 63%（6.39s vs 3.92s），贵 3.3 倍
# - 收益：长篇小说质量优先 > 节省 50% 成本
#
# V0.27 transparent 分流（_is_anthropic_compat）：
# - model="minimax/..." → httpx 直接调 /v1/messages（绕过 litellm 404 bug）
# - model="deepseek/..." → litellm + instructor（V0.21 验证路径）
#
# 其他 4 个 task 仍用 DeepSeek 双模型：
# - CONSISTENCY/EXTRACTION/SUMMARIZATION/COVER 都是结构化任务，DeepSeek flash 质量足够
# - minimax 与 instructor 不兼容（V0.26 实测），不能用 complete_structured

DEFAULT_TASK_ROUTES: dict[TaskType, str] = {
    # V0.27：WRITING 切到 minimax-M3（基于实测质量对比：minimax 文笔 + 剧情推进显著优于 DeepSeek flash）
    # 数据：scripts/test_quality_compare.py + docs/llm-providers-truth.md §15
    TaskType.WRITING: "minimax/MiniMax-M3",  # 创作质量优先（实测 845 字含有效剧情）
    TaskType.CONSISTENCY: "deepseek/deepseek-flash",  # flash 字数更多 + 便宜
    TaskType.EXTRACTION: "deepseek/deepseek-flash",  # 批量处理（V0.26 minimax 试过，但 instructor 不兼容，回退）
    TaskType.SUMMARIZATION: "deepseek/deepseek-flash",  # 批量处理
    TaskType.COVER: "deepseek/deepseek-flash",  # 批量处理
}

DEFAULT_TASK_FALLBACKS: dict[TaskType, str | None] = {
    # V0.27 前置：WRITING primary 将切到 minimax/MiniMax-M3（V0.27 实施）
    # fallback 改 v4-pro 保证质量（之前的 flash fallback 是 V0.23 假设 WRITING 用 v4-pro 时的设计）
    TaskType.WRITING: "deepseek/deepseek-v4-pro",  # minimax 故障 → v4-pro
    TaskType.CONSISTENCY: "deepseek/deepseek-v4-pro",
    TaskType.EXTRACTION: "deepseek/deepseek-v4-pro",
    TaskType.SUMMARIZATION: "deepseek/deepseek-v4-pro",
    TaskType.COVER: "deepseek/deepseek-v4-pro",
}

# === DeepSeek 模型特殊配置（避免 thinking 耗光 token）===
# v4-pro 默认开启 thinking（DeepSeek-V4-Pro-0813），对简单任务会耗光 token budget。
# benchmark 实测：v4-pro 不加 thinking 禁用 → 30.52s 输出 0 字（reasoning 用了所有 token）
# 解决方案：调用时显式 extra_body={"thinking": {"type": "disabled"}}
# flash 也类似（默认 thinking），但实际影响小（benchmark 测出正常输出）

THINKING_CONTROL: dict[str, dict[str, Any]] = {
    # v4-pro：默认关 thinking（防止 reasoning 耗光 token）
    "deepseek/deepseek-v4-pro": {"thinking": {"type": "disabled"}},
    # flash：默认关 thinking（保持一致性，避免偶发耗光 token）
    "deepseek/deepseek-flash": {"thinking": {"type": "disabled"}},
}


# === V0.23.5：模型完整 litellm 配置 ===
# 单一字典取代分散的 THINKING_CONTROL 等，统一管理每个模型的特殊配置：
# - api_base：自定义 endpoint（如 minimax 必须用国内 Anthropic 兼容）
# - extra_body：thinking 控制等（兼容 THINKING_CONTROL）
# - headers：自定义 HTTP header（极少用）
#
# 为什么需要 MODEL_CONFIG 而不是简单加更多字段到 LLMConfig？
# 1. 路由表（DEFAULT_TASK_ROUTES）按 model_name 决策，每种模型都有特殊 endpoint
# 2. 用户不应该需要知道每个模型的 endpoint
# 3. benchmark_llm.py 已经按模型配置 api_base，这里只是把同样逻辑搬到生产代码


class ModelConfig(BaseModel):
    """单个模型的完整 litellm 配置。

    字段：
    - api_base：自定义 endpoint URL（None = 用 litellm 默认）
    - extra_body：每次调用注入的额外参数（thinking、enable_thinking 等）
    - headers：自定义 HTTP header
    """

    api_base: str | None = None
    extra_body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None


MODEL_CONFIG: dict[str, ModelConfig] = {
    # DeepSeek 直连（OpenAI 兼容，LiteLLM 默认路由）
    "deepseek/deepseek-v4-pro": ModelConfig(
        extra_body={"thinking": {"type": "disabled"}},
    ),
    "deepseek/deepseek-flash": ModelConfig(
        extra_body={"thinking": {"type": "disabled"}},
    ),
    # DeepSeek 兼容旧路由名
    "deepseek/deepseek-chat": ModelConfig(
        extra_body={"thinking": {"type": "disabled"}},
    ),
    # minimax-M3（Anthropic Messages API 兼容）
    # V0.26 实测：LiteLLM 默认走 api.minimax.io（国际域名）→ 401 invalid key
    # V0.26 实测：国内 OpenAI 兼容 (api.minimax.cn/v1) HTTP 200 但 content 为空（thinking 丢失 bug）
    # V0.27 解决：LLMProvider._is_anthropic_compat 检测 api_base 含 "anthropic" 时，
    # 走 _call_anthropic_compat()（httpx 直接调 /v1/messages），绕过 LiteLLM 404 bug
    # 调用方直接传 model="minimax/MiniMax-M3" 即可，无需关心底层 endpoint
    "minimax/MiniMax-M3": ModelConfig(
        api_base="https://api.minimax.cn/anthropic",
        extra_body={"thinking": {"type": "disabled"}},
    ),
    # 千问 OpenAI 兼容（DashScope）
    "openai/qwen3.8-flash": ModelConfig(
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        extra_body={"enable_thinking": False},
    ),
    # qwen3.8-max 暂不放入 MODEL_CONFIG（V0.23.4 benchmark 验证太贵，不推荐）
}


def get_model_config(model: str) -> ModelConfig:
    """返回模型的完整 litellm 配置。

    未知模型返回空 ModelConfig（让 litellm 用默认行为）。
    """
    return MODEL_CONFIG.get(model, ModelConfig())


def get_thinking_control(model: str) -> dict[str, Any] | None:
    """返回模型的 thinking 控制参数（extra_body）。

    未知模型返回 None（让调用方用 litellm 默认）。

    V0.23.5 保留此函数（向后兼容），内部委托给 get_model_config。
    """
    cfg = get_model_config(model)
    return cfg.extra_body


# === DeepSeek 真实 CNY 价格表 ===
# 数据来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/（2026-09-12 抓取）
# 价格单位：CNY / M tokens
# 时段：off-peak（默认）+ peak（自动判断）
# cache：hit（缓存命中，按 1/50 ~ 1/30 价格）+ miss（缓存未命中）

MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek/deepseek-flash": {
        # Off-peak（默认）
        "input_hit_offpeak": 0.02,
        "input_miss_offpeak": 1.00,
        "output_offpeak": 4.00,
        # Peak（高峰）
        "input_hit_peak": 0.04,
        "input_miss_peak": 2.00,
        "output_peak": 8.00,
    },
    "deepseek/deepseek-v4-pro": {
        # Off-peak
        "input_hit_offpeak": 0.15,
        "input_miss_offpeak": 4.50,
        "output_offpeak": 13.50,
        # Peak
        "input_hit_peak": 0.30,
        "input_miss_peak": 9.00,
        "output_peak": 27.00,
    },
    # 兼容旧路由（V0.22.5 默认的 deepseek-chat 已下线，实际由 v4.1-Flash 服务）
    # 保留条目避免破坏现有 LLMConfig
    "deepseek/deepseek-chat": {
        "input_hit_offpeak": 0.02,
        "input_miss_offpeak": 1.00,
        "output_offpeak": 4.00,
        "input_hit_peak": 0.04,
        "input_miss_peak": 2.00,
        "output_peak": 8.00,
    },
    # V0.26：minimax-M3 EXTRACTION（无 peak/off-peak 区分，按统一价）
    # 数据来源：docs/llm-providers-truth.md §4（minimax 官方价格）
    "minimax/MiniMax-M3": {
        "input_hit_offpeak": 0.84,
        "input_miss_offpeak": 4.2,
        "output_offpeak": 8.4,
        "input_hit_peak": 0.84,
        "input_miss_peak": 4.2,
        "output_peak": 8.4,
    },
}


class RouterConfig(BaseModel):
    """Router 配置（可序列化为 JSON / YAML）。

    字段：
    - task_routes：每个任务的主模型（覆盖 default_model）
    - task_fallbacks：每个任务的回退模型（None = 无回退）
    """

    task_routes: dict[str, str] = {}
    task_fallbacks: dict[str, str | None] = {}


class ModelRouter:
    """LLM 模型路由器。

    选择策略：
    1. 用户在 config.task_routes 指定 → 用用户的
    2. 否则用 DEFAULT_TASK_ROUTES
    3. 用户传 model= 参数 → 完全覆盖 router（绕过路由）

    V0.23 新增：
    - is_peak_hour() 时段感知
    - cost_estimate 自动选价（off-peak vs peak）
    - get_thinking_control(model) 返回模型特殊配置
    """

    def __init__(
        self,
        config: LLMConfig,
        task_routes: dict[TaskType, str] | None = None,
        task_fallbacks: dict[TaskType, str | None] | None = None,
    ) -> None:
        self.config = config
        # 合并：用户覆盖 > 默认
        self._routes: dict[TaskType, str] = dict(DEFAULT_TASK_ROUTES)
        if task_routes:
            self._routes.update(task_routes)
        self._fallbacks: dict[TaskType, str | None] = dict(DEFAULT_TASK_FALLBACKS)
        if task_fallbacks:
            self._fallbacks.update(task_fallbacks)

    def select(self, task: TaskType) -> str:
        """返回 task 对应的主模型名（litellm prefix）。"""
        return self._routes[task]

    def resolve(self, task: TaskType) -> tuple[str, str | None]:
        """返回 (primary_model, fallback_model_or_None)。"""
        return self._routes[task], self._fallbacks[task]

    def has_fallback(self, task: TaskType) -> bool:
        """该任务是否有回退模型。"""
        return self._fallbacks.get(task) is not None

    def all_routes(self) -> dict[TaskType, dict[str, str | None]]:
        """导出全部路由（含回退），用于调试 / 持久化。"""
        return {
            task: {
                "primary": self._routes[task],
                "fallback": self._fallbacks.get(task),
            }
            for task in TaskType
        }

    def cost_estimate(
        self,
        task: TaskType,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        model: str | None = None,
        cache_hit: bool = False,
    ) -> float:
        """估算 CNY 成本（V0.23 时段感知）。

        Args:
            task: 任务类型（用于选主模型）
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            model: 显式指定模型（默认用主模型）
            cache_hit: 是否命中 prompt cache（命中按 cache_hit 价格）

        Returns:
            成本（CNY）。未知模型返回 0.0（让调用方决定 fallback 策略）。
        """
        model_name = model or self.select(task)
        pricing = MODEL_PRICING.get(model_name)
        if pricing is None:
            return 0.0

        # 时段选择（off-peak vs peak）
        peak = is_peak_hour()
        suffix = "_peak" if peak else "_offpeak"

        # 输入价格：cache_hit 或 cache_miss
        input_key = f"input_hit{suffix}" if cache_hit else f"input_miss{suffix}"
        input_price = pricing[input_key]
        output_price = pricing[f"output{suffix}"]

        prompt_cost = (prompt_tokens / 1_000_000) * input_price
        completion_cost = (completion_tokens / 1_000_000) * output_price
        return round(prompt_cost + completion_cost, 6)


def build_router_from_config(
    config: LLMConfig,
    router_config: RouterConfig | None = None,
) -> ModelRouter:
    """从 RouterConfig 构建 ModelRouter（用于反序列化 from JSON/YAML）。"""
    if router_config is None:
        return ModelRouter(config)
    task_routes: dict[TaskType, str] = {
        TaskType(k): v for k, v in router_config.task_routes.items()
    }
    task_fallbacks: dict[TaskType, str | None] = {
        TaskType(k): v for k, v in router_config.task_fallbacks.items()
    }
    return ModelRouter(config, task_routes=task_routes, task_fallbacks=task_fallbacks)


__all__ = [
    "DEFAULT_TASK_FALLBACKS",
    "DEFAULT_TASK_ROUTES",
    "MODEL_CONFIG",
    "MODEL_PRICING",
    "THINKING_CONTROL",
    "ModelConfig",
    "ModelRouter",
    "RouterConfig",
    "TaskType",
    "build_router_from_config",
    "get_model_config",
    "get_thinking_control",
    "is_peak_hour",
]


# 避免 mypy 把 Any 视为未使用
_ = Any
