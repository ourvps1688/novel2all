"""LLM Provider 抽象。

基于 LiteLLM 统一接口，支持 Anthropic / OpenAI / DeepSeek 等。

V0.29 prompt cache（真 LRU）：
- 应用层 cache（OrderedDict-based，零新依赖），key = (model, system_hash, user_hash, temperature)
- 命中时直接返回缓存 + move_to_end 更新 LRU（V0.29+ 之前是粗暴清空）
- 超过 cache_max_size 时 popitem(last=False) 淘汰最旧条目
- 设计为**透明** cache：调用方无感知，cost_estimate 自动算 cache_hit
- 适用场景：同一 system prompt + 类似 user prompt 重复调用（如 extractor 批处理章节）

V0.33 cache 后端抽象 + TTL + 持久化：
- CacheBackend Protocol（memory + json file）
- LLMProvider._cache 改为 CacheBackend 实例（不再是裸 OrderedDict）
- LLMConfig 加 cache_backend / cache_ttl_seconds / cache_persist_path 配置
- 行为保持向后兼容：默认 cache_backend="memory" + cache_ttl_seconds=0（无 TTL）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Self, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


logger = logging.getLogger(__name__)


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
    # V0.33：cache 后端选择 + TTL + 持久化
    # V0.40：新增 "sqlite" backend（OS-agnostic + 跨进程安全 + 跨 OS 共享）
    # V0.45：新增 "redis" backend（分布式 / 跨机器）
    cache_backend: str = "memory"  # "memory" | "json" | "sqlite" | "redis"
    cache_ttl_seconds: int = 0  # 0 = 永不过期；>0 = N 秒后过期
    cache_persist_path: str | None = None  # json/sqlite backend 的文件路径
    # V0.45：Redis backend 配置
    cache_redis_url: str = "redis://localhost:6379/0"  # Redis 连接 URL
    cache_redis_namespace: str = "novel2all"  # Redis key 前缀
    # V0.29.1：anthropic_compat 重试配置（用于 _call_anthropic_compat / _stream_anthropic_compat）
    # tenacity 指数退避：min_wait × 2^attempt，clamp 到 [min_wait, max_wait]
    anthropic_max_retries: int = 3  # 失败重试次数（除首次外）
    anthropic_retry_min_wait: float = 1.0  # 第一次重试前等待（秒）
    anthropic_retry_max_wait: float = 10.0  # 最长等待（秒）
    # V0.29.1：是否记录重试日志（debug 用）
    anthropic_retry_log: bool = False

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
        # V0.33：cache 后端抽象（MemoryLRUBackend / JSONFileBackend）
        # V0.40：新增 SQLiteBackend（OS-agnostic + 跨进程安全）
        # V0.45：新增 RedisBackend（分布式 / 跨机器）
        # 默认是进程内 OrderedDict 实现（行为与 V0.29 一致）；
        # 通过 LLMConfig.cache_backend / cache_persist_path 可切换到 JSON / SQLite / Redis 持久化。
        from novel2all.core.cache import (
            JSONFileBackend,
            MemoryLRUBackend,
            RedisBackend,
            SQLiteBackend,
        )

        if self.config.cache_backend == "json":
            persist_path = self.config.cache_persist_path
            if not persist_path:
                # 默认路径：.novel2all/cache.json
                persist_path = ".novel2all/cache.json"
            self._cache: Any = JSONFileBackend(
                path=Path(persist_path),
                max_size=self.config.cache_max_size,
                ttl_seconds=self.config.cache_ttl_seconds,
            )
        elif self.config.cache_backend == "sqlite":
            # V0.40：SQLite 持久化（跨 OS + 跨进程安全 + ACID）
            persist_path = self.config.cache_persist_path
            if not persist_path:
                # 默认路径：.novel2all/cache.db
                persist_path = ".novel2all/cache.db"
            self._cache = SQLiteBackend(
                path=Path(persist_path),
                max_size=self.config.cache_max_size,
                ttl_seconds=self.config.cache_ttl_seconds,
            )
        elif self.config.cache_backend == "redis":
            # V0.45：Redis 分布式 cache（跨机器 / 跨进程）
            self._cache = RedisBackend(
                url=self.config.cache_redis_url,
                max_size=self.config.cache_max_size,
                ttl_seconds=self.config.cache_ttl_seconds,
                namespace=self.config.cache_redis_namespace,
            )
        else:
            # "memory"（默认）
            self._cache = MemoryLRUBackend(
                max_size=self.config.cache_max_size,
                ttl_seconds=self.config.cache_ttl_seconds,
            )

        # V0.30.6 C1：Prompt prefix cache 跟踪器（独立于 response cache）
        # 跟踪 sys_hash 复用次数，量化 prompt prefix cache 节省的 ¥
        from novel2all.core.prompt_cache_tracker import PromptCacheTracker

        self._prompt_tracker = PromptCacheTracker()

        # V0.30.6 C3 收尾：AdaptiveRouter 集成（按历史自动选最佳模型）
        # 注意：默认 None，由 init_adaptive_router() 显式启用（web lifespan 或测试）
        self._adaptive_router: Any = None

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

        # V0.33：cache lookup（通过 CacheBackend.get，命中则直接返回 + 自动 LRU 更新）
        cache_key = self._make_cache_key(model_name, system, prompt, temperature)
        # V0.30.6 C1：sys_hash 记录已在 _make_cache_key() 内部完成
        if self.config.cache_enabled:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

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

        V0.30.6 C1：同时记录到 _prompt_tracker，统计 sys_hash 复用。
        这样无论调用方是否实际查 cache（cache_enabled=False），
        都能跟踪 prompt prefix 复用次数。
        """
        sys_h = hashlib.sha256((system or "").encode("utf-8")).hexdigest()[:16]
        usr_h = hashlib.sha256(user.encode("utf-8")).hexdigest()[:16]
        # V0.30.6 C1：prompt prefix cache tracking（与 response cache 解耦）
        self._prompt_tracker.record(sys_h)
        return (model, sys_h, usr_h, temperature)

    def _cache_store(self, key: tuple[str, str, str, float], content: str) -> None:
        """存储到 cache（V0.33：通过 CacheBackend.set，LRU/TTL 由后端管理）。

        V0.29 真 LRU + V0.33 TTL + 持久化 → 全部委托给 self._cache 后端。
        """
        self._cache.set(key, content)

    def cache_stats(self) -> dict[str, Any]:
        """返回 cache 统计（V0.33：通过 CacheBackend.stats）。

        V0.33 扩展：增加 backend / ttl_seconds / persist_path 字段，
        让 /api/cache/stats 面板能展示后端类型。
        V0.30.6 C1：增加 prompt_prefix 子字典，量化 prefix cache 节省的 ¥。
        """
        stats = self._cache.stats()
        # V0.33：补充 cache_enabled（后端 stats 假设 enabled=True）
        stats["enabled"] = self.config.cache_enabled
        # V0.30.6 C1：增加 prompt prefix cache 统计
        stats["prompt_prefix"] = self._prompt_tracker.to_dict()
        return stats

    def prompt_cache_stats(self) -> dict[str, Any]:
        """V0.30.6 C1：返回 prompt prefix cache 专用统计。

        与 cache_stats()["prompt_prefix"] 字段等价，但更直接。
        供 /api/cache/prompt-stats 端点和 Web UI 调用。
        """
        return self._prompt_tracker.to_dict()

    def reset_prompt_cache_stats(self) -> None:
        """V0.30.6 C1：重置 prompt prefix cache 统计（用于测试或手动 reset）。"""
        self._prompt_tracker.reset()

    @property
    def _cache_hits(self) -> int:
        """V0.33 向后兼容：暴露 backend 的 hits（部分测试用此属性）。"""
        return getattr(self._cache, "_hits", 0)

    @_cache_hits.setter
    def _cache_hits(self, value: int) -> None:
        if hasattr(self._cache, "_hits"):
            self._cache._hits = value

    @property
    def _cache_misses(self) -> int:
        """V0.33 向后兼容：暴露 backend 的 misses。"""
        return getattr(self._cache, "_misses", 0)

    @_cache_misses.setter
    def _cache_misses(self, value: int) -> None:
        if hasattr(self._cache, "_misses"):
            self._cache._misses = value

    def cache_clear(self) -> None:
        """清空 cache（V0.33：通过 CacheBackend.clear，hits/misses 一并重置）。"""
        self._cache.clear()

    def close(self) -> None:
        """V0.42：显式关闭 cache backend（释放 SQLite 连接池等资源）。

        推荐在应用退出时调用（FastAPI lifespan / context manager）。
        MemoryLRU / JSONFile 暂为 no-op，SQLite 会关闭所有池中连接。
        """
        if hasattr(self._cache, "close"):
            self._cache.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

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
        from novel2all.core.provider_router import (
            MODEL_CONFIG,
        )
        from novel2all.core.provider_router import (
            get_model_config as _get_cfg_for_struct,
        )

        _cfg = _get_cfg_for_struct(model_name)
        if _cfg.api_base and "anthropic" in _cfg.api_base:
            # V0.29.5：动态列出可用替代模型（数据驱动，不写死）
            alternatives = [
                name
                for name, cfg in MODEL_CONFIG.items()
                if not (cfg.api_base and "anthropic" in cfg.api_base)
            ]
            alternatives_str = (
                chr(10).join(f"  - {m}" for m in alternatives) if alternatives else "  (无)"
            )
            raise NotImplementedError(
                f"complete_structured() 不支持 {model_name}（V0.27 transparent 分流走 httpx 调 /v1/messages，"
                f"Anthropic Messages API 不兼容 instructor Pydantic 验证）。"
                + chr(10)
                + chr(10)
                + "可用的支持结构化输出的模型（从 MODEL_CONFIG 自动筛选）："
                + chr(10)
                + alternatives_str
                + chr(10)
                + chr(10)
                + "两种解决方案："
                + chr(10)
                + "  1. 切到上述支持的模型：provider.complete_structured(model='deepseek/deepseek-flash', ...)"
                + chr(10)
                + f"  2. 改用 complete() 返回文本 + 自己解析 JSON：provider.complete(model='{model_name}', ...) + json.loads(content)"
                + chr(10)
                + chr(10)
                + "参考：docs/llm-providers-truth.md §15（V0.27 transparent 分流）"
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

        # V0.30.6 C1：sys_hash 记录已在 _make_cache_key() 内部完成
        # V0.33：cache 命中 → 返回 cached stream（通过 CacheBackend.get）
        cache_key = self._make_cache_key(model_name, system, prompt, temperature)
        if self.config.cache_enabled:
            cached_content = self._cache.get(cache_key)
            if cached_content is not None:

                async def _cached_stream() -> Any:
                    yield cached_content

                return _cached_stream()

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
        2. V0.30.6 C3：task 参数 + AdaptiveRouter（按历史自动选最佳）
        3. task 参数 + ModelRouter（V0.22.5+ 静态路由）
        4. config.default_model（向后兼容）
        """
        if explicit_model:
            return explicit_model
        if task is not None:
            # lazy import 避免循环依赖
            from novel2all.core.provider_router import ModelRouter, TaskType

            if not isinstance(task, TaskType):
                # 容错：非 TaskType 实例就当作普通 model name 处理
                return str(task)

            # V0.30.6 C3：优先用 AdaptiveRouter（数据驱动，按历史选最佳）
            #   - 冷启动（样本 < min_samples）→ fall back to ModelRouter
            #   - 避免硬依赖：若 adaptive_router 未初始化（测试场景），fall back
            try:
                if hasattr(self, "_adaptive_router") and self._adaptive_router is not None:
                    return self._adaptive_router.select(task)
            except Exception:
                # AdaptiveRouter 失败 → fall back to ModelRouter（V0.23）
                pass

            router = ModelRouter(self.config)
            return router.select(task)
        return self.config.default_model

    def _record_adaptive_run(
        self,
        task: Any,
        model: str,
        *,
        success: bool,
        latency_ms: float,
        quality_score: float | None = None,
    ) -> None:
        """V0.30.6 C3：记录一次 LLM 调用到 AdaptiveRouter（用于下次 select）。"""
        try:
            from novel2all.core.provider_router import TaskType

            if not isinstance(task, TaskType):
                return  # 仅 TaskType 才记录
            if hasattr(self, "_adaptive_router") and self._adaptive_router is not None:
                self._adaptive_router.record_run(
                    task,
                    model,
                    success=success,
                    latency_ms=latency_ms,
                    quality_score=quality_score,
                )
        except Exception:
            pass  # 记录失败不影响主流程

    def init_adaptive_router(
        self,
        default_model: str | None = None,
        strategy: str | None = None,
        min_samples: int | None = None,
        window_size: int | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        """V0.30.6 C3：初始化 AdaptiveRouter（在 lifespan 中调用）。

        不调用则 V0.23 ModelRouter 静态路由生效（向后兼容）。
        """
        from novel2all.core.adaptive_router import (
            AdaptiveRouter,
            AdaptiveStrategy,
        )

        kwargs = {
            "default_model": default_model or self.config.default_model,
            "db_path": Path(db_path) if db_path else Path(".novel2all/adaptive_routing.db"),
        }
        if strategy:
            kwargs["strategy"] = AdaptiveStrategy(strategy)
        if min_samples:
            kwargs["min_samples"] = min_samples
        if window_size:
            kwargs["window_size"] = window_size
        self._adaptive_router = AdaptiveRouter(**kwargs)
        logger.info("V0.30.6 C3: AdaptiveRouter initialized (default=%s)", kwargs["default_model"])

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
        """V0.28：从 MODEL_CONFIG 读 anthropic 兼容端点的 API key 环境变量。

        V0.28 重构：之前是硬编码 "minimax"/"anthropic"/"claude" 启发式匹配；
        改为读 MODEL_CONFIG[model_name].api_key_env 字段（数据驱动）。
        新增 anthropic_compat provider 只需在 MODEL_CONFIG 加 api_key_env 字段，
        无需改本函数。

        Returns:
            API key 字符串，未设置则返回 None。
        """
        model_cfg = self._get_model_config(model_name)
        if not model_cfg.api_key_env:
            return None
        return os.environ.get(model_cfg.api_key_env)

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

        # V0.29.1：tenacity 异步重试 + 指数退避
        # 重试策略：网络错误 + 5xx + 429 都重试，其他 4xx 不重试（客户端错误）
        # max_retries=3 → 总尝试 4 次（首次 + 3 重试）
        from tenacity import (
            AsyncRetrying,
            RetryError,
            retry_if_exception,
            stop_after_attempt,
            wait_exponential,
        )

        def _should_retry(exc: BaseException) -> bool:
            """重试条件：网络错误 + 5xx + 429（其他 4xx 不重试）。"""
            if isinstance(exc, httpx.TransportError):
                return True  # 连接超时、DNS 失败、断开等
            if isinstance(exc, httpx.HTTPStatusError):
                # 5xx 服务器错误 + 429 限流 → 重试
                return exc.response.status_code >= 500 or exc.response.status_code == 429
            return False

        retry_dec = stop_after_attempt(1 + self.config.anthropic_max_retries)
        wait_dec = wait_exponential(
            multiplier=self.config.anthropic_retry_min_wait,
            max=self.config.anthropic_retry_max_wait,
        )

        last_exc: BaseException | None = None
        try:
            async for attempt in AsyncRetrying(
                stop=retry_dec,
                wait=wait_dec,
                retry=retry_if_exception(_should_retry),
                reraise=True,
            ):
                with attempt:
                    if self.config.anthropic_retry_log:
                        logger.debug(
                            "[_call_anthropic_compat] attempt #%d",
                            attempt.retry_state.attempt_number,
                        )
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
        except RetryError as e:
            # tenacity 在最后一次重试失败后抛 RetryError（reraise=True 把原始异常放 __cause__）
            last_exc = e.last_attempt.exception()
            if last_exc is not None:
                raise last_exc from None
            raise

        # 不可达（AsyncRetrying 必须返回或抛）
        raise RuntimeError("unreachable: AsyncRetrying 应当返回或抛 RetryError")

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

        V0.30.0a：tenacity retry "建立连接" 阶段（connect + raise_for_status）
        - 网络抖动（连接超时/5xx/429）→ 重试
        - stream yield 阶段失败 → **不重试**（重试会重复输出已 yield 的内容）
        - HTMX 端 SSE 自动重连处理"stream 中断"

        Yields:
            text_delta 字符串（拼起来即完整响应）。
        """
        import httpx
        from tenacity import (
            AsyncRetrying,
            retry_if_exception,
            stop_after_attempt,
            wait_exponential,
        )

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

        def _should_retry(exc: BaseException) -> bool:
            """V0.30.0a：连接阶段重试条件（同 _call_anthropic_compat V0.29.1）。

            - TransportError（连接超时/DNS 失败/断开）：重试
            - HTTPStatusError 5xx：重试
            - HTTPStatusError 429：重试
            - 其他 4xx：不重试
            """
            if isinstance(exc, httpx.TransportError):
                return True
            if isinstance(exc, httpx.HTTPStatusError):
                return exc.response.status_code >= 500 or exc.response.status_code == 429
            return False

        # V0.30.0a：tenacity retry "建立连接" 阶段（不动 yield 部分）
        # 手动管理 stream lifecycle（__aenter__ + __aexit__）让 connect 阶段能 retry
        async def _connect_with_retry() -> tuple[httpx.AsyncClient, Any, httpx.Response]:
            """connect 阶段（retry 包内）：
            - 1. 建 client
            - 2. __aenter__ stream（建 HTTP 连接）
            - 3. raise_for_status（验证 2xx）
            - 4. 返回 (client, stream_ctx, resp) — 外层会负责 __aexit__

            失败时 tenacity 重新调用，旧的 (client, stream_ctx) 在 __aexit__ 关闭。
            """
            client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
            stream_ctx = client.stream("POST", url, json=body, headers=headers)
            resp = await stream_ctx.__aenter__()
            try:
                resp.raise_for_status()
            except BaseException:
                # raise_for_status 失败：清理 stream_ctx + client
                try:
                    await stream_ctx.__aexit__(None, None, None)
                finally:
                    try:
                        await client.aclose()
                    except Exception:
                        pass
                raise
            return client, stream_ctx, resp

        retry_dec = stop_after_attempt(1 + self.config.anthropic_max_retries)
        wait_dec = wait_exponential(
            multiplier=self.config.anthropic_retry_min_wait,
            max=self.config.anthropic_retry_max_wait,
        )

        client: httpx.AsyncClient | None = None
        stream_ctx: Any = None
        resp: httpx.Response | None = None
        try:
            async for attempt in AsyncRetrying(
                stop=retry_dec,
                wait=wait_dec,
                retry=retry_if_exception(_should_retry),
                reraise=True,
            ):
                with attempt:
                    if self.config.anthropic_retry_log:
                        logger.debug(
                            "[_stream_anthropic_compat] connect attempt #%d",
                            attempt.retry_state.attempt_number,
                        )
                    client, stream_ctx, resp = await _connect_with_retry()
        except BaseException:
            # tenacity 把原异常重抛（reraise=True）
            # 兜底清理（_connect_with_retry 内部已尽量清理）
            if stream_ctx is not None:
                try:
                    await stream_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass
            raise

        # 此时 resp 已成功（status 2xx）— 进入 yield 阶段（不 retry）
        # V0.30.0a 限制：yield 阶段失败（如网络中断）不 retry（避免重复输出已 yield 内容）
        # HTMX SSE 自动重连（前端层面）处理这种 case
        assert resp is not None  # type guard（retry 成功时一定设了）
        try:
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
        finally:
            # 清理：先 __aexit__ stream_ctx，再 aclose client
            assert stream_ctx is not None and client is not None  # type guard
            try:
                await stream_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                await client.aclose()
            except Exception:
                pass
