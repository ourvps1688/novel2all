"""V0.30.0a：_stream_anthropic_compat retry 测试。

V0.29.1 _call_anthropic_compat 加了 tenacity retry（连接阶段）。
V0.30.0a 把同样的 retry 模式应用到 _stream_anthropic_compat（流式）。

关键约束（与 _call_anthropic_compat 不同）：
- 流式响应是 async generator — 已 yield 的内容对外可见
- retry 不能包整个 generator（会重复 yield 已发出内容）
- V0.30.0a 设计：tenacity 只 retry "建立连接" 阶段（手动管理 stream lifecycle）
- yield 阶段失败不 retry — HTMX SSE 端自动重连

实施细节：
- 手动调 stream_ctx.__aenter__() 和 __aexit__()
- tenacity 包 _connect_with_retry() helper（只做 connect + raise_for_status）
- 失败时 cleanup（__aexit__ + aclose）
- 成功后进入 yield 阶段（不 retry）
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock

import httpx
import pytest


class FakeResponse:
    """Mock httpx Response - 用 raise_for_status 验证 2xx。"""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self._lines: list[str] = []

    def set_sse_lines(self, lines: list[str]) -> None:
        """设置 SSE 行（yield 给 aiter_lines）。"""
        self._lines = lines

    def raise_for_status(self) -> None:
        """httpx 真实行为：status >= 400 抛 HTTPStatusError。"""
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self,
            )

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aclose(self) -> None:
        return None


class FakeStreamContext:
    """Mock client.stream() 返回的 context manager — V0.30.0a 手动 __aenter__/__aexit__。"""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *args) -> None:
        return None


class FakeClient:
    """Mock httpx.AsyncClient — V0.30.0a 流式 retry 测试。"""

    captured_kwargs: ClassVar[dict] = {}

    def __init__(self, *args, **kwargs) -> None:
        self._responses: list[FakeResponse] = []
        self._call_count = 0

    def set_responses(self, responses: list[FakeResponse]) -> None:
        """设置每次 connect 返回的 response（按顺序）。"""
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def aclose(self) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs) -> FakeStreamContext:
        self._call_count += 1
        FakeClient.captured_kwargs = {"method": method, "url": url, **kwargs}
        if self._call_count <= len(self._responses):
            resp = self._responses[self._call_count - 1]
        else:
            resp = self._responses[-1] if self._responses else FakeResponse(200)
        return FakeStreamContext(resp)

    @property
    def call_count(self) -> int:
        return self._call_count


SSE_OK = [
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
    "",
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}',
    "",
    'data: {"type":"message_stop"}',
    "",
]


class TestStreamRetryV0300A:
    """V0.30.0a：_stream_anthropic_compat connect 阶段 retry。"""

    @pytest.mark.asyncio
    async def test_retry_on_transient_error_then_success(self) -> None:
        """第一次 TransportError 失败，第二次成功——应 yield 完整内容。"""
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            # 第一次抛 ConnectError，第二次成功
            fake.set_responses(
                [
                    _raising_response(httpx.ConnectError("Connection failed")),
                    _ok_response(),
                ]
            )
            chunks = await _collect_stream(
                provider,
                "minimax/MiniMax-M3",
                "https://api.minimax.cn/anthropic",
            )
            assert chunks == ["Hello", " world"]
            assert fake.call_count == 2  # 1 失败 + 1 成功

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_last_exception(self) -> None:
        """max_retries=3 共 4 次都失败 → 抛最后一次的 ConnectError。"""
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            fake.set_responses(
                [
                    _raising_response(httpx.ConnectError(f"fail #{i + 1}"))
                    for i in range(10)  # 永远失败
                ]
            )
            with pytest.raises(httpx.ConnectError) as exc_info:
                await _collect_stream(
                    provider,
                    "minimax/MiniMax-M3",
                    "https://api.minimax.cn/anthropic",
                )
            assert "fail #4" in str(exc_info.value)  # 最后一次
            assert fake.call_count == 4  # 首次 + 3 重试

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx_client_error(self) -> None:
        """4xx 客户端错误（raise_for_status 抛 HTTPStatusError）不应 retry。"""
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            fake.set_responses([_ok_response(400)])  # 400
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await _collect_stream(
                    provider,
                    "minimax/MiniMax-M3",
                    "https://api.minimax.cn/anthropic",
                )
            assert exc_info.value.response.status_code == 400
            assert fake.call_count == 1  # 4xx 不重试

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self) -> None:
        """429 限流（raise_for_status 抛 HTTPStatusError）应重试。"""
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            fake.set_responses(
                [
                    _ok_response(429),
                    _ok_response(200),
                ]
            )
            chunks = await _collect_stream(
                provider,
                "minimax/MiniMax-M3",
                "https://api.minimax.cn/anthropic",
            )
            assert chunks == ["Hello", " world"]
            assert fake.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_5xx_server_error(self) -> None:
        """5xx 服务器错误应重试。"""
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            fake.set_responses(
                [
                    _ok_response(503),
                    _ok_response(200),
                ]
            )
            chunks = await _collect_stream(
                provider,
                "minimax/MiniMax-M3",
                "https://api.minimax.cn/anthropic",
            )
            assert chunks == ["Hello", " world"]
            assert fake.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_when_max_retries_is_zero(self) -> None:
        """max_retries=0 → 只首次，不重试。"""
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=0,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            fake.set_responses([_raising_response(httpx.ConnectError("immediate"))])
            with pytest.raises(httpx.ConnectError):
                await _collect_stream(
                    provider,
                    "minimax/MiniMax-M3",
                    "https://api.minimax.cn/anthropic",
                )
            assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_yield_phase_does_not_retry(self) -> None:
        """V0.30.0a 关键约束：yield 阶段失败不 retry（避免重复输出）。

        第一次 connect 成功 + yield "Hello"，第二次 aiter_lines 抛错 → 直接抛错
        （不重试，因为重试会重复 yield "Hello"）。
        """
        from novel2all.core.provider import LLMConfig, LLMProvider

        config = LLMConfig(
            anthropic_max_retries=3,
            anthropic_retry_min_wait=0.01,
            anthropic_retry_max_wait=0.05,
        )
        provider = LLMProvider(config)

        with patch_httpx_client_stream_retry(provider) as fake:
            # connect 成功 + yield "Hello" 后 stream 中断
            resp = _ok_response_with_lines(
                [
                    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
                ],
                then_raise=httpx.RemoteProtocolError("Stream broken"),
            )
            fake.set_responses([resp])
            with pytest.raises(httpx.RemoteProtocolError):
                await _collect_stream(
                    provider,
                    "minimax/MiniMax-M3",
                    "https://api.minimax.cn/anthropic",
                )
            # connect 只 1 次（成功后不再 retry）
            assert fake.call_count == 1


# === helpers ===


def _raising_response(exc: Exception) -> FakeResponse:
    """创建一个 raise_for_status 时抛 exc 的 response（用于模拟 connect 失败）。"""
    resp = FakeResponse(500)  # 默认 500
    # 重写 raise_for_status 让它直接抛传入的异常（绕过 status code 检查）
    resp.raise_for_status = lambda: (_ for _ in ()).throw(exc)
    return resp


def _ok_response(status_code: int = 200) -> FakeResponse:
    """创建一个 raise_for_status 成功的 response + 标准 SSE 内容。"""
    resp = FakeResponse(status_code)
    resp.set_sse_lines(SSE_OK)
    return resp


def _ok_response_with_lines(lines: list[str], then_raise: Exception | None = None) -> FakeResponse:
    """成功 + yield 给定 lines，then 抛错（模拟 stream 中途断）。"""
    resp = FakeResponse(200)
    if then_raise is None:
        resp.set_sse_lines(lines)
    else:
        # 重写 aiter_lines：yield 几行后抛错
        async def aiter():
            for line in lines:
                yield line
            raise then_raise

        resp.aiter_lines = aiter
    return resp


def patch_httpx_client_stream_retry(provider):
    """context manager: patch httpx.AsyncClient 为 FakeClient。

    实际 V0.30.0a retry 实现是 tenacity 包 _connect_with_retry() 内部，
    FakeClient.stream 会被调多次（每次 retry 一次）。
    """
    from contextlib import contextmanager
    from unittest.mock import patch

    @contextmanager
    def _ctx():
        fake = FakeClient()
        with patch("httpx.AsyncClient", lambda *a, **kw: fake):
            yield fake

    return _ctx()


async def _collect_stream(provider, model_name: str, api_base: str) -> list[str]:
    """调用 _stream_anthropic_compat 收集所有 yield 的 chunk。"""
    chunks: list[str] = []
    gen = provider._stream_anthropic_compat(
        model_name=model_name,
        api_base=api_base,
        api_key="test-key",
        messages=[{"role": "user", "content": "hi"}],
        system=None,
        temperature=0.7,
        max_tokens=128,
        extra_body=None,
    )
    async for chunk in gen:
        chunks.append(chunk)
    return chunks
