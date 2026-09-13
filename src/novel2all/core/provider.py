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
import json
import os
from collections.abc import AsyncIterator
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

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # V0.27 transparent 分流：Anthropic Messages API 兼容路径（minimax 等）
        if self._is_anthropic_compat(model_name):
            model_cfg = self._get_model_config(model_name)
            api_key = self._anthropic_api_key_for(model_name)
            if not api_key:
                raise ValueError(
                    f"{model_name} requires API key but not set in environment "
                    f"(expected MINIMAX_API_KEY or ANTHROPIC_API_KEY)"
                )
            content = await self._call_anthropic_compat(
                model_name=model_name,
                api_base=model_cfg.api_base,  # 已由 _is_anthropic_compat 保证非 None
                api_key=api_key,
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=model_cfg.extra_body,
            )
            if self.config.cache_enabled:
                self._cache_store(cache_key, content)
            return content

        try:
            import litellm
        except ImportError as e:
            raise ImportError("Please install litellm: `uv add litellm`") from e

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

        # V0.27 transparent 分流：Anthropic Messages API 兼容路径
        if self._is_anthropic_compat(model_name):
            model_cfg = self._get_model_config(model_name)
            api_key = self._anthropic_api_key_for(model_name)
            if not api_key:
                raise ValueError(
                    f"{model_name} requires API key but not set in environment "
                    f"(expected MINIMAX_API_KEY or ANTHROPIC_API_KEY)"
                )
            return self._stream_anthropic_and_cache(
                model_name=model_name,
                api_base=model_cfg.api_base,
                api_key=api_key,
                messages=messages,
                system=system,
                temperature=temperature,
                extra_body=model_cfg.extra_body,
                cache_key=cache_key,
            )

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

    async def _stream_anthropic_and_cache(
        self,
        *,
        model_name: str,
        api_base: str,
        api_key: str,
        messages: list[dict[str, str]],
        system: str | None,
        temperature: float,
        max_tokens: int = 4096,
        extra_body: dict[str, Any] | None = None,
        cache_key: tuple[str, str, str, float] | None = None,
    ) -> AsyncIterator[str]:
        """V0.27：流式 httpx 调 Anthropic Messages API + 缓存。

        与 _stream_and_cache 对称：拼接完整内容后写入 cache。
        调用方用 async for 消费。
        """
        cache_enabled = self.config.cache_enabled
        cache_store = self._cache_store

        chunks: list[str] = []
        async for text in self._stream_anthropic_compat(
            model_name=model_name,
            api_base=api_base,
            api_key=api_key,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        ):
            chunks.append(text)
            yield text
        # 流结束后写入缓存
        if cache_enabled and cache_key is not None:
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

    # === V0.27 transparent 分流：Anthropic Messages API 兼容路径 ===
    # 背景：minimax-M3 必须用 Anthropic Messages API（国内端点 api.minimax.cn/anthropic），
    # 但 litellm 默认拼 /v1/chat/completions → 404。instructor 走 litellm → 同样 404。
    # 解法：LLMProvider 检测 api_base 含 "anthropic" 时，绕过 litellm，直接 httpx 调 /v1/messages。
    # 调用方无需任何改动（仍传 model="minimax/MiniMax-M3"），透明分流。

    def _is_anthropic_compat(self, model_name: str) -> bool:
        """V0.27：判断模型是否走 Anthropic Messages API 兼容端点。

        规则：MODEL_CONFIG[model].api_base 含 "anthropic"。
        适用：minimax-M3（国内 Anthropic 兼容端点 api.minimax.cn/anthropic）。
        未来：其他国内 Anthropic 镜像也可走此路径（如 claude 国内代理）。

        Returns:
            True = 走 _call_anthropic_compat()（httpx 直接调 /v1/messages）
            False = 走 litellm.acompletion()（OpenAI 兼容 / 默认）
        """
        cfg = self._get_model_config(model_name)
        return bool(cfg.api_base and "anthropic" in cfg.api_base)

    def _anthropic_api_key_for(self, model_name: str) -> str | None:
        """V0.27：从环境变量读 anthropic 兼容端点的 API key。

        规则（按 model_name 启发式，未来可改为 MODEL_CONFIG 加字段）：
        - "minimax" in model_name → MINIMAX_API_KEY
        - "anthropic"/"claude" in model_name → ANTHROPIC_API_KEY
        - 其他 anthropic_compat 模型 → 返回 None（调用方需显式提供）

        Returns:
            API key 字符串，未设置则返回 None。
        """
        name_lower = model_name.lower()
        if "minimax" in name_lower:
            return os.environ.get("MINIMAX_API_KEY")
        if "anthropic" in name_lower or "claude" in name_lower:
            return os.environ.get("ANTHROPIC_API_KEY")
        return None

    async def _call_anthropic_compat(
        self,
        *,
        model_name: str,
        api_base: str,
        api_key: str,
        messages: list[dict[str, str]],
        system: str | None,
        temperature: float,
        max_tokens: int,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        """V0.27：直接 httpx 调 Anthropic Messages API（/v1/messages）。

        绕过 litellm 默认拼 `/v1/chat/completions` 路径导致的 404 bug。
        适用：minimax-M3 等使用 Anthropic Messages API 协议但 litellm 不识别的 provider。

        Body 格式（Anthropic 规范）：
        - model 字段去掉 provider 前缀（如 "minimax/MiniMax-M3" → "MiniMax-M3"）
        - system 在 body 顶层（不在 messages 里）
        - messages 只含 user/assistant（不含 system）

        Returns:
            response.content[].text 拼接的字符串。
        """
        import httpx

        # 去掉 provider 前缀（Anthropic Messages API 不认 "minimax/"）
        bare_model = model_name.split("/", 1)[-1] if "/" in model_name else model_name

        # 过滤掉 system messages（Anthropic 用顶层 system 字段）
        user_messages = [
            {"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"
        ]

        body: dict[str, Any] = {
            "model": bare_model,
            "max_tokens": max_tokens,
            "messages": user_messages,
            "temperature": temperature,
        }
        if system:
            body["system"] = system
        # extra_body 合并（如 {"thinking": {"type": "disabled"}}）
        if extra_body:
            body.update(extra_body)

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        url = api_base.rstrip("/") + "/v1/messages"
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Anthropic 响应：content 是数组，每个 element.type="text" 含 text 字段
        content_blocks = data.get("content", [])
        parts: list[str] = []
        for blk in content_blocks:
            if blk.get("type") == "text":
                parts.append(blk.get("text", ""))
        return "".join(parts)

    async def _stream_anthropic_compat(
        self,
        *,
        model_name: str,
        api_base: str,
        api_key: str,
        messages: list[dict[str, str]],
        system: str | None,
        temperature: float,
        max_tokens: int,
        extra_body: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """V0.27：流式 httpx 调 Anthropic Messages API（SSE 事件流）。

        SSE 事件格式：
        - content_block_delta: data.delta.type="text_delta", data.delta.text="..."
        - 其他事件（message_start/content_block_start/content_block_stop/message_stop）忽略

        Yields:
            text_delta 字符串（拼起来即完整响应）。
        """
        import httpx

        bare_model = model_name.split("/", 1)[-1] if "/" in model_name else model_name
        user_messages = [
            {"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"
        ]

        body: dict[str, Any] = {
            "model": bare_model,
            "max_tokens": max_tokens,
            "messages": user_messages,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            body["system"] = system
        if extra_body:
            body.update(extra_body)

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        url = api_base.rstrip("/") + "/v1/messages"
        async with (
            httpx.AsyncClient(timeout=self.config.timeout_seconds) as client,
            client.stream("POST", url, json=body, headers=headers) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[len("data: ") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    evt = json.loads(data_str)
                except Exception:  # SSE 容错：忽略非 JSON 行
                    continue
                # content_block_delta 事件：delta.type="text_delta", delta.text="..."
                if evt.get("type") == "content_block_delta":
                    delta = evt.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield text
