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
    ) -> str:
        """调 LLM 完成文本生成。"""
        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

        model_name = model or self.config.default_model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await litellm.acompletion(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.config.timeout_seconds,
            num_retries=self.config.max_retries,
        )
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
    ) -> T:
        """结构化输出：返回 Pydantic 模型实例。

        使用 instructor + 当前模型。
        """
        try:
            import instructor
        except ImportError as e:
            raise ImportError("Please install instructor: `uv add instructor`") from e

        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

        model_name = model or self.config.default_model

        client = instructor.from_litellm(litellm.acompletion)

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        result = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=self.config.timeout_seconds,
        )
        return result

    async def stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> Any:
        """流式输出：返回 async iterator。"""
        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

        model_name = model or self.config.default_model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await litellm.acompletion(
            model=model_name,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
