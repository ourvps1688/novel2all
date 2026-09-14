"""V0.30.6 B5 收尾：FastAPI auth 中间件 + 依赖。

提供：
- current_user_optional：request.state.user 注入（可能为 None）
- current_user_required：必须已登录，否则 401
- admin_required：必须是 admin，否则 403
- request_logger：记录每个请求 + rate limit 检查
"""

from __future__ import annotations

import ipaddress
import logging
import os
import threading
from typing import ClassVar

from fastapi import HTTPException, Request

from novel2all.core.auth import User

logger = logging.getLogger(__name__)


# === Helpers ===


def get_request_user(request: Request) -> User | None:
    """V0.30.6 B5 收尾：从 request.state 取当前用户（可能 None）。"""
    return getattr(request.state, "user", None)


def get_request_session_id(request: Request) -> str | None:
    """V0.30.6 B5 收尾：从 request.state 取当前 session ID。"""
    return getattr(request.state, "session_id", None)


# === V1.0.1 B5：Trusted proxies (CIDR-based, env-configurable) ===

# 模块级缓存（lazy init + threading.Lock）
_TRUSTED_PROXY_NETWORKS: ClassVar[list[ipaddress._BaseNetwork]] = []
_TRUSTED_PROXIES_LOCK: ClassVar[threading.Lock] = threading.Lock()


def _parse_trusted_proxies() -> list[ipaddress._BaseNetwork]:
    """V1.0.1 B5：解析 TRUSTED_PROXIES 环境变量为 CIDR 列表。

    优先级：
      1. ``TRUSTED_PROXIES``（标准约定）
      2. ``NOVEL2ALL_TRUSTED_PROXIES``（项目专属 fallback）

    格式：逗号分隔的 CIDR（IPv4 / IPv6）或单 IP。
    示例：``TRUSTED_PROXIES="10.0.0.0/8,127.0.0.1/32,::1"``

    解析失败的单条会被跳过（log warning），避免整个函数崩溃。
    空字符串 / 未设置 → 返回 []（即不信任任何代理）。
    """
    raw = os.environ.get("TRUSTED_PROXIES")
    if raw is None:
        raw = os.environ.get("NOVEL2ALL_TRUSTED_PROXIES", "")
    if not raw:
        return []

    networks: list[ipaddress._BaseNetwork] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning("V1.0.1 B5: invalid TRUSTED_PROXIES entry skipped: %s", token)
    return networks


def _get_trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    """V1.0.1 B5：惰性加载 trusted proxy CIDR 列表（thread-safe）。"""
    global _TRUSTED_PROXY_NETWORKS
    with _TRUSTED_PROXIES_LOCK:
        if not _TRUSTED_PROXY_NETWORKS:
            _TRUSTED_PROXY_NETWORKS = _parse_trusted_proxies()
        return list(_TRUSTED_PROXY_NETWORKS)


def reset_trusted_proxy_cache() -> None:
    """V1.0.1 B5：清除 trusted proxy 缓存（仅测试使用）。"""
    global _TRUSTED_PROXY_NETWORKS
    with _TRUSTED_PROXIES_LOCK:
        _TRUSTED_PROXY_NETWORKS = []


def _client_ip_in_trusted(ip_str: str) -> bool:
    """V1.0.1 B5：判断 client IP 是否在 trusted proxy 列表中。"""
    networks = _get_trusted_proxy_networks()
    if not networks:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip_obj in net for net in networks)


# === FastAPI dependencies ===


async def current_user_optional(request: Request) -> User | None:
    """V0.30.6 B5 收尾：注入当前用户（可选，未登录返回 None）。

    中间件会先调用这个把 user 注入 request.state。
    """
    return get_request_user(request)


async def current_user_required(request: Request) -> User:
    """V0.30.6 B5 收尾：必须已登录（未登录 → 401）。"""
    user = get_request_user(request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please login via POST /api/auth/login.",
        )
    return user


async def admin_required(request: Request) -> User:
    """V0.30.6 B5 收尾：必须是 admin（否则 403）。"""
    user = await current_user_required(request)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=f"Admin role required (current: {user.role})",
        )
    return user


async def get_client_ip(request: Request) -> str:
    """V1.0.1 B5 + V1.0.1 QA fix：获取客户端 IP（仅当直接客户端是 trusted proxy 时才采信 XFF）。

    安全模型：
      - 默认（``TRUSTED_PROXIES`` 未设置）→ 完全忽略 ``X-Forwarded-For``，
        始终使用 ``request.client.host``。这避免了"任意客户端伪造 XFF 冒用
        上游 IP"的 spoofing 风险。
      - 当 ``TRUSTED_PROXIES`` 配置了 CIDR（如 ``127.0.0.1/32``、
        ``10.0.0.0/8``）→ 仅当 ``request.client.host`` 落在 trusted CIDR 内时
        才信任 XFF 的最左侧地址；否则继续使用直连 IP。
      - **V1.0.1 QA fix**：XFF 首条若不是合法 IP（``ipaddress.ip_address()`` 抛
        ``ValueError``），则 fallback 到 ``direct_ip``，**绝不**把垃圾字符串
        当 IP 返回（防 XFF 注入 / 字符串污染日志）。

    Returns:
        客户端 IP 字符串（合法 XFF 首条 / 直连 host / ``"127.0.0.1"`` 三选一）。
    """
    direct_ip = request.client.host if request.client else "127.0.0.1"

    if not _client_ip_in_trusted(direct_ip):
        # 直接客户端不在 trusted 列表 → 不采信任何 XFF
        return direct_ip

    # trusted proxy 链：取最左（非最右）条目（典型 RFC 7239 约定）
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            # V1.0.1 QA fix：验证 XFF entry 是合法 IP，无效时 fallback。
            # 这是关键的"input validation"步骤 — 否则恶意代理可以塞进
            # "not-an-ip-address" 之类的字符串污染我们的 IP 日志 / 限流 key。
            try:
                ipaddress.ip_address(first)
                return first
            except ValueError:
                logger.warning(
                    "V1.0.1 QA fix: invalid XFF entry %r, falling back to direct IP %s",
                    first,
                    direct_ip,
                )
    return direct_ip
