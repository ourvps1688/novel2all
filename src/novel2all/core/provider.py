"""LLM Provider 抽象。

基于 LiteLLM 统一接口，支持 Anthropic / OpenAI / DeepSeek 等。
"""

from __future__ import annotations

import os
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _strip_proxy_env() -> None:
    """清除 httpx/litellm 会读取的代理环境变量。

    在沙箱/CI 环境下，HTTP_PROXY/HTTPS_PROXY 会让 httpx 通过代理连接 DeepSeek，
    代理会破坏 Bearer header（导致 'Illegal header value b\"Bearer \"'）。
    """
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(k, None)


# 模块加载时立即清代理（关键：litellm import 时就会读 env）
_strip_proxy_env()


class LLMConfig(BaseModel):
    """LLM 配置。

    注意 default_model 必须带 litellm provider 前缀：
      - claude-sonnet-4-...  → "anthropic/claude-sonnet-4-20250514"
      - gpt-4o               → "openai/gpt-4o"
      - deepseek-chat        → "deepseek/deepseek-chat"
    """

    default_model: str = "deepseek/deepseek-chat"
    fallback_model: str | None = "deepseek/deepseek-chat"
    api_key_anthropic: str | None = None
    api_key_openai: str | None = None
    api_key_deepseek: str | None = None
    timeout_seconds: int = 120
    max_retries: int = 3


class LLMProvider:
    """LLM 提供者抽象。

    用法：
        llm = LLMProvider(LLMConfig(...))
        response = await llm.complete(prompt="...")
        structured = await llm.complete_structured(prompt="...", response_model=MyModel)
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._configure_env()

    def _configure_env(self) -> None:
        """从 config 同步设置环境变量（LiteLLM 需要）。"""
        _strip_proxy_env()  # 沙箱/CI 环境必须
        if self.config.api_key_anthropic:
            os.environ["ANTHROPIC_API_KEY"] = self.config.api_key_anthropic
        if self.config.api_key_openai:
            os.environ["OPENAI_API_KEY"] = self.config.api_key_openai
        if self.config.api_key_deepseek:
            os.environ["DEEPSEEK_API_KEY"] = self.config.api_key_deepseek

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        task: Any = None,
    ) -> str:
        """调 LLM 完成文本生成。

        Args:
            task: TaskType 枚举（V0.22.5+）。若提供，router 选 model；若 model= 也提供，
                model= 优先（向后兼容测试 / 调试场景）。
        """
        # 决定模型：显式 model= > task router > config.default_model
        model_name = self._resolve_model(task=task, explicit_model=model)
        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": self.config.timeout_seconds,
            "num_retries": self.config.max_retries,
        }
        # V0.23：自动应用模型 thinking 控制（防止 reasoning 耗光 token）
        extra_body = self._get_extra_body(model_name)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content or ""

    async def complete_structured(
        self,
        prompt: str,
        *,
        response_model: type[T],
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.3,
        max_retries: int = 3,
        task: Any = None,
    ) -> T:
        """结构化输出：返回 Pydantic 模型实例。

        使用 instructor + 当前模型。
        """
        model_name = self._resolve_model(task=task, explicit_model=model)
        try:
            import instructor
        except ImportError as e:
            raise ImportError("Please install instructor: `uv add instructor`") from e

        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

        client = instructor.from_litellm(litellm.acompletion)

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        result = await client.chat.completions.create(  # type: ignore[misc]
            model=model_name,
            messages=messages,  # type: ignore[arg-type]
            response_model=response_model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=self.config.timeout_seconds,
        )
        return result  # type: ignore[no-any-return]

    async def stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        task: Any = None,
    ) -> Any:
        """流式输出：返回 async iterator。

        Args:
            task: TaskType 枚举（V0.22.5+）。若提供，router 选 model。
        """
        model_name = self._resolve_model(task=task, explicit_model=model)
        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        # V0.23：自动应用模型 thinking 控制
        extra_body = self._get_extra_body(model_name)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _resolve_model(self, *, task: Any = None, explicit_model: str | None = None) -> str:
        """决定本次调用使用哪个模型。

        优先级（高 → 低）：
        1. 显式 model= 参数（测试 / 调试场景）
        2. task 参数 + ModelRouter（V0.22.5+）
        3. config.default_model（向后兼容）
        """
        if explicit_model:
            return explicit_model
        if task is not None:
            # lazy import 避免循环依赖
            from novel2all.core.provider_router import ModelRouter, TaskType

            if not isinstance(task, TaskType):
                # 容错：非 TaskType 实例就当作普通 model name 处理
                return str(task)
            router = ModelRouter(self.config)
            return router.select(task)
        return self.config.default_model

    def _get_extra_body(self, model_name: str) -> dict[str, Any] | None:
        """V0.23：返回模型的特殊控制参数（extra_body）。

        主要用于 DeepSeek thinking 控制：
        - v4-pro 默认 thinking 模式会耗光 token → 显式禁用
        - flash 也类似（保持一致性）

        未知模型返回 None（让 litellm 用默认行为）。
        """
        # lazy import 避免循环依赖
        from novel2all.core.provider_router import get_thinking_control

        return get_thinking_control(model_name)
