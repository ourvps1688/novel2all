"""LLM Provider 抽象。

基于 LiteLLM 统一接口，支持 Anthropic / OpenAI / DeepSeek 等。

V0.24 prompt cache：
- 应用层 cache（dict-based，零新依赖），key = (model, system_hash, user_hash, temperature)
- 命中时直接返回缓存响应（不调 API）
- 设计为**透明** cache：调用方无感知，cost_estimate 自动算 cache_hit
- 适用场景：同一 system prompt + 类似 user prompt 重复调用（如 extractor 批处理章节）
"""

from __future__ import annotations

import hashlib
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
      - minimax-M3           → "minimax/MiniMax-M3"（必须用 Anthropic 兼容路径）
      - qwen3.8-flash        → "openai/qwen3.8-flash"（用 DashScope base_url）

    API key 设置：
      - api_key_anthropic / openai / deepseek：直接设到对应环境变量
      - api_key_minimax：设到 MINIMAX_API_KEY（V0.23.5+）
      - api_key_dashscope：设到 DASHSCOPE_API_KEY（V0.23.5+）
    """

    default_model: str = "deepseek/deepseek-chat"
    fallback_model: str | None = "deepseek/deepseek-chat"
    api_key_anthropic: str | None = None
    api_key_openai: str | None = None
    api_key_deepseek: str | None = None
    api_key_minimax: str | None = None
    api_key_dashscope: str | None = None
    timeout_seconds: int = 120
    max_retries: int = 3
    # V0.24：prompt cache（应用层 dict-based，零新依赖）
    # V0.25：从 NOVEL2ALL_LLM_CACHE 环境变量读默认（"1"/"true" 启用，其他关闭）
    cache_enabled: bool = False
    cache_max_size: int = 256  # LRU 上限（防内存爆炸）

    def __init__(self, **data: Any) -> None:
        """V0.25：从 .env 自动读 cache_enabled（如果未显式传入）。"""
        if "cache_enabled" not in data:
            env_val = os.environ.get("NOVEL2ALL_LLM_CACHE", "").lower()
            data["cache_enabled"] = env_val in ("1", "true", "yes", "on")
        super().__init__(**data)


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
        # V0.24：prompt cache（应用层 dict-based）
        # 透明 cache：调用方完全无感知
        self._cache: dict[tuple[str, str, str, float], str] = {}
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    def _configure_env(self) -> None:
        """从 config 同步设置环境变量（LiteLLM 需要）。"""
        _strip_proxy_env()  # 沙箱/CI 环境必须
        if self.config.api_key_anthropic:
            os.environ["ANTHROPIC_API_KEY"] = self.config.api_key_anthropic
        if self.config.api_key_openai:
            os.environ["OPENAI_API_KEY"] = self.config.api_key_openai
        if self.config.api_key_deepseek:
            os.environ["DEEPSEEK_API_KEY"] = self.config.api_key_deepseek
        # V0.23.5+：minimax 和千问 key 注入
        if self.config.api_key_minimax:
            os.environ["MINIMAX_API_KEY"] = self.config.api_key_minimax
        if self.config.api_key_dashscope:
            os.environ["DASHSCOPE_API_KEY"] = self.config.api_key_dashscope

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

        V0.24：自动应用 prompt cache（如果 config.cache_enabled=True）：
        - key = (model, system_hash, user_hash, temperature)
        - 命中：直接返回缓存，不调 API
        - miss：调 API 并缓存响应
        """
        # 决定模型：显式 model= > task router > config.default_model
        model_name = self._resolve_model(task=task, explicit_model=model)

        # V0.24：cache lookup（命中则直接返回，不调 API）
        cache_key = self._make_cache_key(model_name, system, prompt, temperature)
        if self.config.cache_enabled and cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]
        if self.config.cache_enabled:
            self._cache_misses += 1

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
        # V0.23.5：自动应用模型完整配置（api_base + extra_body + headers）
        model_cfg = self._get_model_config(model_name)
        if model_cfg.api_base:
            kwargs["api_base"] = model_cfg.api_base
        if model_cfg.extra_body:
            kwargs["extra_body"] = model_cfg.extra_body
        if model_cfg.headers:
            kwargs["extra_headers"] = model_cfg.headers

        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content or ""

        # V0.24：cache store（仅当 cache_enabled）
        if self.config.cache_enabled:
            self._cache_store(cache_key, content)

        return content

    def _make_cache_key(
        self, model: str, system: str | None, user: str, temperature: float
    ) -> tuple[str, str, str, float]:
        """生成 cache key（V0.24）。

        key = (model, sha256(system), sha256(user), temperature)
        - hash 用 sha256 截前 16 字符（足够唯一 + 省内存）
        - None system 用空字符串
        """
        sys_h = hashlib.sha256((system or "").encode("utf-8")).hexdigest()[:16]
        usr_h = hashlib.sha256(user.encode("utf-8")).hexdigest()[:16]
        return (model, sys_h, usr_h, temperature)

    def _cache_store(self, key: tuple[str, str, str, float], content: str) -> None:
        """存储到 cache（V0.24）。

        LRU 简单实现：超过 cache_max_size 时清空（粗暴但安全）。
        """
        if len(self._cache) >= self.config.cache_max_size:
            # 简单 LRU：超过上限时清空整个 cache
            # （更精细的 LRU 需要 OrderedDict + 双向链表，V0.24 不优化）
            self._cache.clear()
        self._cache[key] = content

    def cache_stats(self) -> dict[str, Any]:
        """返回 cache 统计（V0.24）。

        用于 benchmark / 监控 cache 命中率。
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "enabled": self.config.cache_enabled,
            "size": len(self._cache),
            "max_size": self.config.cache_max_size,
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": round(hit_rate, 4),
        }

    def cache_clear(self) -> None:
        """清空 cache（V0.24）。

        用于测试或强制重新调用 API。
        """
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

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

        # V0.27 前置：anthropic 兼容模型（如 minimax-M3）不支持 instructor Pydantic schema 验证
        # 必须显式报错（V0.27 实现 transparent 分流后，WRITING 走 complete() 而非 complete_structured）
        from novel2all.core.provider_router import get_model_config as _get_cfg_for_struct

        _cfg = _get_cfg_for_struct(model_name)
        if _cfg.api_base and "anthropic" in _cfg.api_base:
            raise NotImplementedError(
                f"complete_structured() 不支持 {model_name}（Anthropic Messages API 不兼容 instructor Pydantic 验证）。"
                "请改用 complete() 返回文本，或换用 litellm 支持的模型（如 deepseek/千问）。"
            )

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

        # V0.26：应用 MODEL_CONFIG.api_base + extra_body（minimax 必须用 Anthropic 兼容）
        model_cfg = self._get_model_config(model_name)
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "response_model": response_model,
            "temperature": temperature,
            "max_retries": max_retries,
            "timeout": self.config.timeout_seconds,
        }
        if model_cfg.api_base:
            kwargs["api_base"] = model_cfg.api_base
        if model_cfg.extra_body:
            kwargs["extra_body"] = model_cfg.extra_body
        if model_cfg.headers:
            kwargs["extra_headers"] = model_cfg.headers

        result = await client.chat.completions.create(
            **kwargs,
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

        V0.24：cache 命中时直接 yield 完整 content（不调 API，零延迟）。
        """
        model_name = self._resolve_model(task=task, explicit_model=model)

        # V0.24：cache 命中 → 返回 cached stream
        cache_key = self._make_cache_key(model_name, system, prompt, temperature)
        if self.config.cache_enabled and cache_key in self._cache:
            self._cache_hits += 1
            cached_content = self._cache[cache_key]

            async def _cached_stream() -> Any:
                yield cached_content

            return _cached_stream()
        if self.config.cache_enabled:
            self._cache_misses += 1

        # litellm 由 _stream_and_cache 闭包导入（V0.24 重构）

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
        # V0.23.5：自动应用模型完整配置
        model_cfg = self._get_model_config(model_name)
        if model_cfg.api_base:
            kwargs["api_base"] = model_cfg.api_base
        if model_cfg.extra_body:
            kwargs["extra_body"] = model_cfg.extra_body
        if model_cfg.headers:
            kwargs["extra_headers"] = model_cfg.headers

        # V0.24：缓存流式响应（拼接完整内容后存）
        return self._stream_and_cache(kwargs, model_name, system, prompt, temperature)

    async def _stream_and_cache(
        self,
        kwargs: dict[str, Any],
        model_name: str,
        system: str | None,
        user: str,
        temperature: float,
    ) -> Any:
        """流式调用 + 缓存（V0.24）。

        真实流式调用 litellm，拼接完整内容后写入 cache。
        整个函数本身是 async generator（直接 yield，调用方用 async for）。
        """
        import litellm

        cache_key = self._make_cache_key(model_name, system, user, temperature)
        cache_enabled = self.config.cache_enabled
        cache_store = self._cache_store

        chunks: list[str] = []
        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            content = chunk.choices[0].delta.content or ""
            if content:
                chunks.append(content)
                yield content
        # 流结束后写入缓存
        if cache_enabled:
            full = "".join(chunks)
            cache_store(cache_key, full)

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

    def _get_model_config(self, model_name: str) -> Any:
        """V0.23.5：返回模型的完整 litellm 配置。

        通过 MODEL_CONFIG 字典统一管理 api_base / extra_body / headers。
        未知模型返回空 ModelConfig（litellm 用默认行为）。

        V0.23 旧接口 _get_extra_body 保留向后兼容（委托给 ModelConfig.extra_body）。
        """
        # lazy import 避免循环依赖
        from novel2all.core.provider_router import get_model_config

        return get_model_config(model_name)

    def _get_extra_body(self, model_name: str) -> dict[str, Any] | None:
        """V0.23：返回模型的 thinking 控制参数（extra_body）。

        向后兼容接口，V0.23.5+ 委托给 MODEL_CONFIG.extra_body。
        """
        cfg = self._get_model_config(model_name)
        return cfg.extra_body if cfg else None
