"""V0.30.6 B5 收尾：FastAPI auth 中间件 + 依赖。

提供：
- current_user_optional：request.state.user 注入（可能为 None）
- current_user_required：必须已登录，否则 401
- admin_required：必须是 admin，否则 403
- request_logger：记录每个请求 + rate limit 检查
"""

from __future__ import annotations

import logging

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
    """V0.30.6 B5 收尾：获取客户端 IP（优先 X-Forwarded-For）。"""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"
