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


# === 默认路由表（V0.23，基于 benchmark 真实数据）===
# 数据来源：scripts/benchmark_results.md（2026-09-13 跑的真实数据）
# 关键发现：flash 总成本 ¥0.007 vs v4-pro ¥0.025（flash 便宜 3.6 倍）
# 唯一 v4-pro 优势：WRITING 字数多 35%（1662 vs 1232）

DEFAULT_TASK_ROUTES: dict[TaskType, str] = {
    TaskType.WRITING: "deepseek/deepseek-v4-pro",  # 旗舰创作，字数多 35%
    TaskType.CONSISTENCY: "deepseek/deepseek-flash",  # flash 在 consistency 上字数更多 + 便宜
    TaskType.EXTRACTION: "deepseek/deepseek-flash",  # 批量处理，最便宜最快
    TaskType.SUMMARIZATION: "deepseek/deepseek-flash",  # 批量处理
    TaskType.COVER: "deepseek/deepseek-flash",  # 批量处理
}

DEFAULT_TASK_FALLBACKS: dict[TaskType, str | None] = {
    TaskType.WRITING: "deepseek/deepseek-flash",  # v4-pro 故障 → flash
    TaskType.CONSISTENCY: "deepseek/deepseek-v4-pro",  # flash 故障 → v4-pro
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


def get_thinking_control(model: str) -> dict[str, Any] | None:
    """返回模型的 thinking 控制参数（extra_body）。

    未知模型返回 None（让调用方用 litellm 默认）。
    """
    return THINKING_CONTROL.get(model)


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
    "MODEL_PRICING",
    "THINKING_CONTROL",
    "ModelRouter",
    "RouterConfig",
    "TaskType",
    "build_router_from_config",
    "get_thinking_control",
    "is_peak_hour",
]


# 避免 mypy 把 Any 视为未使用
_ = Any
