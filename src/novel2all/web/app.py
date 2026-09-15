"""novel2all Web UI（FastAPI + V1.5 React SPA）。

v0.20 基础：项目状态 + skill 列表 + role 列表 + tracking state
v0.21 Step 3：SSE 流式写作端点 + 前端实时显示
v1.5 React 迁移：移除 Jinja2Templates，改为 mount V1.5 React dist/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.auth_middleware import (
    admin_required,
    get_client_ip,
    get_request_session_id,
    get_request_user,
)
from novel2all.core.memory import MemoryManager, Tracker
from novel2all.core.pipeline import (
    BlockingIssuesError,
    OutlineNotFoundError,
    PipelineCancelledError,
    WritingPipeline,
)
from novel2all.core.project import ProjectStructure
from novel2all.core.role import RoleRegistry
from novel2all.core.skill import SkillRegistry

logger = logging.getLogger(__name__)

# === SSE 工具函数 ===


def sse_event(event: str, data: dict[str, Any]) -> str:
    """格式化为 SSE 事件字符串。

    格式：
        event: <event>
        data: <json>

        （以 \\n\\n 结束）
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# === V1.0.1 B1：dev mode detection ===
def _is_dev_mode() -> bool:
    """V1.0.1 B1：判断是否处于 dev 模式（HTTP，非 HTTPS）。

    返回 True 时，session cookie 的 ``secure`` 标志必须为 False
    （否则浏览器会拒收 cookie，导致 session 丢失）。

    优先级：
      1. ``NOVEL2ALL_DEBUG`` 环境变量（项目专属）
      2. ``DEBUG`` 环境变量（通用约定）

    任何能解析为真值的值（"1", "true", "yes", "on"）都视为 dev mode。
    默认行为：``True``（即无环境变量时按 dev 处理，避免 HTTP 下 cookie 失效）。

    注意：空字符串 / 未设置 → True（dev mode）。要显式启用 prod，
    必须设置 ``NOVEL2ALL_DEBUG=false`` 或 ``DEBUG=false``。
    """
    raw = os.environ.get("NOVEL2ALL_DEBUG")
    if raw is None:
        raw = os.environ.get("DEBUG")
    if raw is None:
        return True  # 默认 dev mode（避免本地 HTTP cookie 失效）
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# === V1.0.1 B8：Idempotency store（thread-safe + TTL + in-flight claim） ===
class InMemoryIdempotencyStore:
    """V1.0.1 B8：内存版 idempotency store（threading.Lock + TTL + in-flight claim）。

    用于 /api/chapter/{n}/review 等昂贵端点，防止客户端双击 + 并发同 key
    触发重复 LLM 调用。

    设计要点：
      - 锁内做读写（threading.Lock，非 RLock 因为逻辑简单）。
      - 写入时惰性清理过期条目（每写入一次清理一次，简单实用）。
      - 默认 TTL 5 分钟（per spec）；过期后重新调用 LLM。
      - key 维度由 caller 决定（spec 要求 per-chapter + per-endpoint）。
      - **in-flight sentinel**（QA B8 PoC 修复）：``claim()`` 原子地尝试占位，
        后续请求看到 sentinel 时会 ``await wait_for_result()`` 轮询等第一个
        完成，然后拿到结果作为 replay 一起返回 200。这样：
          * LLM 不会被并发请求重复调用（fix race condition）
          * 后到的请求仍拿到结果（不会 409 拒绝）
          * 极端情况下 in-flight 永不 complete → 30s 超时后返回 409
      - **跨 event loop 友好**：用 poll 模式而非 ``asyncio.Event``。
        不同 TestClient 各自有独立 event loop；asyncio.Event 绑一个 loop 后
        不能跨 loop 使用（"is bound to a different event loop" error），
        poll 模式则没有这个问题（store 自身有 threading.Lock 保护并发）。

    用法：
        store = InMemoryIdempotencyStore(ttl_seconds=300)
        cache_key = (user_id, chapter, idempotency_key)
        claimed, existing = store.claim(cache_key)
        if not claimed:
            if isinstance(existing, dict) and existing.get("_in_flight"):
                result = await store.wait_for_result(cache_key, timeout=30.0)
                if result is None:
                    raise HTTPException(409, "...")
                existing = result
            replay = dict(existing)
            replay["_idempotent_replay"] = True
            return replay
        # 占位成功 → 跑 LLM
        result = await expensive_llm_call(...)
        store.complete(cache_key, result)
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        # value 可能是：
        #   - tuple[float, Any]    — 旧格式（直接 set() 写入）
        #   - dict[str, Any]       — sentinel ({"_in_flight": True, "_created_at": float})
        self._store: dict[tuple[Any, ...], Any] = {}
        self._lock = threading.Lock()

    def _now(self) -> float:
        return time.time()

    def _is_expired(self, created_at: float, now: float | None = None) -> bool:
        if self.ttl_seconds <= 0:
            return True
        if now is None:
            now = self._now()
        return now - created_at >= self.ttl_seconds

    def _extract_created_at(self, entry: Any) -> float | None:
        """V1.0.1 B8：从 entry 提取 created_at（兼容旧/新两种格式）。"""
        if isinstance(entry, tuple) and len(entry) == 2:
            ts, _ = entry
            return float(ts) if isinstance(ts, (int, float)) else None
        if isinstance(entry, dict):
            ts = entry.get("_created_at")
            return float(ts) if isinstance(ts, (int, float)) else None
        return None

    def _purge_expired(self) -> None:
        """V1.0.1 B8：清理过期条目（callers 持有 lock）。"""
        now = self._now()
        expired = [
            k
            for k in list(self._store)
            if self._is_expired(self._extract_created_at(self._store[k]) or 0.0, now)
        ]
        for k in expired:
            self._store.pop(k, None)

    def get(self, key: tuple[Any, ...]) -> Any | None:
        """V1.0.1 B8：取缓存结果。命中且未过期返回原值；过期或未命中返回 None。

        in-flight sentinel 被视为"未命中"（返回 None），caller 应改用
        ``claim()`` 来观察 sentinel + 等待完成。
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            created = self._extract_created_at(entry)
            if created is not None and self._is_expired(created):
                self._store.pop(key, None)
                return None
            # in-flight sentinel → 视为未命中
            if isinstance(entry, dict) and entry.get("_in_flight"):
                return None
            # 旧格式 (ts, value)
            if isinstance(entry, tuple) and len(entry) == 2:
                return entry[1]
            # 新格式（直接存 result）
            return entry

    def set(self, key: tuple[Any, ...], value: Any) -> None:
        """V1.0.1 B8：写缓存（绕过 claim 流程，直接存结果）。

        惰性清理过期条目以限制内存增长。保留向后兼容：旧测试用 ``.set()`` + ``.get()``
        仍按原语义工作。
        """
        with self._lock:
            self._purge_expired()
            self._store[key] = (self._now(), value)

    def claim(self, key: tuple[Any, ...]) -> tuple[bool, Any]:
        """V1.0.1 B8：原子地尝试占位。

        Returns:
            (claimed, existing):
              - (True, None) — 占位成功，你是第一个（应跑 LLM 然后 ``complete()``）
              - (False, sentinel_dict) — 已有 in-flight；caller 应 poll
                ``get()`` 等候结果（见 ``wait_for_result()``）。
              - (False, result) — 已有 cached result；直接返回作为 replay。
        """
        with self._lock:
            existing = self._store.get(key)
            if existing is not None:
                created = self._extract_created_at(existing)
                if created is not None and self._is_expired(created):
                    self._store.pop(key, None)
                    existing = None
            if existing is not None:
                # in-flight sentinel → 整体返回（caller 检测 _in_flight）
                if isinstance(existing, dict) and existing.get("_in_flight"):
                    return False, existing
                # cached result — 兼容旧 tuple 格式 (ts, value)
                if isinstance(existing, tuple) and len(existing) == 2:
                    return False, existing[1]
                return False, existing
            # 占位（sentinel；不绑 asyncio.Event 因为跨 event loop 不可用）
            sentinel: dict[str, Any] = {
                "_in_flight": True,
                "_created_at": self._now(),
            }
            self._store[key] = sentinel
            self._purge_expired()
            return True, None

    def complete(self, key: tuple[Any, ...], result: Any) -> None:
        """V1.0.1 B8：占位完成后存 result（覆盖 sentinel）。

        唤醒"在等待"同一 key 的协程是 caller 的责任：用
        ``wait_for_result()`` 轮询即可（见 review 端点实现）。
        """
        with self._lock:
            # 总是覆盖（让后续请求拿到 result）
            self._store[key] = (self._now(), result)

    async def wait_for_result(
        self, key: tuple[Any, ...], timeout: float = 30.0, poll_interval: float = 0.02
    ) -> Any | None:
        """V1.0.1 B8：异步轮询等待 in-flight 结果。

        跨 event loop 友好的等待（不用 asyncio.Event，因为不同 TestClient
        用各自 event loop）。每 ``poll_interval`` 秒检查 store 是否有 result。
        Returns:
            result（命中） / None（超时或 key 不存在）。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.get(key)
            if result is not None:
                return result
            await asyncio.sleep(poll_interval)
        return None

    def clear(self) -> None:
        """V1.0.1 B8：清空（仅测试使用）。"""
        with self._lock:
            self._store.clear()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """V0.29.3：app 启动时建全局 LLMProvider 单例，关闭时清理。

        之前 V0.27 之前：每次请求都新建 LLMProvider，导致：
        - cache stats（hits/misses）每次请求重置，命中率永远显示 0
        - 重复初始化开销（load .env、读 MODEL_CONFIG）
        - V0.30 WebUI 暴露 cache 命中率时无法跨请求累计

        收益：cache 跨请求连续、stats 稳定、单进程多请求共享 provider

        V0.30.6 B5：新增 auth_store / session_store / rate_limiter（多用户）。
        V0.30.6 C3：adaptive_router 已集成在 LLMProvider 内。
        """
        load_dotenv(".env", override=False)
        app.state.provider = LLMProvider(LLMConfig())
        # V0.31：活跃 pipeline task 注册表（用于 /api/write/cancel/{task_id} 取消正在运行的写作任务）
        # key = task_id (uuid4 hex[:8])，value = asyncio.Task
        app.state.active_pipelines = {}

        # V0.30.6 B5 收尾：auth + session + rate limiter
        from novel2all.core.auth import AuthStore, RateLimiter
        from novel2all.core.session import SessionStore

        app.state.auth_store = AuthStore()
        app.state.session_store = SessionStore()
        app.state.rate_limiter = RateLimiter()
        # V1.0 GA Day 11-15：audit log store（fail-safe：失败不阻塞 lifespan）
        try:
            from novel2all.core.audit import AuditStore

            app.state.audit_store = AuditStore()
        except Exception as e:
            logger.warning("V1.0 GA: AuditStore init failed (audit disabled): %s", e)
            app.state.audit_store = None

        # V1.0.1 B8：review 端点 idempotency store（防双击重复 LLM 调用）。
        # 单进程内有效；multi-worker 部署下需换成 Redis 共享（后续 V1.0.2+）。
        app.state.idempotency_store = InMemoryIdempotencyStore(ttl_seconds=300)

        # V0.30.6 C3 收尾：初始化 LLMProvider 内 AdaptiveRouter（数据驱动选模型）
        try:
            app.state.provider.init_adaptive_router()
        except Exception as e:
            logger.warning("V0.30.6 C3: AdaptiveRouter init failed (V0.23 router 仍生效): %s", e)
        logger.info(
            "Web app started: LLMProvider initialized (model=%s, cache_enabled=%s)",
            app.state.provider.config.default_model,
            app.state.provider.config.cache_enabled,
        )
        try:
            yield
        finally:
            # 清理：打印最终 cache stats（debug 用）
            stats = app.state.provider.cache_stats()
            logger.info(
                "Web app shutting down: cache stats=%s",
                stats,
            )
            # V0.42：显式关闭 cache backend（SQLite 连接池等）
            app.state.provider.close()
            # V1.0 GA：关闭 httpx 连接池
            if hasattr(app.state.provider, "_http_pool"):
                try:
                    import asyncio as _aio

                    _aio.get_event_loop().run_until_complete(
                        app.state.provider._http_pool.close_all()
                    )
                except Exception:
                    pass  # ignore close errors
            del app.state.provider

    app = FastAPI(
        title="novel2all Web UI",
        description="""novel2all 是 AI 驱动的小说创作平台。

## 核心特性
- **多 LLM 协同**：DeepSeek / Anthropic / OpenAI / minimax 等 12+ provider
- **质量保障**：4-agent 并行审查（critical / major / minor + quality）
- **数据驱动**：prompt prefix cache 节省 ~27% LLM 成本，自适应路由
- **多用户协作**：Session + ProjectMembership 权限管理
- **实时反馈**：8 阶段 SSE 进度条，字数/字秒/ETA 实时显示
- **章节导出**：Markdown / TXT / EPUB 3.0

## 认证
除  外大部分端点需要 Session cookie（HttpOnly + SameSite=Strict）。
登录后自动获得 7 天有效 cookie。

## 主要端点分组
-  - 认证
-  - 写作
-  - 章节管理
-  - Cache 管理
-  - 项目授权（B5）
-  - 本 OpenAPI 文档
        """,
        version="1.0.0",
        contact={"name": "novel2all", "url": "https://github.com/ourvps1688/novel2all"},
        license_info={"name": "MIT"},
        lifespan=lifespan,
        openapi_tags=[
            {"name": "auth", "description": "认证（登录/注销/用户管理）"},
            {"name": "writing", "description": "写作（SSE 流式 + cancel）"},
            {"name": "chapters", "description": "章节管理（导出/审查/回滚）"},
            {"name": "cache", "description": "Cache 管理（4 backend）"},
            {"name": "projects", "description": "项目授权（B5 多用户）"},
        ],
    )

    # === V1.0.1 B2：全局 500 exception handler（防 stack trace 泄露） ===

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """V1.0.1 B2：未捕获异常 → 返回 500 + 简短 message，不泄露 stack trace。

        实现要点：
          - 用 ``tracer.span("http.request.error")`` 包装整个处理流程，
            通过手动设置 ``span.status = "error"`` + ``span.attributes["error"]``
            标记错误（不重新 raise，否则会被 Starlette 的 ServerErrorMiddleware
            当作"test 时 raise"或 prod 时 500 response 处理）。
          - 返回 ``{"detail": "Internal server error", "request_id": "..."}``，
            request_id 便于运维按 ID 在 traces.jsonl 中定位完整堆栈。
          - 仅记录 logger.exception（不向 client 输出 stack trace）。
          - HTTPException 已经被 FastAPI 框架自身处理，这里仅捕获其他 Exception。
        """
        from novel2all.core.tracing import get_tracer

        tracer = get_tracer()
        request_id = uuid.uuid4().hex[:16]
        with tracer.span(
            "http.request.error",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            exception_type=type(exc).__name__,
        ) as span:
            span.status = "error"
            span.attributes["error"] = str(exc)
            logger.exception(
                "V1.0.1 B2 unhandled exception: request_id=%s path=%s exc=%s",
                request_id,
                request.url.path,
                exc,
            )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
        )

    # === V1.0.2 B4：LLMRateLimitExceeded → 429 with X-LLM-Tokens-Remaining ===
    from novel2all.core.llm_rate_limiter import LLMRateLimitExceeded

    @app.exception_handler(LLMRateLimitExceeded)
    async def _llm_rate_limit_handler(request: Request, exc: LLMRateLimitExceeded) -> JSONResponse:
        """V1.0.2 B4：per-user LLM rate limit 超额 → 429 + 友好提示。

        与 B2 全局 handler 不同：
          - 状态码 429（不是 500）
          - detail 含用户友好的"剩余 quota"信息
          - response header ``Retry-After`` = 3600（1h 窗口建议重试时间）
          - response header ``X-LLM-Tokens-Remaining`` = 0
          - logger.warning（不是 exception — 这是预期错误路径，不是 bug）
        """
        logger.warning(
            "V1.0.2 B4: LLM rate limit user=%s used=%d limit=%d requested=%d path=%s",
            exc.user_id,
            exc.used,
            exc.limit,
            exc.requested,
            request.url.path,
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": str(exc),
                "user_id": exc.user_id,
                "used": exc.used,
                "limit": exc.limit,
                "retry_after_seconds": 3600,
            },
            headers={
                "Retry-After": "3600",
                "X-LLM-Tokens-Remaining": "0",
            },
        )

    # === V1.0.1 B3：/metrics 端点 IP 白名单 ===
    @app.middleware("http")
    async def _metrics_ip_filter(request: Request, call_next):  # type: ignore[no-untyped-def]
        """V1.0.1 B3：限制 ``/metrics`` 端点仅 trusted IP 访问。

        默认白名单：``127.0.0.1``, ``::1``（localhost scrape）。
        通过 ``METRICS_ALLOWED_IPS`` 环境变量覆盖（逗号分隔）。
        注意：这是简单的 IP 字符串比较；如需 CIDR，可扩展为 ``ipaddress``
        模块匹配（per B5 同款思路）。
        """
        if request.url.path == "/metrics":
            allowed_raw = os.environ.get("METRICS_ALLOWED_IPS", "127.0.0.1,::1")
            allowed = {ip.strip() for ip in allowed_raw.split(",") if ip.strip()}
            client_ip = request.client.host if request.client else ""
            if client_ip not in allowed:
                logger.warning("V1.0.1 B3: /metrics access denied from %s", client_ip)
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            f"metrics endpoint only available from {', '.join(sorted(allowed))}"
                        ),
                    },
                )
        return await call_next(request)

    # V0.30.6 B5 收尾：注入 AuthMiddleware 到 FastAPI（处理每个请求的 session cookie）
    try:
        from starlette.middleware.base import BaseHTTPMiddleware

        class AuthMiddleware(BaseHTTPMiddleware):
            """V0.30.6 B5 收尾：从 session cookie 注入 user 到 request.state。"""

            async def dispatch(self, request, call_next):
                session_id = request.cookies.get("n2a_session")
                user = None
                active_session = None
                if session_id:
                    active_session = app.state.session_store.get(session_id)
                    if active_session:
                        user = app.state.auth_store.get_user_by_id(active_session.user_id)
                request.state.user = user
                request.state.session_id = active_session.id if user else None
                return await call_next(request)

        app.add_middleware(AuthMiddleware)
    except Exception as e:
        logger.warning("V0.30.6 B5: AuthMiddleware init failed: %s", e)

    # V1.0 GA：安全 headers 中间件（X-Content-Type-Options / X-Frame-Options / CSP）
    try:
        from novel2all.core.security_headers import SecurityHeadersMiddleware

        app.add_middleware(SecurityHeadersMiddleware)
    except Exception as e:
        logger.warning("V1.0 GA: SecurityHeadersMiddleware init failed: %s", e)

    # ============================================================
    # V1.0 GA Day 11-15：监控端点（metrics / traces / audit）
    # ============================================================

    @app.get("/metrics", response_class=Response)
    async def metrics_endpoint() -> Response:
        """V1.0 GA Day 11-15：Prometheus scrape endpoint。

        暴露 metrics：
        - novel2all_llm_calls_total（按 model / task / status）
        - novel2all_cache_operations_total（按 backend / operation）
        - novel2all_chapter_writes_total（按 verdict）
        - novel2all_rollbacks_total
        - novel2all_llm_latency_seconds（histogram）
        - novel2all_active_sessions（gauge）

        Prometheus scrape config:
          scrape_configs:
            - job_name: novel2all
              metrics_path: /metrics
              static_configs:
                - targets: [localhost:8000]
        """
        from novel2all.core.metrics import get_metrics_registry

        registry = get_metrics_registry()
        text = registry.export_prometheus()
        return Response(content=text, media_type="text/plain; version=0.0.4")

    @app.get("/api/debug/traces")
    async def get_recent_traces(limit: int = 100) -> dict[str, Any]:
        """V1.0 GA Day 11-15：最近 N 个 trace spans。"""
        from novel2all.core.tracing import get_tracer

        tracer = get_tracer()
        spans = tracer.get_recent_spans(limit=limit)
        return {"spans": spans, "count": len(spans)}

    @app.get("/api/debug/trace-stats")
    async def get_trace_stats() -> dict[str, Any]:
        """V1.0 GA Day 11-15：tracer 统计（按 span name 分组）。"""
        from novel2all.core.tracing import get_tracer

        tracer = get_tracer()
        return tracer.get_stats()

    @app.get("/api/auth/audit")
    async def get_audit_log(
        request: Request,
        event_type: str | None = None,
        user_id: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """V1.0 GA Day 11-15：审计日志查询（admin only）。"""
        await admin_required(request)
        events = request.app.state.audit_store.query(
            event_type=event_type,
            user_id=user_id,
            limit=limit,
        )
        return {"events": events, "count": len(events)}

    # ============================================================

    @app.post("/api/auth/login")
    async def auth_login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ) -> dict[str, Any]:
        """V0.30.6 B5 收尾：登录（username + password → set cookie）。

        V1.0.1 B1：cookie 增加 ``secure=not is_dev_mode`` 标志。
        V1.0.1 B7：用户名枚举防护——
          1. 用户不存在时也执行一次 PBKDF2 hash（与"用户存在但密码错"路径
             的耗时对齐），消除时序侧信道。
          2. audit log ``login_failed`` 不记 username（仅记 IP）——避免日志中
             泄露哪些 username 被尝试过、被用于枚举。

        Returns:
            {user: {...}, message: "Login successful"}
        Set-Cookie: n2a_session=<id>; HttpOnly; SameSite=Strict; Secure;
                    Max-Age=604800
        """
        client_ip = await get_client_ip(request)
        limiter = request.app.state.rate_limiter

        # V0.30.6 B5：rate limit
        if limiter.is_locked(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again later.",
            )

        auth_store = request.app.state.auth_store
        # V1.0.1 B7：先看用户是否存在（不暴露给 client），用户不存在时跑一遍
        # dummy hash 抹平时序差异。
        existing_user = auth_store.get_user_by_username(username)
        user = auth_store.authenticate(username, password)

        if user is None:
            # V1.0.1 B7：用户不存在或密码错时跑一次 dummy PBKDF2，使两条
            # 路径耗时大致相等。dummy hash 使用固定随机 salt（每次启动都
            # 不同），与 verify_password 走相同的算法路径。
            if existing_user is None:
                # 用户不存在：仍执行一次完整 PBKDF2（与 verify_password
                # 路径一致）
                from novel2all.core.auth import hash_password

                _ = hash_password(password)
            locked = limiter.record_fail(client_ip)
            detail = "Invalid credentials"
            if locked:
                detail = "Too many failed attempts. Account temporarily locked."
            # V1.0 GA Day 11-15：audit 记录登录失败
            # V1.0.1 B7：不记 username（防止日志被用作枚举探测 + PII 防护）
            audit_store = request.app.state.audit_store
            if audit_store is not None:
                audit_store.record(
                    "login_failed",
                    username=None,  # B7: 不记 username
                    ip=client_ip,
                    success=False,
                    detail=detail,
                )
            raise HTTPException(status_code=401, detail=detail)

        # 登录成功：创建 session + 重置 rate limit
        limiter.record_success(client_ip)
        sess = request.app.state.session_store.create(user.id)

        # V1.0 GA Day 11-15：audit + metrics
        audit_store = request.app.state.audit_store
        if audit_store is not None:
            audit_store.record(
                "login",
                user_id=user.id,
                username=user.username,
                ip=client_ip,
                success=True,
            )
        from novel2all.core.metrics import get_metrics_registry

        registry = get_metrics_registry()
        registry.counter(
            "novel2all_chapter_writes_total", "", ()
        ).inc()  # placeholder; real metric below

        response = JSONResponse(
            {
                "user": user.to_dict(),
                "message": "Login successful",
            }
        )
        # V1.0.1 B1：HttpOnly + SameSite=Strict + Secure cookie。
        # Secure 标志在 dev 模式下（HTTP）必须为 False，否则浏览器拒收。
        # 生产（HTTPS）通过 NOVEL2ALL_DEBUG=false 或 DEBUG=false 启用。
        is_dev_mode = _is_dev_mode()
        response.set_cookie(
            key="n2a_session",
            value=sess.id,
            max_age=7 * 24 * 3600,
            httponly=True,
            samesite="strict",
            secure=not is_dev_mode,
            path="/",
        )
        # V1.5 React：登录成功后 React 端拿到 200 JSON 后自行 navigate("/")
        # 不再依赖 HTMX HX-Redirect header（V1.0.2 兼容保留无害）
        response.headers["HX-Redirect"] = "/"
        return response

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request) -> dict[str, Any]:
        """V0.30.6 B5 收尾：注销（删除 session + clear cookie）。"""
        session_id = get_request_session_id(request)
        if session_id:
            request.app.state.session_store.delete(session_id)

        from starlette.responses import JSONResponse

        response = JSONResponse({"message": "Logged out"})
        response.delete_cookie("n2a_session", path="/")
        return response

    @app.get("/api/auth/me")
    async def auth_me(request: Request) -> dict[str, Any]:
        """V0.30.6 B5 收尾：当前用户信息（未登录返回 null user）。"""
        user = get_request_user(request)
        return {
            "user": user.to_dict() if user else None,
            "authenticated": user is not None,
        }

    # V0.30.6 B5 收尾：admin-only 用户管理
    @app.get("/api/auth/users")
    async def list_all_users(request: Request) -> dict[str, Any]:
        """V0.30.6 B5 收尾：admin 列所有用户。"""
        await admin_required(request)
        users = request.app.state.auth_store.list_users()
        return {"users": [u.to_dict() for u in users]}

    @app.post("/api/auth/users")
    async def create_user_endpoint(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        role: str = Form("editor"),
    ) -> dict[str, Any]:
        """V0.30.6 B5 收尾：admin 创建用户。"""
        await admin_required(request)
        try:
            user = request.app.state.auth_store.create_user(username, password, role=role)
            return {"user": user.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete("/api/auth/users/{user_id}")
    async def delete_user_endpoint(request: Request, user_id: int) -> dict[str, Any]:
        """V0.30.6 B5 收尾：admin 删除用户。"""
        current = await admin_required(request)
        if current.id == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        if not request.app.state.auth_store.delete_user(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return {"deleted": user_id}

    # V0.30.6 B5 收尾：项目授权
    @app.post("/api/auth/projects/{project_root:path}/share")
    async def share_project(
        request: Request,
        project_root: str,
        user_id: int = Form(...),
        role: str = Form("viewer"),
    ) -> dict[str, Any]:
        """V0.30.6 B5 收尾：admin 给用户授权项目访问（owner/editor/viewer）。

        V1.0.1 B6：增加路径校验 + 项目存在性 check + 双层 admin guard：
          1. ``current_user_required`` 必须是已登录用户。
          2. ``admin_required`` 必须是 admin（否则 403）。
          3. URL 路径不得含 ``..`` 或绝对路径前缀 → 400。
          4. admin 自身必须已对该项目有 owner/editor 权限 → 403（admin 不能凭空
             grant 一个 admin 自己都没访问权的项目；这避免了恶意 admin 把
             任意路径授权出去）。**注意**：spec 中"admin 跳过"指跳过
             *非 admin 路径*（即 admin 总可以授权），但项目级仍要求 admin 自己
             已 ``grant_project_access`` 过该 project（"必须先有 owner"）。
        """
        # === V1.0.1 B6：路径校验（防越权） ===
        # 拒绝含 `..` 的相对路径穿越，以及绝对路径绕过（绝对路径会被 Path.resolve
        # 直接接受，但 spec 要求拒绝）。
        if ".." in project_root.split("/") or ".." in project_root.split("\\"):
            raise HTTPException(
                status_code=400,
                detail="Invalid project_root: '..' path traversal not allowed",
            )
        if Path(project_root).is_absolute() or project_root.startswith(("/", "\\")):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid project_root: absolute paths not allowed. "
                    "Use a relative path (resolved against the caller)."
                ),
            )

        # === V1.0.1 B6：admin guard + caller 项目授权检查 ===
        admin = await admin_required(request)
        abs_path = str(Path(project_root).resolve())

        # admin 自身必须已对该项目有 owner/editor 权限（防任意路径授权）
        admin_role = request.app.state.auth_store.get_project_role(admin.id, abs_path)
        if admin_role not in {"owner", "editor"}:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Admin does not have owner/editor access to {abs_path}. "
                    "Grant yourself access first."
                ),
            )

        try:
            m = request.app.state.auth_store.grant_project_access(
                user_id,
                abs_path,
                role,
                admin.id,
            )
            return {"membership": m.to_dict()}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete("/api/auth/projects/{project_root:path}/share/{user_id}")
    async def revoke_project(
        request: Request,
        project_root: str,
        user_id: int,
    ) -> dict[str, Any]:
        """V0.30.6 B5 收尾：admin 撤销用户项目访问。"""
        await admin_required(request)
        abs_path = str(Path(project_root).resolve())
        if not request.app.state.auth_store.revoke_project_access(user_id, abs_path):
            raise HTTPException(status_code=404, detail="Membership not found")
        return {"revoked": True}

    @app.get("/api/auth/users/{user_id}/projects")
    async def list_user_projects(request: Request, user_id: int) -> dict[str, Any]:
        """V0.30.6 B5 收尾：列用户的所有项目授权。"""
        await admin_required(request)
        memberships = request.app.state.auth_store.list_user_projects(user_id)
        return {"memberships": [m.to_dict() for m in memberships]}

    # ============================================================

    # V0.29.3：测试 fallback（TestClient 默认不触发 lifespan 上下文）
    # 生产路径走 lifespan；测试路径直接初始化 provider
    # 这样 `app = create_app(); client = TestClient(app)` 也能工作
    if not hasattr(app.state, "provider"):
        load_dotenv(".env", override=False)
        app.state.provider = LLMProvider(LLMConfig())

    # V1.0.1 B8：测试 fallback 也初始化 idempotency_store（让 TestClient 测试
    # 访问 review 端点时不会因 app.state 缺失而 crash）。
    if not hasattr(app.state, "idempotency_store"):
        app.state.idempotency_store = InMemoryIdempotencyStore(ttl_seconds=300)

    @app.get("/api/status")
    async def status(project_root: str = ".") -> dict:
        root = Path(project_root).resolve()
        tracker = Tracker(root / "_tracking-state.json")
        if not tracker.exists():
            return {"initialized": False, "project_root": str(root)}
        state = tracker.read()
        return {
            "initialized": True,
            "project_root": str(root),
            "project_name": state.project_name,
            "genre": state.genre,
            "style_anchor": state.style_anchor,
            "total_chapters_target": state.total_chapters_target,
            "total_word_count_target": state.total_word_count_target,
            "last_updated_chapter": state.last_updated_chapter,
            "character_count": len(state.characters),
            "active_foreshadowing_count": len(
                [f for f in state.foreshadowing.values() if f.status == "active"]
            ),
            "timeline_count": len(state.timeline),
            "summary_count": len(state.recent_chapter_summaries),
        }

    @app.get("/api/skills")
    async def list_skills() -> list[dict]:
        skills_dir = Path(__file__).parent.parent / "skills"
        registry = SkillRegistry(skills_dir)
        registry.discover()
        return [
            {
                "name": s.name,
                "description": s.description,
                "user_invocable": s.user_invocable,
                "model_invocable": s.model_invocable,
            }
            for s in registry.list()
        ]

    @app.get("/api/roles")
    async def list_roles() -> list[dict]:
        roles_dir = Path(__file__).parent.parent / "roles"
        registry = RoleRegistry(roles_dir)
        registry.discover()
        return [
            {
                "name": r.name,
                "description": r.description,
                "preferred_model": r.preferred_model,
            }
            for r in registry.list()
        ]

    @app.get("/api/cache/stats")
    async def cache_stats(request: Request) -> dict[str, Any]:
        """V0.29.3：返回 lifespan provider 的 cache 统计。

        V0.30 WebUI 暴露此端点做实时命中率面板。
        V0.30.6 C1：额外包含 prompt_prefix 子字典（量化 prefix cache 节省）。
        """
        provider: LLMProvider = request.app.state.provider
        return provider.cache_stats()

    # V0.30.6 C1：Prompt prefix cache 专用端点
    @app.get("/api/cache/prompt-stats")
    async def prompt_cache_stats(request: Request) -> dict[str, Any]:
        """V0.30.6 C1：返回 prompt prefix cache 统计。

        与 /api/cache/stats["prompt_prefix"] 等价，但更直接。
        用于 Web UI "prompt prefix 节省 ¥" 卡片 + benchmark 验证脚本。

        Returns:
            dict 含 prefix_hits/misses/total/hit_rate/unique_sys_prompts/
            cost_saved_cny/potential_savings_cny + model 参数
        """
        provider: LLMProvider = request.app.state.provider
        return provider.prompt_cache_stats()

    @app.post("/api/cache/prompt-stats/reset")
    async def reset_prompt_cache_stats(request: Request) -> dict[str, Any]:
        """V0.30.6 C1：重置 prompt prefix cache 统计（手动 reset）。"""
        provider: LLMProvider = request.app.state.provider
        provider.reset_prompt_cache_stats()
        return {"reset": True, "stats": provider.prompt_cache_stats()}

    # V0.43：Cache 迁移端点（POST 表单）
    @app.post("/api/cache/migrate")
    async def cache_migrate(
        src: str = Form(...),
        dst: str = Form(...),
        src_backend: str = Form("auto"),
        dst_backend: str = Form("auto"),
        max_size: int = Form(1024),
        ttl_seconds: int = Form(0),
    ) -> dict[str, Any]:
        """V0.43：在不同 cache backend 之间平滑迁移（零数据丢失）。

        Form 参数：
        - src: 源 cache 文件路径
        - dst: 目标 cache 文件路径
        - src_backend/dst_backend: "json" / "sqlite" / "auto"（按扩展名自动检测）
        - max_size: 目标 max_size
        - ttl_seconds: 目标 TTL

        返回：MigrationResult 转 dict（含 migrated/errors/elapsed 等）
        """
        from novel2all.core.migration import migrate_cache

        # auto-detect backend
        if src_backend == "auto":
            if src.endswith(".json"):
                src_backend = "json"
            elif src.endswith((".db", ".sqlite")):
                src_backend = "sqlite"
            elif src.startswith("redis://"):
                src_backend = "redis"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"无法自动检测 src backend（{src}）",
                )
        if dst_backend == "auto":
            if dst.endswith(".json"):
                dst_backend = "json"
            elif dst.endswith((".db", ".sqlite")):
                dst_backend = "sqlite"
            elif dst.startswith("redis://"):
                dst_backend = "redis"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"无法自动检测 dst backend（{dst}）",
                )

        if src_backend == "memory" or dst_backend == "memory":
            raise HTTPException(
                status_code=400,
                detail="memory backend 不支持迁移（无持久化）",
            )

        try:
            result = migrate_cache(
                src_backend=src_backend,
                dst_backend=dst_backend,
                src_path=src,
                dst_path=dst,
                max_size=max_size,
                ttl_seconds=ttl_seconds,
            )
        except Exception as e:
            logger.exception("V0.43 cache_migrate failed")
            raise HTTPException(status_code=500, detail=f"迁移失败: {e}")

        return {
            "src_backend": result.src_backend,
            "dst_backend": result.dst_backend,
            "src_path": result.src_path,
            "dst_path": result.dst_path,
            "total_entries": result.total_entries,
            "migrated": result.migrated,
            "skipped_expired": result.skipped_expired,
            "errors": result.errors,
            "elapsed_seconds": result.elapsed_seconds,
        }

    # V0.51：Cache 配置智能推荐端点
    @app.get("/api/cache/recommend")
    async def cache_recommend(request: Request) -> dict[str, Any]:
        """V0.51：根据 cache_stats() + 当前 LLMConfig 推荐 backend / max_size / ttl_seconds。

        返回结构见 CacheRecommendation.to_dict()：
        - current: 当前配置
        - recommended: 各字段推荐值 + 理由 + 预期影响 + 置信度
        - actions: 立即可执行的动作列表（含 how-to 步骤）
        - health_score: 0.0-1.0
        - issues: 检测到的问题列表
        - confidence: 整体置信度（high/medium/low）
        - notes: 备注（如数据不足警告）

        算法：见 novel2all.core.cache_recommend.recommend_cache_config()
        """
        from novel2all.core.cache_recommend import recommend_cache_config

        provider: LLMProvider = request.app.state.provider
        stats = provider.cache_stats()
        config = provider.config

        rec = recommend_cache_config(
            stats=stats,
            current_backend=config.cache_backend,
            current_max_size=config.cache_max_size,
            current_ttl_seconds=config.cache_ttl_seconds,
        )
        return rec.to_dict()

    # V0.30.1：模型选择器 API
    @app.get("/api/models")
    async def list_models() -> list[dict[str, Any]]:
        """V0.30.1：列出 MODEL_CONFIG 中所有可用模型。

        前端模型选择器用。每条含：
        - name：模型名（litellm 格式，如 "minimax/MiniMax-M3"）
        - anthropic_compat：是否走 anthropic Messages API 路径
        - api_base：自定义 endpoint（None = 用 litellm 默认）
        - api_key_env：环境变量名（None = 用 LLMConfig 默认）
        """
        from novel2all.core.provider_router import MODEL_CONFIG

        models = []
        for name, cfg in MODEL_CONFIG.items():
            models.append(
                {
                    "name": name,
                    "anthropic_compat": bool(cfg.api_base and "anthropic" in cfg.api_base),
                    "api_base": cfg.api_base,
                    "api_key_env": cfg.api_key_env,
                }
            )
        return models

    @app.get("/api/model/current")
    async def get_current_model(request: Request) -> dict[str, str]:
        """V0.30.1：返回当前 provider 的 default_model。"""
        provider: LLMProvider = request.app.state.provider
        return {"model": provider.config.default_model}

    @app.post("/api/model/switch")
    async def switch_model(request: Request, model: str = Form(...)) -> dict[str, str]:
        """V0.30.1：切换 provider 的 default_model。

        切换后：
        - 后续 complete()/stream() 不传 model 参数时用新 model
        - 已创建的 provider（lifespan 单例）保持
        - cache stats 不受影响（LRU 保留）
        """
        from novel2all.core.provider_router import MODEL_CONFIG

        provider: LLMProvider = request.app.state.provider
        if model not in MODEL_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"未知模型: {model}。可选: {', '.join(MODEL_CONFIG.keys())}",
            )
        old_model = provider.config.default_model
        provider.config.default_model = model
        logger.info("V0.30.1: 模型切换 %s → %s", old_model, model)
        return {"old_model": old_model, "new_model": model}

    @app.post("/api/write/stream/model")
    async def write_stream_with_model(
        request: Request,
        chapter: int = Form(...),
        project_root: str = Form("."),
        skill: str = Form("story-long-write"),
        model: str | None = Form(None),
        min_chars: int = Form(2000),
        skip_pre_write: bool = Form(False),
        resume_from_chars: int = Form(0),  # V0.32：0 = 正常开始，>0 = 接续模式
    ) -> StreamingResponse:
        """V0.30.1：带 model 参数的流式写作端点（V0.29.3 单例 + V0.30 WebUI 集成）。

        复用了原 /api/write/stream 的逻辑，但接受 Form 参数（HTMX 友好）。

        V0.31：在 'started' 事件里 yield task_id（uuid4 hex[:8]），
        注册到 app.state.active_pipelines，让 /api/write/cancel/{task_id} 能取消。
        Pipeline 抛 PipelineCancelledError 时 yield 'cancelled' 事件（partial content 信息）。

        V0.32：接受 resume_from_chars 参数 → pipeline 接续 partial content 写。
        """
        # V0.30.1：用请求中的 model（不污染单例）
        from novel2all.cli.main import get_llm_for_model

        # V0.31：生成 task_id 提前（即便后续初始化失败也要返回 task_id 用于排查）
        task_id = uuid.uuid4().hex[:8]

        async def event_stream() -> AsyncIterator[str]:
            llm: LLMProvider = get_llm_for_model(model)
            root = Path(project_root).resolve()
            project = ProjectStructure(root=root)
            if not project.exists():
                yield sse_event(
                    "error",
                    {
                        "message": f"项目未初始化: {root}. 请先跑 novel2all setup.",
                        "task_id": task_id,
                    },
                )
                return

            yield sse_event(
                "started",
                {
                    "task_id": task_id,  # V0.31：让前端能调用 /api/write/cancel/{task_id}
                    "chapter": chapter,
                    "skill": skill,
                    "model": model or "default",
                    "min_chars": min_chars,
                    "skip_pre_write": skip_pre_write,
                    "resume_from_chars": resume_from_chars,  # V0.32
                    "project_root": str(root),
                },
            )

            try:
                manager = MemoryManager(project_root=root, llm=llm)
                skills_dir = Path(__file__).parent.parent / "skills"
                skill_registry = SkillRegistry(skills_dir)
                skill_registry.discover()
                pipeline = WritingPipeline(
                    manager=manager,
                    skill_registry=skill_registry,
                    llm=llm,
                    project=project,
                )
            except Exception as e:
                yield sse_event("error", {"message": f"Pipeline 初始化失败: {e}"})
                return

            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            collected: list[str] = []

            def on_chunk(text: str) -> None:
                collected.append(text)
                chunk_queue.put_nowait(text)

            async def run_pipeline() -> None:
                try:
                    await pipeline.write_chapter(
                        chapter=chapter,
                        outline_path=project.chapter_outline(chapter),
                        skill_name=skill,
                        stream_callback=on_chunk,
                        min_chars=min_chars,
                        skip_pre_write_check=skip_pre_write,
                        resume_from_chars=resume_from_chars,  # V0.32
                    )
                finally:
                    await chunk_queue.put(None)

            pipeline_task = asyncio.create_task(run_pipeline())
            # V0.31：注册到 app.state.active_pipelines（让 cancel endpoint 能找到）
            request.app.state.active_pipelines[task_id] = pipeline_task
            try:
                while True:
                    chunk = await chunk_queue.get()
                    if chunk is None:
                        break
                    yield sse_event("chunk", {"text": chunk})

                # V0.31：先取 pipeline_task 结果（可能抛 PipelineCancelledError）
                try:
                    result = await pipeline_task
                except PipelineCancelledError as cancel_exc:
                    # 用户中途取消 → 已保存 partial content 到 output_path
                    partial_content = "".join(collected)
                    yield sse_event(
                        "cancelled",
                        {
                            "task_id": task_id,
                            "chapter": cancel_exc.chapter,
                            "partial_chars": cancel_exc.partial_chars,
                            "output_path": str(cancel_exc.output_path),
                            "preview": partial_content[:200],
                            "message": (
                                f"已在 {cancel_exc.partial_chars} 字处取消，"
                                f"内容已保存到 {cancel_exc.output_path.name}"
                            ),
                        },
                    )
                    return

                if result.pre_write_issues:
                    yield sse_event(
                        "pre_write_check",
                        {"issues": [issue.model_dump() for issue in result.pre_write_issues]},
                    )

                yield sse_event(
                    "progress",
                    {"phase": "save", "message": f"已写文件: {result.output_path}"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "extract", "message": "提取角色/伏笔/时间线"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "merge", "message": "合并到 tracking state"},
                )

                if result.post_write_issues:
                    yield sse_event(
                        "post_write_check",
                        {"issues": [issue.model_dump() for issue in result.post_write_issues]},
                    )

                yield sse_event(
                    "done",
                    {
                        "task_id": task_id,
                        "output_path": str(result.output_path),
                        "content_chars": result.content_chars,
                        "resumed_from_chars": result.resumed_from_chars,  # V0.32
                        "post_issue_count": len(result.post_write_issues),
                        "pre_issue_count": len(result.pre_write_issues),
                    },
                )

            except OutlineNotFoundError as e:
                yield sse_event("error", {"message": str(e), "code": "outline_not_found"})
            except BlockingIssuesError as e:
                yield sse_event(
                    "error",
                    {
                        "message": f"pre-write check 发现 {len(e.issues)} 个 critical 问题",
                        "code": "blocking_issues",
                        "issues": [issue.model_dump() for issue in e.issues],
                    },
                )
            except Exception as e:
                if pipeline_task.done() and pipeline_task.exception():
                    exc = pipeline_task.exception()
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(exc).__name__}: {exc}"},
                    )
                else:
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(e).__name__}: {e}"},
                    )
            finally:
                # V0.31：无论成功/失败/取消，都从注册表移除
                request.app.state.active_pipelines.pop(task_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # V0.31：取消正在运行的 pipeline 任务
    @app.post("/api/write/cancel/{task_id}")
    async def cancel_write_task(task_id: str, request: Request) -> dict[str, Any]:
        """V0.31：取消 task_id 对应的 pipeline 任务。

        取消后：
        - pipeline 协程收到 CancelledError，捕获后保存 partial content 到 <chapter>.md
        - SSE 流发送 'cancelled' 事件（partial_chars + output_path）
        - 任务从 app.state.active_pipelines 注册表移除

        Returns:
            200 + {"task_id": ..., "status": "cancelled"} 成功取消
            404 + {"task_id": ..., "status": "not_found"} task_id 不存在（已完成/已取消）
        """
        pipeline_task = request.app.state.active_pipelines.get(task_id)
        if pipeline_task is None or pipeline_task.done():
            raise HTTPException(
                status_code=404,
                detail=f"task {task_id} 不存在或已完成",
            )
        pipeline_task.cancel()
        logger.info("V0.31 cancel: pipeline task %s cancelled", task_id)
        return {"task_id": task_id, "status": "cancelling"}

    @app.get("/api/write/active")
    async def list_active_pipelines(request: Request) -> list[dict[str, Any]]:
        """V0.31：列出当前活跃的 pipeline task（调试用）。

        Returns:
            [{"task_id": ..., "done": False, "cancelled": False}, ...]
        """
        result = []
        for tid, task in request.app.state.active_pipelines.items():
            result.append(
                {
                    "task_id": tid,
                    "done": task.done(),
                    "cancelled": task.cancelled() if hasattr(task, "cancelled") else False,
                }
            )
        return result

    @app.get("/api/tracking")
    async def get_tracking(project_root: str = ".") -> dict:
        root = Path(project_root).resolve()
        tracker = Tracker(root / "_tracking-state.json")
        if not tracker.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        state = tracker.read()
        return state.model_dump(mode="json")

    @app.get("/api/chapters")
    async def list_chapters(project_root: str = ".") -> list[dict]:
        """列出项目下已写章节。"""
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            return []
        result: list[dict] = []
        prose_dir = project.chapter_prose(1).parent  # 正文/ 目录
        if not prose_dir.exists():
            return []
        # 找所有 第NNN章.md
        import re

        for f in sorted(prose_dir.glob("第*章.md")):
            m = re.match(r"^第(\d+)章\.md$", f.name)
            if not m:
                continue
            ch = int(m.group(1))
            text = f.read_text(encoding="utf-8")
            result.append(
                {
                    "chapter": ch,
                    "filename": f.name,
                    "char_count": len(text),
                    "first_line": text.split("\n", 1)[0].strip()[:80],
                }
            )
        return result

    @app.get("/api/chapter/{chapter}/content")
    async def get_chapter_content(
        chapter: int,
        project_root: str = Query(".", description="项目根目录"),
    ) -> dict:
        """获取指定章节的完整内容。"""
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found")
        text_content = prose_path.read_text(encoding="utf-8")
        return {
            "chapter": chapter,
            "filename": prose_path.name,
            "content": text_content,
            "char_count": len(text_content),
            "first_line": text_content.split("\n", 1)[0].strip()[:120],
        }

    # V0.30.6 B6：章节导出端点
    @app.get("/api/chapter/{chapter}/export")
    async def export_chapter(
        chapter: int,
        format: str = Query("md", description="导出格式: md | txt | epub"),
        project_root: str = Query(".", description="项目根目录"),
    ) -> Response:
        """V0.30.6 B6：导出单章节为指定格式。

        支持格式：
        - md：Markdown（直接透传 + 标准 frontmatter）
        - txt：纯文本（剥离 markdown 语法）
        - epub：EPUB 3.0（单章节 + 元数据）

        Returns:
            Response: 带 Content-Disposition 头的文件流
        """
        from novel2all.core.exporter import (
            Chapter,
            get_exporter,
        )

        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")

        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found")

        try:
            ch = Chapter.from_md_file(prose_path)
            exporter = get_exporter(format)
            content_bytes = exporter.export_chapter(ch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("V0.30.6 B6 export_chapter failed")
            raise HTTPException(status_code=500, detail=f"Export failed: {e}") from e

        return Response(
            content=content_bytes,
            media_type=exporter.mime_type(),
            headers={
                # V0.30.6 B6: ASCII-safe filename（HTTP header 必须 latin-1）
                "Content-Disposition": (
                    f'attachment; filename="chapter_{chapter:03d}.{exporter.file_extension()}"'
                ),
            },
        )

    # V0.30.6 B2：手动 rollback 端点（CLI/UI 触发）
    @app.post("/api/chapter/{chapter}/rollback")
    async def rollback_chapter(
        chapter: int,
        project_root: str = Query(".", description="项目根目录"),
    ) -> dict[str, Any]:
        """V0.30.6 B2：手动回滚章节。

        注意：手动回滚需要存在 .bak 备份文件。
        如果 7 天前备份已被清理，回滚失败。

        正常流程：B1 review verdict=fail 时自动回滚（无需手动调）。
        本端点用于：
        - 用户后悔想撤回刚才的章节
        - 自动回滚失败后手动恢复

        Returns:
            dict 含 success / restored_from_backup / state_changes_reverted / message
        """
        from novel2all.core.memory.rollback import RollbackManager

        root = Path(project_root).resolve()
        manager = RollbackManager(project_root=root)

        # 找最新的 .bak 备份
        prose_dir = root / "正文"
        if not prose_dir.exists():
            raise HTTPException(status_code=404, detail="Prose directory not found")

        pattern = f"第{chapter:03d}章.md.bak.*"
        backups = sorted(prose_dir.glob(pattern), reverse=True)
        if not backups:
            raise HTTPException(
                status_code=404,
                detail=f"No backup found for chapter {chapter}. Auto-rollback only works within 7 days.",
            )

        latest_backup = backups[0]
        from novel2all.core.memory.rollback import WriteSnapshot

        snapshot = WriteSnapshot(
            chapter_number=chapter,
            backup_path=latest_backup,
            state_changes=[],
            timestamp=latest_backup.stat().st_mtime,
            state_file=root / "_tracking-state.json",
        )

        result = manager.rollback(snapshot)
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        return result.to_dict()

    # V0.30.6 B1：4-agent 审查端点
    @app.post("/api/chapter/{chapter}/review")
    async def review_chapter(
        request: Request,
        chapter: int,
        project_root: str = Query(".", description="项目根目录"),
    ) -> dict[str, Any]:
        """V0.30.6 B1：4-agent 并行审查章节（critical/major/minor + quality）。

        V1.0.1 B8：``Idempotency-Key`` header 支持（防双击 + 防并发重复 LLM）。
        - 客户端在请求头中传 UUID4 作 idempotency key。
        - 后端用 ``InMemoryIdempotencyStore.claim()`` 原子占位，避免并发同
          key 触发多次 LLM 调用。
        - 同 key 同 chapter + TTL 内：直接返回缓存（不调 LLM）。
        - 并发同 key：第一个抢到 claim 的跑 LLM，其他请求 await asyncio.Event
          等结果（共享同一 LLM 结果，全部 200 返回）。
        - TTL 过期或 in-flight 超时（30s）→ 重新调用 LLM 或返回 409。
        - 不同 chapter → 不同 cache slot。

        Returns:
            dict 含 critical_issues / major_issues / minor_issues / quality_score /
            total_* / overall_verdict / elapsed_seconds / content_chars / chapter_number
            （含 ``_idempotent_replay: true`` 字段当返回缓存命中时）
        """
        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        # === V1.0.1 B8：idempotency check (claim-based, race-safe) ===
        idempotency_key = request.headers.get("Idempotency-Key")
        user = get_request_user(request)
        user_id = user.id if user is not None else 0

        cache_key: tuple[int, int, str] | None = None
        claimed: bool = False
        if idempotency_key:
            # key 维度：(user_id, chapter, idempotency_key) — per spec。
            # 同 chapter 不同 user 的请求互不干扰。
            cache_key = (user_id, chapter, idempotency_key)
            idempotency_store = request.app.state.idempotency_store
            claimed, existing = idempotency_store.claim(cache_key)
            if not claimed:
                # 已有 in-flight 或 cached result
                if isinstance(existing, dict) and existing.get("_in_flight"):
                    # In-flight：轮询等第一个请求完成（跨 event loop 友好）
                    result = await idempotency_store.wait_for_result(cache_key, timeout=30.0)
                    if result is None:
                        logger.warning(
                            "V1.0.1 B8: idempotency in-flight timeout user=%s chapter=%s key=%s",
                            user_id,
                            chapter,
                            idempotency_key[:8],
                        )
                        raise HTTPException(
                            status_code=409,
                            detail="Idempotency-Key request still in progress (timeout)",
                        ) from None
                    existing = result
                # 此时 existing 一定是 cached result
                logger.info(
                    "V1.0.1 B8: review idempotent replay user=%s chapter=%s key=%s",
                    user_id,
                    chapter,
                    idempotency_key[:8],
                )
                replay = dict(existing)
                replay["_idempotent_replay"] = True
                return replay

        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")

        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found")

        # 读取章节正文
        try:
            content = prose_path.read_text(encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Read failed: {e}") from e

        # 读取 state（_tracking-state.json）
        state_data = {}
        if project.tracking_state_file.exists():
            try:
                state_data = json.loads(project.tracking_state_file.read_text(encoding="utf-8"))
            except Exception:
                state_data = {}

        # 构建 minimal state 对象（MultiAgentReviewer._state_to_text 兼容）
        from types import SimpleNamespace

        state = SimpleNamespace(
            characters=state_data.get("characters", {}),
            foreshadowing=state_data.get("foreshadowing", []),
            style_anchor=state_data.get("style_anchor"),
        )

        # 跑 4-agent 并行审查
        provider: LLMProvider = request.app.state.provider
        reviewer = MultiAgentReviewer(llm=provider)
        report = await reviewer.review(state=state, content=content, chapter_number=chapter)
        result = report.to_dict()

        # === V1.0.1 B8：complete（覆盖 sentinel + 唤醒 waiter）===
        if cache_key is not None and claimed:
            idempotency_store.complete(cache_key, result)
        return result

    # V0.30.6 B6：批量导出端点（整本书）
    @app.get("/api/export")
    async def export_project(
        format: str = Query("epub", description="导出格式: md | txt | epub"),
        project_root: str = Query(".", description="项目根目录"),
        title: str = Query("", description="书名（EPUB 用）"),
        author: str = Query("", description="作者（EPUB 用）"),
    ) -> Response:
        """V0.30.6 B6：导出整本书为指定格式（自动发现所有 chapter）。

        支持格式：
        - md：单文件 Markdown（多章节拼接）
        - txt：纯文本（多章节拼接）
        - epub：EPUB 3.0（含导航 + 元数据 + 完整结构）
        """
        from novel2all.core.exporter import BookMetadata
        from novel2all.core.exporter import export_project as do_export

        root = Path(project_root).resolve()
        try:
            metadata = BookMetadata(
                title=title or "未命名作品",
                author=author or "未知作者",
            )
            content_bytes = do_export(root, format, metadata)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("V0.30.6 B6 export_project failed")
            raise HTTPException(status_code=500, detail=f"Export failed: {e}") from e

        from novel2all.core.exporter import get_exporter

        exporter = get_exporter(format)
        # V0.30.6 B6: HTTP header latin-1 only, so strip non-ASCII
        import re as _re

        safe_title = (title or "未命名作品").replace("/", "_").replace("\\", "_")
        safe_title_ascii = _re.sub(r"[^\\w\\-]", "_", safe_title) or "novel"
        return Response(
            content=content_bytes,
            media_type=exporter.mime_type(),
            headers={
                # V0.30.6 B6: ASCII-safe filename
                "Content-Disposition": (
                    f'attachment; filename="{safe_title_ascii}.{exporter.file_extension()}"'
                ),
            },
        )

    # V0.34：手动保存编辑后的章节
    @app.post("/api/chapter/{chapter}/save")
    async def save_chapter_content(
        chapter: int,
        request: Request,
        content: str = Form(...),
        project_root: str = Form("."),
    ) -> dict[str, Any]:
        """V0.34：保存用户手动编辑的章节内容（覆盖章节文件）。

        流程：
        1. 写入 chapter_prose(chapter) 文件
        2. 同步 _tracking-state.json 的 last_updated_chapter（让 UI 知道最新进度）
        3. 不调 update_after_writing（手动编辑不走 LLM 提取）

        Returns:
            200 + {"chapter": ..., "char_count": ..., "output_path": "..."}
            404 + 错误信息
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")

        prose_path = project.chapter_prose(chapter)
        prose_path.parent.mkdir(parents=True, exist_ok=True)
        prose_path.write_text(content, encoding="utf-8")

        # 同步 tracking state（不更新角色/伏笔/时间线，因为没有 LLM 提取）
        tracker = Tracker(root / "_tracking-state.json")
        if tracker.exists():
            state = tracker.read()
            if state.last_updated_chapter is None or chapter > state.last_updated_chapter:
                state.last_updated_chapter = chapter
                state.last_updated_at = datetime.now(tz=UTC)
                tracker.write(state)

        logger.info(
            "V0.34 save: 第 %s 章已手动保存 %d 字到 %s",
            chapter,
            len(content),
            prose_path,
        )
        return {
            "chapter": chapter,
            "char_count": len(content),
            "output_path": str(prose_path),
        }

    # V0.34：AI 扩写（从当前字数继续写）
    @app.post("/api/chapter/{chapter}/expand")
    async def expand_chapter(
        chapter: int,
        request: Request,
        project_root: str = Form("."),
        skill: str = Form("story-long-write"),
        min_chars: int = Form(1000),
    ) -> dict[str, Any]:
        """V0.34：AI 扩写 — 从当前章节末尾继续写 N 字（基于 V0.32 智能恢复）。

        流程：
        1. 读取 chapter_prose(chapter) 当前内容
        2. 调 pipeline.write_chapter(resume_from_chars=len(current))
        3. 走 LLM → 流式 SSE 输出（与 V0.32 一致）

        注意：实际流式输出在 /api/write/stream/model；本端点仅作为元数据检查。
        实际扩写请用 POST /api/write/stream/model + resume_from_chars。
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter} not found. Use /api/write/stream/model first.",
            )
        current_content = prose_path.read_text(encoding="utf-8")
        return {
            "chapter": chapter,
            "current_chars": len(current_content),
            "expand_endpoint": "/api/write/stream/model",
            "form_params": {
                "chapter": chapter,
                "project_root": str(root).replace("\\", "/"),
                "skill": skill,
                "min_chars": min_chars,
                "resume_from_chars": len(current_content),
            },
            "hint": "POST 表单到 /api/write/stream/model 触发扩写",
        }

    # V0.38：AI 重写指定区段
    @app.post("/api/chapter/{chapter}/rewrite")
    async def rewrite_section(
        request: Request,  # V1.0.2 B4：注入 request 拿 user_id
        chapter: int,
        start: int = Form(...),
        end: int = Form(...),
        instruction: str = Form("改写得更生动自然"),
        project_root: str = Form("."),
        model: str | None = Form(None),
    ) -> dict[str, Any]:
        """V0.38：LLM 改写章节中指定字符范围 [start, end)。

        Args:
            start: 起始字符位置（0-based）
            end: 结束字符位置（exclusive）
            instruction: 改写指令（默认"改写得更生动自然"）

        Returns:
            dict 含 original / rewritten / start / end / chapter / model

        注意：本端点只生成 LLM 改写结果，不直接修改文件。
        前端应在用户确认后调 /api/chapter/{n}/save 应用修改。

        V1.0.2 B4：per-user LLM rate limit — user_id 从 session 取，
        超额返 429 + X-LLM-Tokens-Remaining=0。
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter} not found",
            )
        full_content = prose_path.read_text(encoding="utf-8")
        total = len(full_content)
        if start < 0 or end > total or start >= end:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid range [{start}:{end}] for content length {total}",
            )
        selected = full_content[start:end]
        before = full_content[:start]
        after = full_content[end:]

        # 调 LLM 改写
        from novel2all.cli.main import get_llm_for_model

        llm = get_llm_for_model(model)
        system = (
            "你是一位专业的中文小说编辑。根据用户指令改写指定段落，"
            "保持原文风格、人称和情节连续性，只输出改写后的段落文本本身（不含任何前后缀）。"
        )
        user_prompt = (
            f"##原文（{len(selected)} 字）\n{selected}\n\n"
            f"##改写要求\n{instruction}\n\n"
            "##输出要求\n只输出改写后的段落文本，不要加任何说明、注释、引号或前后缀。"
        )
        # V1.0.2 B4：注入 user_id 触发 rate limit
        current_user = get_request_user(request)
        user_id = current_user.id if current_user is not None else 0
        try:
            rewritten = await llm.complete(
                prompt=user_prompt,
                system=system,
                max_tokens=2000,
                temperature=0.7,
                user_id=user_id if user_id else None,
            )
        except Exception as e:
            logger.exception("V0.38 rewrite_section: LLM call failed")
            raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e
        rewritten_clean = rewritten.strip()
        logger.info(
            "V0.38 rewrite: 第 %s 章 [%s:%s] %s字 → %s字",
            chapter,
            start,
            end,
            len(selected),
            len(rewritten_clean),
        )
        return {
            "chapter": chapter,
            "start": start,
            "end": end,
            "original": selected,
            "rewritten": rewritten_clean,
            "before_len": len(before),
            "after_len": len(after),
            "model": model or "default",
        }

    # V0.38：在指定位置插入 AI 生成的内容
    @app.post("/api/chapter/{chapter}/insert")
    async def insert_at_position(
        request: Request,  # V1.0.2 B4：注入 request 拿 user_id
        chapter: int,
        position: int = Form(...),
        instruction: str = Form("自然衔接上下文的过渡段落"),
        project_root: str = Form("."),
        model: str | None = Form(None),
        context_chars: int = Form(500),
    ) -> dict[str, Any]:
        """V0.38：LLM 在 position 处生成可插入的内容（前后各取 context_chars 字上下文）。

        Returns:
            dict 含 position / inserted / chapter / model

        注意：本端点只生成 LLM 插入内容，不直接修改文件。
        前端应在用户确认后调 /api/chapter/{n}/save 应用修改。

        V1.0.2 B4：per-user LLM rate limit。
        """
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            raise HTTPException(status_code=404, detail="Project not initialized")
        prose_path = project.chapter_prose(chapter)
        if not prose_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter} not found",
            )
        full_content = prose_path.read_text(encoding="utf-8")
        total = len(full_content)
        if position < 0 or position > total:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid position {position} for content length {total}",
            )
        # 取上下文
        ctx_start = max(0, position - context_chars)
        ctx_end = min(total, position + context_chars)
        before_ctx = full_content[ctx_start:position]
        after_ctx = full_content[position:ctx_end]

        from novel2all.cli.main import get_llm_for_model

        llm = get_llm_for_model(model)
        system = (
            "你是一位专业的中文小说编辑。在小说指定位置插入自然衔接的段落，"
            "保持文风一致、人称一致、情节连续，只输出要插入的新段落文本本身（不含任何前后缀）。"
        )
        user_prompt = (
            f"##插入位置前的上下文（前 {len(before_ctx)} 字）\n{before_ctx}\n"
            f"[在此处插入新内容]\n"
            f"##插入位置后的上下文（后 {len(after_ctx)} 字）\n{after_ctx}\n\n"
            f"##插入要求\n{instruction}\n\n"
            "##输出要求\n只输出要插入的新段落文本，不要加任何说明、注释、引号或前后缀。"
        )
        # V1.0.2 B4：注入 user_id 触发 rate limit
        current_user = get_request_user(request)
        user_id = current_user.id if current_user is not None else 0
        try:
            inserted = await llm.complete(
                prompt=user_prompt,
                system=system,
                max_tokens=2000,
                temperature=0.7,
                user_id=user_id if user_id else None,
            )
        except Exception as e:
            logger.exception("V0.38 insert_at_position: LLM call failed")
            raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}") from e
        inserted_clean = inserted.strip()
        logger.info(
            "V0.38 insert: 第 %s 章 pos=%s → %s字",
            chapter,
            position,
            len(inserted_clean),
        )
        return {
            "chapter": chapter,
            "position": position,
            "inserted": inserted_clean,
            "before_ctx_len": len(before_ctx),
            "after_ctx_len": len(after_ctx),
            "model": model or "default",
        }

    @app.get("/api/outlines")
    async def list_outlines(project_root: str = ".") -> list[dict]:
        """列出项目下已有细纲。"""
        root = Path(project_root).resolve()
        project = ProjectStructure(root=root)
        if not project.exists():
            return []
        outline_dir = project.chapter_outline(1).parent
        if not outline_dir.exists():
            return []
        import re

        result: list[dict] = []
        for f in sorted(outline_dir.glob("细纲_第*章.md")):
            m = re.search(r"第(\d+)章", f.name)
            if not m:
                continue
            ch = int(m.group(1))
            result.append({"chapter": ch, "filename": f.name})
        return result

    @app.get("/api/write/stream")
    async def write_chapter_stream(
        request: Request,  # V0.29.3：lifespan 单例 provider（FastAPI 自动注入）
        chapter: int = Query(..., description="章节号"),
        project_root: str = Query(".", description="项目根目录"),
        skill: str = Query("story-long-write", description="使用的 skill"),
        min_chars: int = Query(2000, description="最低字数"),
        skip_pre_write: bool = Query(False, description="跳过 pre-write check"),
    ) -> StreamingResponse:
        """SSE 流式写作端点。

        V0.29.3：request 参数注入（用于获取 app.state.provider 单例）
        事件序列：
          - started: pipeline 启动
          - pre_write_check: pre-write check 结果（如有）
          - chunk: LLM 输出片段（多次，实时）
          - progress: 阶段切换
          - post_write_check: post-write check 结果
          - done: 完成（含 output_path, content_chars）
          - error: 出错
        """

        # V0.29.3：闭包捕获 request（FastAPI 不会自动注入到 inner async generator）
        async def event_stream() -> AsyncIterator[str]:
            # V0.29.3：用 lifespan 管理的单例 provider（cache 跨请求连续）
            llm: LLMProvider = request.app.state.provider
            root = Path(project_root).resolve()
            project = ProjectStructure(root=root)
            if not project.exists():
                yield sse_event(
                    "error",
                    {"message": f"项目未初始化: {root}. 请先跑 novel2all setup."},
                )
                return

            # started
            yield sse_event(
                "started",
                {
                    "chapter": chapter,
                    "skill": skill,
                    "min_chars": min_chars,
                    "skip_pre_write": skip_pre_write,
                    "project_root": str(root),
                },
            )

            # 构造 pipeline（用 lifespan 管理的单例 llm）
            try:
                manager = MemoryManager(project_root=root, llm=llm)
                skills_dir = Path(__file__).parent.parent / "skills"
                skill_registry = SkillRegistry(skills_dir)
                skill_registry.discover()
                pipeline = WritingPipeline(
                    manager=manager,
                    skill_registry=skill_registry,
                    llm=llm,
                    project=project,
                )
            except Exception as e:
                yield sse_event("error", {"message": f"Pipeline 初始化失败: {e}"})
                return

            # 用 asyncio.Queue 桥接 sync stream_callback → async generator
            chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
            collected: list[str] = []

            def on_chunk(text: str) -> None:
                collected.append(text)
                # 同步函数中塞入异步队列
                chunk_queue.put_nowait(text)

            async def run_pipeline() -> None:
                """在 task 中跑 pipeline，同时把 chunk 事件 yield 给前端。"""
                try:
                    await pipeline.write_chapter(
                        chapter=chapter,
                        outline_path=project.chapter_outline(chapter),
                        skill_name=skill,
                        stream_callback=on_chunk,
                        min_chars=min_chars,
                        skip_pre_write_check=skip_pre_write,
                    )
                finally:
                    # 即使 pipeline 异常也要 put sentinel，让 event_stream 能退出
                    await chunk_queue.put(None)

            try:
                # 后台跑 pipeline
                pipeline_task = asyncio.create_task(run_pipeline())

                # 实时消费 chunk 队列
                while True:
                    chunk = await chunk_queue.get()
                    if chunk is None:
                        break  # pipeline 完成
                    yield sse_event("chunk", {"text": chunk})

                # 等待 pipeline 完成并取结果
                result = await pipeline_task

                # pre_write_check 事件（如有）
                if result.pre_write_issues:
                    yield sse_event(
                        "pre_write_check",
                        {"issues": [issue.model_dump() for issue in result.pre_write_issues]},
                    )

                # 阶段事件
                yield sse_event(
                    "progress",
                    {"phase": "save", "message": f"已写文件: {result.output_path}"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "extract", "message": "提取角色/伏笔/时间线"},
                )
                yield sse_event(
                    "progress",
                    {"phase": "merge", "message": "合并到 tracking state"},
                )

                # post_write_check
                if result.post_write_issues:
                    yield sse_event(
                        "post_write_check",
                        {"issues": [issue.model_dump() for issue in result.post_write_issues]},
                    )

                # done
                yield sse_event(
                    "done",
                    {
                        "output_path": str(result.output_path),
                        "content_chars": result.content_chars,
                        "post_issue_count": len(result.post_write_issues),
                        "pre_issue_count": len(result.pre_write_issues),
                    },
                )

            except OutlineNotFoundError as e:
                yield sse_event("error", {"message": str(e), "code": "outline_not_found"})
            except BlockingIssuesError as e:
                yield sse_event(
                    "error",
                    {
                        "message": f"pre-write check 发现 {len(e.issues)} 个 critical 问题",
                        "code": "blocking_issues",
                        "issues": [issue.model_dump() for issue in e.issues],
                    },
                )
            except Exception as e:
                # 检查是否是 pipeline_task 异常
                if pipeline_task.done() and pipeline_task.exception():
                    exc = pipeline_task.exception()
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(exc).__name__}: {exc}"},
                    )
                else:
                    yield sse_event(
                        "error",
                        {"message": f"Pipeline 失败: {type(e).__name__}: {e}"},
                    )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # 防止 nginx 等缓冲
            },
        )

    # ============================================================
    # V1.5 React SPA mount（必须在所有 /api/* 路由注册之后）
    # ============================================================
    # __file__ = src/novel2all/web/app.py
    # parents[0] = web/, parents[1] = novel2all/, parents[2] = src/, parents[3] = 项目根
    _dist_dir = Path(__file__).resolve().parents[3] / "web-react" / "dist"
    if _dist_dir.exists():
        # 静态资源（JS / CSS / 图片等）
        _assets_dir = _dist_dir / "assets"
        if _assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(_assets_dir)),
                name="react-assets",
            )

        # favicon（Vite 默认输出 favicon.svg）
        @app.get("/favicon.ico", include_in_schema=False)
        async def favicon() -> FileResponse:
            return FileResponse(str(_dist_dir / "favicon.svg"), media_type="image/svg+xml")

        # SPA fallback — 未匹配的前端路径返回 index.html（让 React Router 处理）
        # 用 404 exception handler 而不是 catch-all 路由，原因：
        #   - catch-all `/{full_path:path}` 会在注册顺序上排在最后，可能吞掉测试
        #     在 create_app() 之后动态注入的端点（如 /test/boom）
        #   - 404 handler 只在确实没有匹配路由时才触发，更安全
        # 行为：
        #   - /api/* /docs /openapi.json /redoc /metrics /assets → 走 FastAPI 默认
        #     JSON 404（保留原始 detail，如 "task xxx 不存在"）
        #   - 其他路径（前端路由）→ 返回 SPA index.html
        from starlette.exceptions import HTTPException as StarletteHTTPException

        @app.exception_handler(StarletteHTTPException)
        async def _spa_404_handler(request: Request, exc: StarletteHTTPException) -> Response:
            """V1.5 React：404 → SPA index.html（除 API / docs / static）。"""
            if exc.status_code != 404:
                # 非 404 仍走 FastAPI 默认行为
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            path = request.url.path
            if path.startswith(
                (
                    "/api/",
                    "/assets",
                    "/docs",
                    "/openapi.json",
                    "/redoc",
                    "/metrics",
                )
            ):
                # API / docs / static 路径仍按 FastAPI 默认 404 JSON 返回
                # 保留 exc.detail（如 "task xxx 不存在或已完成"）
                return JSONResponse({"detail": exc.detail}, status_code=404)
            # 前端路径：返回 SPA index.html（让 React Router 处理）
            return FileResponse(str(_dist_dir / "index.html"))

        # 显式注册 / 避免被 catch-all 吞掉（其实 catch-all 已能匹配，
        # 但显式声明可让 OpenAPI / logs 更清晰）
        @app.get("/", include_in_schema=False)
        async def root_spa() -> FileResponse:
            return FileResponse(str(_dist_dir / "index.html"))
    else:
        # dist/ 不存在时的 fallback（开发阶段友好）
        @app.get("/", include_in_schema=False)
        async def root_no_dist() -> JSONResponse:
            return JSONResponse(
                {
                    "error": "V1.5 React dist not built",
                    "hint": "cd web-react && npm install && npm run build",
                    "api_docs": "/docs",
                }
            )

    return app
