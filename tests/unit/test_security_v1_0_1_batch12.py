"""V1.0.1 Batch 1+2：8 个 P0/P1 bug 修复测试。

覆盖：
  B1  cookie secure 标志（dev vs prod）
  B2  全局 500 exception handler（不泄露 stack trace）
  B3  /metrics 端点 IP 白名单
  B4  Dockerfile USER 行（lint 验证）
  B5  XFF trusted proxy 列表（CIDR 匹配）
  B6  /api/auth/projects/{path}/share 路径越权 + 项目存在性
  B7  /api/auth/login 用户名枚举防护（不记 username + 耗时对齐）
  B8  /api/chapter/{n}/review Idempotency-Key 防双击
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel2all.core.auth_middleware import (
    _client_ip_in_trusted,
    _parse_trusted_proxies,
    reset_trusted_proxy_cache,
)
from novel2all.core.memory import Tracker
from novel2all.web.app import InMemoryIdempotencyStore, _is_dev_mode, create_app

# === Fixtures（项目根目录带 _tracking-state.json + 正文/第001章.md） ===


@pytest.fixture
def initialized_project(tmp_path: Path) -> Path:
    """V1.0.1 Batch 1+2：创建一个最小可用项目结构。"""
    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(
        project_name="测试项目",
        genre="玄幻",
        style_anchor="古风古韵",
        total_chapters_target=10,
    )
    prose_dir = tmp_path / "正文"
    prose_dir.mkdir(exist_ok=True)
    (prose_dir / "第001章.md").write_text(
        "# 第 1 章\n\n林雷觉醒血脉，苍茫镇为之震动。\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def app_with_lifespan(tmp_path: Path) -> FastAPI:
    """V1.0.1 Batch 1+2：默认 FastAPI app（dev mode，无环境变量），state 已手动初始化。

    设计：lifespan 内的所有初始化代码都被手动复刻到一个 fixture helper 中，
    避免与 ``TestClient(app)`` 的 `with` 上下文管理器发生双重 lifespan 冲突。
    这给我们完整的 state 控制：每个测试用例独立目录 → 独立 DB。

    CWD 在 teardown 时恢复，避免污染后续 test 的相对路径访问。
    """
    os.environ.pop("NOVEL2ALL_DEBUG", None)
    os.environ.pop("DEBUG", None)

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        app = create_app()
        # 手动初始化所有依赖（避免与 TestClient 的 lifespan 上下文冲突）
        from novel2all.core.audit import AuditStore
        from novel2all.core.auth import AuthStore, RateLimiter
        from novel2all.core.session import SessionStore

        app.state.auth_store = AuthStore(db_path=tmp_path / "auth.db")
        app.state.session_store = SessionStore(db_path=tmp_path / "sessions.db")
        app.state.rate_limiter = RateLimiter()
        try:
            app.state.audit_store = AuditStore(db_path=tmp_path / "audit.db")
        except Exception:
            app.state.audit_store = None
        yield app
    finally:
        # 恢复 CWD（重要：避免污染后续 test 的相对路径访问）
        try:
            os.chdir(old_cwd)
        except OSError:
            pass


@pytest.fixture
def app() -> FastAPI:
    """V1.0.1 Batch 1+2：默认 FastAPI app（dev mode，无环境变量）。

    注意：仅触发 ``create_app``，lifespan 未运行。需要 auth state 的测试请用
    ``app_with_lifespan`` 或自行用 ``with TestClient(app) as client:`` 触发。
    """
    os.environ.pop("NOVEL2ALL_DEBUG", None)
    os.environ.pop("DEBUG", None)
    return create_app()


@pytest.fixture(autouse=True)
def _restore_env() -> Any:
    """V1.0.1 Batch 1+2：每个 test 后恢复环境变量 + 清除 trusted proxy 缓存。"""
    # 保存初始 CWD（在 pytest 自身任何 chdir 之后），避免后续 test 因相对路径
    # 解析失败。
    saved_cwd = os.getcwd()
    yield
    for var in (
        "NOVEL2ALL_DEBUG",
        "DEBUG",
        "TRUSTED_PROXIES",
        "NOVEL2ALL_TRUSTED_PROXIES",
        "METRICS_ALLOWED_IPS",
    ):
        os.environ.pop(var, None)
    reset_trusted_proxy_cache()
    # 恢复 CWD（保护后续 test 的相对路径访问）
    try:
        if os.getcwd() != saved_cwd:
            os.chdir(saved_cwd)
    except OSError:
        pass


# === B1: Cookie secure 标志 ===


class TestCookieSecureFlag:
    """V1.0.1 B1：dev 模式 secure=False，prod 模式 secure=True。"""

    def test_dev_mode_default_secure_false(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B1：默认（无环境变量）→ dev mode → secure=False。"""
        os.environ.pop("NOVEL2ALL_DEBUG", None)
        os.environ.pop("DEBUG", None)
        assert _is_dev_mode() is True

        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        client = TestClient(app)
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("alice", "secret_password", role="admin")

        resp = client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "secret_password"},
        )
        assert resp.status_code == 200, resp.text
        set_cookie = resp.headers.get("set-cookie", "")
        assert "n2a_session=" in set_cookie
        attrs = [a.strip() for a in set_cookie.split(";")]
        secure_attrs = [a for a in attrs if a.lower() == "secure"]
        assert secure_attrs == [], f"dev mode 不应有 Secure; got {set_cookie}"

    def test_prod_mode_secure_true(self) -> None:
        """V1.0.1 B1：NOVEL2ALL_DEBUG=false → prod mode → secure=True。"""
        os.environ["NOVEL2ALL_DEBUG"] = "false"
        assert _is_dev_mode() is False

        from novel2all.core.auth import AuthStore

        os.chdir(tempfile.mkdtemp())  # 新 tmpdir 避免 auth DB 冲突
        tc = TestClient(create_app())
        tc.__enter__()
        try:
            app = tc.app
            store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
            store.create_user("bob", "p", role="admin")

            resp = tc.post(
                "/api/auth/login",
                data={"username": "bob", "password": "p"},
            )
            assert resp.status_code == 200, resp.text
            set_cookie = resp.headers.get("set-cookie", "")
            attrs = [a.strip() for a in set_cookie.split(";")]
            secure_attrs = [a for a in attrs if a.lower() == "secure"]
            assert secure_attrs, f"prod mode 必有 Secure; got {set_cookie}"
        finally:
            tc.__exit__(None, None, None)

    def test_is_dev_mode_truthy_values(self) -> None:
        """V1.0.1 B1：'1'/'true'/'yes'/'on' 都视为 dev mode。"""
        for truthy in ("1", "true", "yes", "on", "TRUE", "True"):
            os.environ["NOVEL2ALL_DEBUG"] = truthy
            assert _is_dev_mode() is True, f"{truthy!r} 视为 dev mode"
        for falsy in ("0", "false", "no", "off", ""):
            os.environ["NOVEL2ALL_DEBUG"] = falsy
            assert _is_dev_mode() is False, f"{falsy!r} 不应视为 dev mode"


# === B2: 全局 exception handler ===


class TestGlobalExceptionHandler:
    """V1.0.1 B2：未捕获异常 → 500 + 不含 stack trace + 含 request_id。"""

    def test_exception_returns_500_without_traceback(self, app: FastAPI) -> None:
        """V1.0.1 B2：自定义端点抛 ValueError → 500，不含 'Traceback' 文本。"""

        @app.get("/test/boom")
        async def boom() -> None:
            raise ValueError("internal boom")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/test/boom")
            assert resp.status_code == 500
            body = resp.text
            # 关键断言：response body 不含 stack trace 痕迹
            assert "Traceback" not in body
            assert "ValueError: internal boom" not in body
            # 响应结构
            data = resp.json()
            assert data["detail"] == "Internal server error"
            assert "request_id" in data
            # request_id 是 16-char hex
            assert len(data["request_id"]) == 16
            int(data["request_id"], 16)  # 是合法 hex


# === B3: /metrics IP 白名单 ===


class TestMetricsAuth:
    """V1.0.1 B3：/metrics 端点仅 trusted IP 可见。"""

    def test_localhost_allowed(self) -> None:
        """V1.0.1 B3：TestClient 默认从 testclient（被 metrics middleware 视为非白名单）。"""
        os.environ.pop("METRICS_ALLOWED_IPS", None)
        # 默认白名单 = "127.0.0.1,::1"，但 TestClient 的 client.host 是 "testclient"
        # 因此默认配置下，TestClient 访问 /metrics 会被拒绝 → 403
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            # TestClient 走 ASGI scope 注入 client=("testclient", 50000)
            assert resp.status_code == 403
            assert "metrics endpoint only available from" in resp.json()["detail"]

    def test_localhost_allowed_with_whitelist(self) -> None:
        """V1.0.1 B3：把 'testclient' 加入白名单 → 通过。"""
        os.environ["METRICS_ALLOWED_IPS"] = "127.0.0.1,::1,testclient"
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]

    def test_non_localhost_rejected(self) -> None:
        """V1.0.1 B3：只允许 10.0.0.1 → TestClient 被拒 → 403。"""
        os.environ["METRICS_ALLOWED_IPS"] = "10.0.0.1"
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 403
            data = resp.json()
            assert "metrics endpoint only available from" in data["detail"]
            assert "10.0.0.1" in data["detail"]

    def test_default_whitelist(self) -> None:
        """V1.0.1 B3：未配置环境变量 → 默认白名单为 127.0.0.1 + ::1。"""
        os.environ.pop("METRICS_ALLOWED_IPS", None)
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 403
            # 默认 detail 应提及 127.0.0.1 和 ::1
            detail = resp.json()["detail"]
            assert "127.0.0.1" in detail
            assert "::1" in detail


# === B4: Dockerfile USER 行 ===


class TestDockerfileUserDirective:
    """V1.0.1 B4：Dockerfile 必须包含 USER 指令（非 root 运行）。"""

    def test_dockerfile_contains_user_directive(self) -> None:
        """V1.0.1 B4：Dockerfile 含 USER 行。"""
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        assert dockerfile.exists(), f"Dockerfile 未找到 at {dockerfile}"
        content = dockerfile.read_text(encoding="utf-8")
        # 至少一行以 USER 开头（非注释）
        user_lines = [
            line
            for line in content.splitlines()
            if line.strip().startswith("USER ") and not line.strip().startswith("#")
        ]
        assert user_lines, "Dockerfile 缺少 USER 指令（容器仍以 root 运行）"

    def test_dockerfile_user_not_root(self) -> None:
        """V1.0.1 B4：USER 后的用户名不是 root（防止 'USER root'）。"""
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("USER ") and not stripped.startswith("#"):
                user_part = stripped.split()[1]
                assert user_part != "root", f"Dockerfile 仍以 root 运行: {stripped!r}"


# === B5: XFF trusted proxies (CIDR) ===


class TestTrustedProxies:
    """V1.0.1 B5：get_client_ip 在 trusted proxy 内才采信 XFF。"""

    def test_default_no_trust_ignores_xff(self) -> None:
        """V1.0.1 B5：默认（无 TRUSTED_PROXIES）→ 忽略 XFF，用直连 IP。"""
        os.environ.pop("TRUSTED_PROXIES", None)
        os.environ.pop("NOVEL2ALL_TRUSTED_PROXIES", None)
        reset_trusted_proxy_cache()

        from fastapi import Request

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("1.2.3.4", 12345),
            "headers": [(b"x-forwarded-for", b"99.99.99.99")],
        }
        req = Request(scope)

        async def _check() -> str:
            from novel2all.core.auth_middleware import get_client_ip

            return await get_client_ip(req)

        result = asyncio.run(_check())
        assert result == "1.2.3.4"  # 忽略 XFF，用直连

    def test_trusted_loopback_respects_xff(self) -> None:
        """V1.0.1 B5：TRUSTED_PROXIES=127.0.0.1/32，client 在 trusted 内 → 信任 XFF。"""
        os.environ["TRUSTED_PROXIES"] = "127.0.0.1/32"
        reset_trusted_proxy_cache()

        from fastapi import Request

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.5")],
        }
        req = Request(scope)

        async def _check() -> str:
            from novel2all.core.auth_middleware import get_client_ip

            return await get_client_ip(req)

        result = asyncio.run(_check())
        assert result == "203.0.113.5"  # 采信 XFF

    def test_untrusted_client_still_ignores_xff(self) -> None:
        """V1.0.1 B5：client=1.2.3.4 不在 trusted 内 → 仍忽略 XFF。"""
        os.environ["TRUSTED_PROXIES"] = "10.0.0.0/8"
        reset_trusted_proxy_cache()

        from fastapi import Request

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("1.2.3.4", 12345),
            "headers": [(b"x-forwarded-for", b"10.0.0.5")],
        }
        req = Request(scope)

        async def _check() -> str:
            from novel2all.core.auth_middleware import get_client_ip

            return await get_client_ip(req)

        result = asyncio.run(_check())
        assert result == "1.2.3.4"  # 忽略 XFF

    def test_parse_trusted_proxies_handles_invalid(self) -> None:
        """V1.0.1 B5：TRUSTED_PROXIES 中的非法 CIDR 被跳过，不 crash。"""
        os.environ["TRUSTED_PROXIES"] = "127.0.0.1/32, not_an_ip, 10.0.0.0/8"
        reset_trusted_proxy_cache()

        nets = _parse_trusted_proxies()
        assert len(nets) == 2  # 1 个 invalid 被跳过
        assert _client_ip_in_trusted("127.0.0.1") is True
        assert _client_ip_in_trusted("10.5.5.5") is True
        assert _client_ip_in_trusted("8.8.8.8") is False

    def test_invalid_xff_entry_falls_back_to_direct(self) -> None:
        """V1.0.1 QA B5 fix：trusted 客户端 + 非法 XFF（垃圾字符串）→ fallback 到直连 IP。

        防止 XFF 注入攻击（恶意代理塞垃圾字符串污染日志/限流 key）。
        """
        os.environ["TRUSTED_PROXIES"] = "127.0.0.1/32"
        reset_trusted_proxy_cache()

        from fastapi import Request

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"not-an-ip-address")],
        }
        req = Request(scope)

        async def _check() -> str:
            from novel2all.core.auth_middleware import get_client_ip

            return await get_client_ip(req)

        result = asyncio.run(_check())
        # 不能原样返回垃圾字符串
        assert result != "not-an-ip-address", f"invalid XFF 不应被原样返回；got {result!r}"
        # fallback 到直连 IP
        assert result == "127.0.0.1", f"unexpected fallback: {result!r}"


# === B6: /api/auth/projects/{path}/share 路径越权 + 项目存在性 ===


class TestSharePathTraversal:
    """V1.0.1 B6：share 端点拒绝 .. 路径 + 绝对路径 + admin 项目授权检查。"""

    def _login_admin(self, app: FastAPI, client: TestClient) -> None:
        """V1.0.1 B6：登录 admin 并把 session cookie 写到 client。"""
        # Note: 不再需要显式获取 store —— admin 已在调用前由 test 创建。
        resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin_pass"},
        )
        assert resp.status_code == 200, resp.text

    def test_path_traversal_rejected(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B6：含 ``..`` 的路径 → 400。"""
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("admin", "admin_pass", role="admin")
        # admin 自身对某项目有 owner
        admin = store.get_user_by_username("admin")
        assert admin is not None
        store.grant_project_access(admin.id, str(Path.cwd() / "proj"), "owner", admin.id)

        client = TestClient(app)
        self._login_admin(app, client)
        resp = client.post(
            "/api/auth/projects/..%2F..%2Fetc%2Fpasswd/share",
            data={"user_id": 1, "role": "viewer"},
        )
        assert resp.status_code == 400
        assert ".." in resp.json()["detail"]

    def test_absolute_path_rejected(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B6：绝对路径 → 400。"""
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("admin", "admin_pass", role="admin")
        admin = store.get_user_by_username("admin")
        assert admin is not None
        store.grant_project_access(admin.id, str(Path.cwd() / "proj"), "owner", admin.id)

        client = TestClient(app)
        self._login_admin(app, client)
        resp = client.post(
            "/api/auth/projects/%2Fabsolute%2Fpath/share",
            data={"user_id": 1, "role": "viewer"},
        )
        assert resp.status_code == 400
        assert "absolute" in resp.json()["detail"].lower()

    def test_admin_without_project_access_rejected(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B6：admin 自身没有该项目的 owner/editor → 403。"""
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("admin", "admin_pass", role="admin")
        # admin 没有 grant 自己任何项目

        client = TestClient(app)
        self._login_admin(app, client)
        resp = client.post(
            "/api/auth/projects/myproj/share",
            data={"user_id": 1, "role": "viewer"},
        )
        assert resp.status_code == 403
        assert "owner/editor access" in resp.json()["detail"]

    def test_non_admin_rejected(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B6：非 admin 用户 → 403。"""
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("editor", "ep", role="editor")

        client = TestClient(app)
        resp = client.post(
            "/api/auth/login",
            data={"username": "editor", "password": "ep"},
        )
        assert resp.status_code == 200
        resp = client.post(
            "/api/auth/projects/myproj/share",
            data={"user_id": 1, "role": "viewer"},
        )
        assert resp.status_code == 403

    def test_admin_with_owner_access_succeeds(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B6：admin 自身已有 owner 权限 → share 成功。"""
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        admin = store.create_user("admin", "admin_pass", role="admin")
        victim = store.create_user("victim", "v", role="editor")
        # admin grant 自己 owner "proj" 路径（相对路径 "proj"）
        store.grant_project_access(admin.id, str(Path.cwd() / "proj"), "owner", admin.id)

        client = TestClient(app)
        self._login_admin(app, client)
        resp = client.post(
            "/api/auth/projects/proj/share",
            data={"user_id": victim.id, "role": "viewer"},
        )
        assert resp.status_code == 200, resp.text


# === B7: /api/auth/login 用户名枚举防护 ===


class TestLoginEnumerationProtection:
    """V1.0.1 B7：用户不存在 / 用户存在+密码错 的耗时对齐 + audit 不记 username。"""

    def test_login_failed_audit_omits_username(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B7：login_failed audit 不记 username（仅 ip）。"""
        from novel2all.core.audit import AuditStore
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        audit: AuditStore = app.state.audit_store  # type: ignore[attr-defined]

        client = TestClient(app)
        # 故意登录不存在的用户
        resp = client.post(
            "/api/auth/login",
            data={"username": "ghost_user_xyz", "password": "any_pass"},
        )
        assert resp.status_code == 401

        # 故意登录存在的用户但密码错
        store.create_user("real_user", "real_pass")
        resp = client.post(
            "/api/auth/login",
            data={"username": "real_user", "password": "wrong"},
        )
        assert resp.status_code == 401

        # 检查 audit log：username 字段必须是 None（不记用户名）
        events = audit.query(event_type="login_failed")
        assert len(events) == 2
        for ev in events:
            assert ev["username"] is None, f"login_failed 不应记 username; got {ev}"

    def test_login_response_time_equalized(self, app_with_lifespan: FastAPI) -> None:
        """V1.0.1 B7：用户存在 vs 不存在 响应时间差 < 50ms（消除时序侧信道）。"""
        from novel2all.core.auth import AuthStore

        app = app_with_lifespan
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("real_user", "correct_password")
        rate_limiter = app.state.rate_limiter  # type: ignore[attr-defined]

        client = TestClient(app)

        def measure_login(username: str, password: str) -> float:
            """V1.0.1 B7：测单次 login 的 wall-clock 耗时。"""
            # 重置 rate limiter 防止 5 次后触发 429 lockout（与本测试无关）
            rate_limiter._fail_counts.clear()  # type: ignore[attr-defined]
            rate_limiter._locked_until.clear()  # type: ignore[attr-defined]
            t0 = time.perf_counter()
            resp = client.post(
                "/api/auth/login",
                data={"username": username, "password": password},
            )
            elapsed = time.perf_counter() - t0
            assert resp.status_code == 401, f"期望 401 但得到 {resp.status_code}"
            return elapsed

        def median(values: list[float]) -> float:
            sorted_values = sorted(values)
            n = len(sorted_values)
            return sorted_values[n // 2]

        # 路径 A：用户存在 + 密码错
        times_existing = [measure_login("real_user", "wrong_password") for _ in range(3)]
        # 路径 B：用户不存在（dummy hash 路径）
        times_missing = [measure_login("ghost_user", "any_password") for _ in range(3)]

        median_existing = median(times_existing)
        median_missing = median(times_missing)
        diff_ms = abs(median_existing - median_missing) * 1000

        assert diff_ms < 50, (
            f"时序差异过大: existing={median_existing * 1000:.1f}ms "
            f"vs missing={median_missing * 1000:.1f}ms (diff={diff_ms:.1f}ms)"
        )


# === B8: /api/chapter/{n}/review Idempotency-Key 防双击 ===


class TestReviewIdempotency:
    """V1.0.1 B8：review 端点 Idempotency-Key 缓存（5 分钟 TTL）。"""

    def test_idempotency_store_basic(self) -> None:
        """V1.0.1 B8：InMemoryIdempotencyStore 基础 get/set。"""
        store = InMemoryIdempotencyStore(ttl_seconds=300)
        assert store.get((1, 1, "key")) is None
        store.set((1, 1, "key"), {"result": "ok"})
        cached = store.get((1, 1, "key"))
        assert cached == {"result": "ok"}

    def test_idempotency_store_ttl_expiry(self) -> None:
        """V1.0.1 B8：TTL 过期后 get 返回 None。"""
        store = InMemoryIdempotencyStore(ttl_seconds=0)  # 立即过期
        store.set((1, 1, "key"), "value")
        # 0 TTL → 立即过期
        assert store.get((1, 1, "key")) is None

    def test_idempotency_store_thread_safety(self) -> None:
        """V1.0.1 B8：threading.Lock 保护并发读写。"""
        import threading

        store = InMemoryIdempotencyStore(ttl_seconds=300)

        def writer(i: int) -> None:
            for j in range(100):
                store.set((i, j, f"key-{i}-{j}"), f"value-{i}-{j}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 不 crash = 通过
        store.clear()
        assert store.get((0, 0, "anything")) is None

    def test_review_same_key_returns_cached(self, initialized_project: Path) -> None:
        """V1.0.1 B8：同 key 同 chapter → 第二次返回缓存（不调 LLM）。"""
        import uuid as _uuid
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        app = create_app()
        idempotency_key = _uuid.uuid4().hex

        call_count = {"n": 0}

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            call_count["n"] += 1

            class _Report:
                def to_dict(self) -> dict[str, Any]:
                    return {
                        "total_critical": 0,
                        "total_major": 0,
                        "total_minor": 0,
                        "overall_verdict": "pass",
                        "elapsed_seconds": 0.1,
                        "content_chars": 100,
                        "chapter_number": 1,
                        "call_seq": call_count["n"],
                    }

            return _Report()

        # 不使用 `with` 触发生命周期 → state 不被覆盖
        client = TestClient(app)
        with patch.object(MultiAgentReviewer, "review", new=fake_review):
            # 第一次
            resp1 = client.post(
                f"/api/chapter/1/review?project_root={initialized_project}",
                headers={"Idempotency-Key": idempotency_key},
            )
            assert resp1.status_code == 200, resp1.text
            assert call_count["n"] == 1

            # 第二次（同 key 同 chapter）→ 应返回缓存
            resp2 = client.post(
                f"/api/chapter/1/review?project_root={initialized_project}",
                headers={"Idempotency-Key": idempotency_key},
            )
            assert resp2.status_code == 200
            assert call_count["n"] == 1, f"应只调 1 次 LLM；call_count={call_count['n']}"
            assert resp2.json().get("_idempotent_replay") is True

    def test_review_different_chapter_calls_llm_again(self, initialized_project: Path) -> None:
        """V1.0.1 B8：同 key 不同 chapter → 第二次仍调 LLM（per-chapter 维度）。"""
        import uuid as _uuid
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        # 给第二个章节也建文件
        (initialized_project / "正文" / "第002章.md").write_text(
            "# 第 2 章\n\n继续修炼。\n",
            encoding="utf-8",
        )

        app = create_app()
        idempotency_key = _uuid.uuid4().hex

        call_count = {"n": 0}

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            call_count["n"] += 1

            class _Report:
                def to_dict(self) -> dict[str, Any]:
                    return {
                        "total_critical": 0,
                        "total_major": 0,
                        "total_minor": 0,
                        "overall_verdict": "pass",
                        "elapsed_seconds": 0.1,
                        "content_chars": 100,
                        "chapter_number": kwargs.get("chapter_number", 0),
                    }

            return _Report()

        client = TestClient(app)
        with patch.object(MultiAgentReviewer, "review", new=fake_review):
            resp1 = client.post(
                f"/api/chapter/1/review?project_root={initialized_project}",
                headers={"Idempotency-Key": idempotency_key},
            )
            assert resp1.status_code == 200

            resp2 = client.post(
                f"/api/chapter/2/review?project_root={initialized_project}",
                headers={"Idempotency-Key": idempotency_key},
            )
            assert resp2.status_code == 200
            assert call_count["n"] == 2, "不同 chapter 应独立缓存"
            assert "_idempotent_replay" not in resp2.json()

    def test_review_ttl_expiry_calls_llm_again(self, initialized_project: Path) -> None:
        """V1.0.1 B8：TTL 过期后 → 重新调 LLM。"""
        import uuid as _uuid
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        app = create_app()
        # 把 TTL 改到 0（立即过期）。必须在 TestClient 之前设置（避免 `with` 触发
        # lifespan 重置）。
        app.state.idempotency_store = InMemoryIdempotencyStore(ttl_seconds=0)

        idempotency_key = _uuid.uuid4().hex
        call_count = {"n": 0}

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            call_count["n"] += 1

            class _Report:
                def to_dict(self) -> dict[str, Any]:
                    return {
                        "total_critical": 0,
                        "total_major": 0,
                        "total_minor": 0,
                        "overall_verdict": "pass",
                        "elapsed_seconds": 0.1,
                        "content_chars": 100,
                        "chapter_number": 1,
                    }

            return _Report()

        client = TestClient(app)
        with patch.object(MultiAgentReviewer, "review", new=fake_review):
            resp1 = client.post(
                f"/api/chapter/1/review?project_root={initialized_project}",
                headers={"Idempotency-Key": idempotency_key},
            )
            assert resp1.status_code == 200

            resp2 = client.post(
                f"/api/chapter/1/review?project_root={initialized_project}",
                headers={"Idempotency-Key": idempotency_key},
            )
            assert resp2.status_code == 200
            # TTL=0 → 立即过期 → 第 2 次应调 LLM
            assert call_count["n"] == 2, "TTL 过期后应重新调 LLM"

    def test_idempotency_concurrent_same_key_only_one_llm_call(
        self, initialized_project: Path
    ) -> None:
        """V1.0.1 B8 race condition fix：5 线程同 key 并发调 → 只调 1 次 LLM。

        修复前（race condition）：所有线程同时看到 ``cached = None``，
        全部调 LLM（5 次 LLM 调用）。
        修复后：``claim()`` 原子占位 → 第一个跑 LLM，其他 4 个等结果后
        共享同一 response（全部 200，LLM 仅 1 次）。
        """
        import threading
        import uuid as _uuid
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        app = create_app()
        idempotency_key = _uuid.uuid4().hex

        call_count = {"n": 0}
        call_lock = threading.Lock()

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            with call_lock:
                call_count["n"] += 1
            # 模拟 LLM 50ms 延迟，让 race window 充分
            import asyncio as _asyncio

            await _asyncio.sleep(0.05)

            class _Report:
                def to_dict(self) -> dict[str, Any]:
                    return {
                        "total_critical": 0,
                        "total_major": 0,
                        "total_minor": 0,
                        "overall_verdict": "pass",
                        "elapsed_seconds": 0.05,
                        "content_chars": 100,
                        "chapter_number": 1,
                    }

            return _Report()

        results: list[int] = []
        errors: list[str] = []

        def hit() -> None:
            try:
                # 每个线程独立 TestClient（模拟真实并发场景）
                client = TestClient(app)
                resp = client.post(
                    f"/api/chapter/1/review?project_root={initialized_project}",
                    headers={"Idempotency-Key": idempotency_key},
                )
                results.append(resp.status_code)
            except Exception as e:
                errors.append(str(e))

        with patch.object(MultiAgentReviewer, "review", new=fake_review):
            threads = [threading.Thread(target=hit) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors, f"并发调用出错: {errors}"
        # 关键：5 个并发 → 全部 200（要么 200 replay，要么 409 in-flight timeout）
        # 这里 poll-based wait 保证全部 200（共享结果）
        non_200 = [r for r in results if r not in (200, 409)]
        assert not non_200, f"Unexpected status codes: {non_200}"
        assert call_count["n"] == 1, (
            f"5 线程同 key 应只调 1 次 LLM；got {call_count['n']} 次（race condition！）"
        )
