"""V1.0 GA 性能优化：httpx AsyncClient 连接池。

问题：当前每次 LLM 调用都新建 httpx.AsyncClient，浪费 TCP 握手 / TLS 握手成本（~100-500ms）。

解决：复用 AsyncClient（httpx 内部连接池 + HTTP/2 + keep-alive）。

设计：
- 每 provider (api_base) 共享一个 AsyncClient
- Lazy init（首次调用时创建）
- lifespan 关闭时清理（call aclose()）
- 零外部依赖：stdlib asyncio + httpx
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HttpxConnectionPool:
    """V1.0 GA：httpx AsyncClient 连接池（每 api_base 一个 client）。"""

    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()

    async def get_client(
        self,
        api_base: str,
        *,
        timeout: float = 60.0,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ) -> httpx.AsyncClient:
        """V1.0 GA：获取（或创建）api_base 对应的 AsyncClient。

        Args:
            api_base: API 基础 URL
            timeout: 请求超时（秒）
            max_connections: 最大连接数
            max_keepalive_connections: keep-alive 连接数

        Returns:
            复用的 httpx.AsyncClient
        """
        async with self._lock:
            if api_base in self._clients:
                return self._clients[api_base]

            # V1.0 GA：连接池配置（httpx 默认是 100 keepalive，足够大多数工作负载）
            limits = httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            )
            client = httpx.AsyncClient(
                base_url=api_base,
                timeout=timeout,
                limits=limits,
                # V1.0 GA：启用 HTTP/2（如果 provider 支持）
                # http2=True,  # 默认关闭，避免某些 provider 不支持
            )
            self._clients[api_base] = client
            logger.debug(
                "V1.0 GA: created httpx pool for %s (max_conn=%d)", api_base, max_connections
            )
            return client

    async def close_all(self) -> None:
        """V1.0 GA：关闭所有 client（lifespan 退出时调用）。"""
        async with self._lock:
            for api_base, client in list(self._clients.items()):
                try:
                    await client.aclose()
                    logger.debug("V1.0 GA: closed httpx pool for %s", api_base)
                except Exception as e:
                    logger.warning("V1.0 GA: close failed for %s: %s", api_base, e)
            self._clients.clear()

    def get_stats(self) -> dict[str, Any]:
        """V1.0 GA：返回当前池状态（用于监控）。"""
        return {
            "num_clients": len(self._clients),
            "api_bases": list(self._clients.keys()),
        }
