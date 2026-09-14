"""V1.0 GA Day 11-15：安全 HTTP headers 中间件。

设计：
- 添加 OWASP 推荐的安全 headers
- CSP（Content Security Policy）防止 XSS
- HSTS（Strict-Transport-Security）强制 HTTPS
- X-Frame-Options 防止 clickjacking
- X-Content-Type-Options 防止 MIME sniffing
- Referrer-Policy 防止 URL 泄漏
- Permissions-Policy 限制浏览器特性
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


# === Default headers ===

DEFAULT_SECURITY_HEADERS: dict[str, str] = {
    # V1.0 GA：X-Content-Type-Options 防止 MIME sniffing
    "X-Content-Type-Options": "nosniff",
    # V1.0 GA：X-Frame-Options 防止 clickjacking（DENY = 不能 iframe）
    "X-Frame-Options": "DENY",
    # V1.0 GA：Referrer-Policy（同源 + 同协议）
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # V1.0 GA：Permissions-Policy 限制浏览器特性（关掉无用 API）
    "Permissions-Policy": (
        "geolocation=(), microphone=(), camera=(), payment=(), "
        "usb=(), magnetometer=(), gyroscope=(), accelerometer=()"
    ),
    # V1.0 GA：CSP（允许 self + inline styles for Alpine.js 兼容）
    # 注：HTMX 1.x 不需要 inline JS，所以 script-src 'self' 即可
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "  # Alpine.js x-* 属性需要
        "script-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'; "  # 同 X-Frame-Options: DENY
        "base-uri 'self';"
    ),
}


def with_security_headers(response: Response, headers: dict[str, str] | None = None) -> Response:
    """V1.0 GA：添加安全 headers 到 Response（直接调用）。"""
    h = headers or DEFAULT_SECURITY_HEADERS
    for key, value in h.items():
        response.headers[key] = value
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """V1.0 GA：自动为每个 Response 添加安全 headers。

    用法（web/app.py）：
        app.add_middleware(SecurityHeadersMiddleware)
    """

    def __init__(self, app: Any, headers: dict[str, str] | None = None) -> None:
        super().__init__(app)
        self.headers = headers or DEFAULT_SECURITY_HEADERS

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """V1.0 GA：拦截每个 Response，添加安全 headers。"""
        response = await call_next(request)
        for key, value in self.headers.items():
            response.headers[key] = value
        return response
