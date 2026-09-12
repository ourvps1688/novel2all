"""LLM Provider Router（V0.22.5）。

按任务类型（TaskType）选择合适的 LLM 模型，并支持回退。

设计目标：
- 把"模型选择"和"模型调用"解耦
- 一份 LLMConfig 既能控制 default 模型，又能按任务覆盖
- 失败回退 + 成本估算

典型用法：
    from novel2all.core.provider import LLMConfig, LLMProvider
    from novel2all.core.provider_router import TaskType, ModelRouter

    config = LLMConfig(default_model="deepseek/deepseek-chat", ...)
    router = ModelRouter(config)
    provider = LLMProvider(config)

    # 按任务选模型
    model = router.select(TaskType.WRITING)  # → "deepseek/deepseek-chat"
    primary, fallback = router.resolve(TaskType.CONSISTENCY)  # → (claude..., deepseek...)

    # 成本估算
    cost = router.cost_estimate(TaskType.WRITING, prompt_tokens=3000, completion_tokens=4000)

    # LLMProvider 集成（V0.22.5+）：
    response = await provider.complete(prompt=..., task=TaskType.WRITING)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from novel2all.core.provider import LLMConfig


class TaskType(str, Enum):
    """任务类型。

    每个任务对应不同的模型偏好：
    - WRITING：长篇写作（需要长输出 + 中文能力 + 成本友好）
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


# === 默认路由表（设计文档 §4.2）===

DEFAULT_TASK_ROUTES: dict[TaskType, str] = {
    TaskType.WRITING: "deepseek/deepseek-chat",
    TaskType.CONSISTENCY: "anthropic/claude-sonnet-4-20250514",
    TaskType.EXTRACTION: "openai/gpt-4o-mini",
    TaskType.SUMMARIZATION: "deepseek/deepseek-chat",
    TaskType.COVER: "anthropic/claude-sonnet-4-20250514",
}

DEFAULT_TASK_FALLBACKS: dict[TaskType, str | None] = {
    TaskType.WRITING: None,  # 便宜模型无回退必要
    TaskType.CONSISTENCY: "deepseek/deepseek-chat",
    TaskType.EXTRACTION: "deepseek/deepseek-chat",
    TaskType.SUMMARIZATION: None,
    TaskType.COVER: "openai/gpt-4o",
}

# === 成本表（USD / 1M tokens，2026 年初行情）===
# 缺失的模型视为 0（调用方决定怎么处理）
MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek/deepseek-chat": {"prompt": 0.27, "completion": 1.10},
    "anthropic/claude-sonnet-4-20250514": {"prompt": 3.0, "completion": 15.0},
    "anthropic/claude-sonnet-4": {"prompt": 3.0, "completion": 15.0},
    "openai/gpt-4o": {"prompt": 2.5, "completion": 10.0},
    "openai/gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
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
    ) -> float:
        """估算 USD 成本。

        默认按主模型算；如传 model= 用指定模型。
        未知模型返回 0.0（让调用方决定 fallback 策略）。
        """
        model_name = model or self.select(task)
        pricing = MODEL_PRICING.get(model_name)
        if pricing is None:
            return 0.0
        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
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
    "ModelRouter",
    "RouterConfig",
    "TaskType",
    "build_router_from_config",
]


# 避免 mypy 把 Any 视为未使用
_ = Any
