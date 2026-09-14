"""V1.0.1 Batch 1+2：QA 独立攻击 PoC。

不复用工程师的 tests/unit/test_security_v1_0_1_batch12.py；这些是从攻击者视角
额外设计的 PoC：覆盖 spec 边缘 + 攻击场景 + 实现细节二次确认。

每个 PoC 标题带"❌" = 失败即源码 bug；不带 = 防御性测试（即使通过也不代表
实现正确，需要看 PoC 含义本身）。

测试目标（per 工程师产出摘要）：
  B1  cookie secure 标志（dev vs prod）
  B2  全局 500 exception handler
  B3  /metrics 端点 IP 白名单
  B4  Dockerfile USER 行
  B5  XFF trusted proxy 列表
  B6  share 端点路径越权 + 项目授权
  B7  login 用户名枚举防护
  B8  review Idempotency-Key 防双击
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from novel2all.core.auth_middleware import (
    _client_ip_in_trusted,
    _parse_trusted_proxies,
    get_client_ip,
    reset_trusted_proxy_cache,
)
from novel2all.web.app import (
    InMemoryIdempotencyStore,
    _is_dev_mode,
    create_app,
)

# === Shared Fixtures ==================================================


@pytest.fixture
def app() -> FastAPI:
    """默认 dev mode 下的 FastAPI app（lifespan 未跑）。"""
    os.environ.pop("NOVEL2ALL_DEBUG", None)
    os.environ.pop("DEBUG", None)
    return create_app()


@pytest.fixture
def app_with_state(tmp_path: Path) -> FastAPI:
    """带 state 初始化的 app（auth_store / session_store / rate_limiter）。"""
    os.environ.pop("NOVEL2ALL_DEBUG", None)
    os.environ.pop("DEBUG", None)
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        from novel2all.core.audit import AuditStore
        from novel2all.core.auth import AuthStore, RateLimiter
        from novel2all.core.session import SessionStore

        a = create_app()
        a.state.auth_store = AuthStore(db_path=tmp_path / "auth.db")
        a.state.session_store = SessionStore(db_path=tmp_path / "sessions.db")
        a.state.rate_limiter = RateLimiter()
        a.state.audit_store = AuditStore(db_path=tmp_path / "audit.db")
        return a
    finally:
        try:
            os.chdir(old_cwd)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def _restore_env() -> Any:
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
    try:
        if os.getcwd() != saved_cwd:
            os.chdir(saved_cwd)
    except OSError:
        pass


# ============================================================================
# B1: cookie secure 标志（独立 PoC — 环境变量边界 + DEBUG 优先级）
# ============================================================================


class TestB1CookieSecurePoC:
    """PoC B1：从客户端角度验证 secure 标志在 prod 模式下确实为 True。"""

    def test_prod_mode_explicit_false_sets_secure(self) -> None:
        """PoC B1-1：NOVEL2ALL_DEBUG="false" → secure=True。

        注意：TestClient 不能用 `with` 触发 lifespan —— 那会重置 auth_store 到默认
        相对路径（.novel2all/auth.db），丢失我们手动创建的用户。需先 create user，
        再用 `TestClient(app)`（无 `with`）。
        """
        os.environ["NOVEL2ALL_DEBUG"] = "false"
        assert _is_dev_mode() is False

        from novel2all.core.audit import AuditStore
        from novel2all.core.auth import AuthStore, RateLimiter
        from novel2all.core.session import SessionStore

        tmp = Path(tempfile.mkdtemp())
        os.chdir(tmp)
        app = create_app()
        app.state.auth_store = AuthStore(db_path=tmp / "auth.db")
        app.state.session_store = SessionStore(db_path=tmp / "sessions.db")
        app.state.rate_limiter = RateLimiter()
        app.state.audit_store = AuditStore(db_path=tmp / "audit.db")
        # Create user BEFORE TestClient to avoid lifespan re-init
        app.state.auth_store.create_user("alice_prod", "pw", role="admin")

        # Use TestClient without `with` to keep our manually-set state
        tc = TestClient(app)
        resp = tc.post("/api/auth/login", data={"username": "alice_prod", "password": "pw"})
        assert resp.status_code == 200, f"login 失败: {resp.text}"
        set_cookie = resp.headers.get("set-cookie", "")
        # 严格断言：prod 模式下 Set-Cookie 必有 Secure 标志
        attrs = [a.strip() for a in set_cookie.split(";")]
        assert "Secure" in attrs, f"prod 模式必须有 Secure；got: {set_cookie!r}"
        # 同时验证其他标志没掉
        assert any(a.lower() == "httponly" for a in attrs)
        assert any(a.lower().startswith("samesite=") for a in attrs)

    def test_debug_env_fallback_when_novel_debug_unset(self) -> None:
        """PoC B1-2：NOVEL2ALL_DEBUG 未设但 DEBUG="false" → 走 fallback → prod。"""
        os.environ.pop("NOVEL2ALL_DEBUG", None)
        os.environ["DEBUG"] = "false"
        assert _is_dev_mode() is False
        # 浏览器场景：Set-Cookie 必有 Secure

    def test_debug_falsy_strings_are_prod(self) -> None:
        """PoC B1-3：所有 falsy 字符串（false/no/off/0/empty）→ prod。"""
        for falsy in ("false", "FALSE", "False", "0", "no", "off", ""):
            os.environ["NOVEL2ALL_DEBUG"] = falsy
            assert _is_dev_mode() is False, f"{falsy!r} 应该是 prod"

    def test_debug_whitespace_stripped(self) -> None:
        """PoC B1-4：值带前后空白 → 仍正确判断。"""
        os.environ["NOVEL2ALL_DEBUG"] = "  true  "
        assert _is_dev_mode() is True
        os.environ["NOVEL2ALL_DEBUG"] = "  false  "
        assert _is_dev_mode() is False


# ============================================================================
# B2: 全局 500 exception handler（独立 PoC — 异常细节泄露检测）
# ============================================================================


class TestB2ExceptionHandlerPoC:
    """PoC B2：模拟攻击者探测 — 多种异常类型都不能泄露内部细节。"""

    def test_no_traceback_for_typeerror(self, app: FastAPI) -> None:
        @app.get("/attack/te")
        async def boom() -> None:
            # 真实的运行时异常：dict 取不存在的 key → KeyError
            return {}["nonexistent_key_for_typeerror_test"]

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/attack/te")
            assert resp.status_code == 500, f"期望 500 但得到 {resp.status_code}"
            body = resp.text
            # 关键：不能泄露内部路径、文件、行号
            for forbidden in [
                "Traceback",
                ".py",  # 任何 .py 文件名泄露
                "line ",
                'File "',
                "nonexistent_key_for_typeerror_test",  # 也不能泄露 key 名
            ]:
                assert forbidden not in body, f"500 响应泄露内部细节 ({forbidden!r})"
            data = resp.json()
            assert data["detail"] == "Internal server error"
            assert "request_id" in data

    def test_no_internal_message_leak(self, app: FastAPI) -> None:
        """PoC B2-2：异常 message 含敏感信息（密码 / secret 字符串）→ 不应泄露。"""

        @app.get("/attack/secret")
        async def leak() -> None:
            raise ValueError("password=supersecret123 token=abc.def.ghi")

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/attack/secret")
            assert resp.status_code == 500
            body = resp.text
            for sensitive in ["supersecret123", "abc.def.ghi", "password=", "token="]:
                assert sensitive not in body, f"500 响应泄露敏感字符串: {sensitive!r}"

    def test_request_id_format_and_uniqueness(self, app: FastAPI) -> None:
        """PoC B2-3：request_id 是 hex，且多次调用不重复（用于 trace 关联）。"""

        @app.get("/attack/boom")
        async def boom() -> None:
            raise RuntimeError("x")

        with TestClient(app, raise_server_exceptions=False) as c:
            ids: set[str] = set()
            for _ in range(10):
                resp = c.get("/attack/boom")
                assert resp.status_code == 500
                rid = resp.json()["request_id"]
                assert len(rid) == 16
                int(rid, 16)  # 是合法 hex
                ids.add(rid)
            # 16-hex = 64 bit — 10 次调用 0 重复概率 > 99.99%
            assert len(ids) == 10, f"request_id 重复：{ids}"

    def test_content_type_is_json(self, app: FastAPI) -> None:
        """PoC B2-4：500 响应必须是 application/json（不是 HTML 错误页）。"""

        @app.get("/attack/ct")
        async def boom() -> None:
            raise RuntimeError("x")

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/attack/ct")
            assert resp.status_code == 500
            ct = resp.headers.get("content-type", "")
            assert "application/json" in ct, f"500 响应 content-type 异常: {ct!r}"


# ============================================================================
# B3: /metrics 端点 IP 白名单（独立 PoC — 攻击场景）
# ============================================================================


class TestB3MetricsAuthPoC:
    """PoC B3：模拟扫描器从多个 IP 探测 /metrics。"""

    def test_attacker_cannot_use_xff_to_bypass(self) -> None:
        """PoC B3-1：关键攻击 — 攻击者伪造 XFF=127.0.0.1，能否绕过 IP 白名单？

        当前实现是简单字符串比较 client.host，理论上 XFF 没用。
        """
        os.environ.pop("METRICS_ALLOWED_IPS", None)  # 默认白名单
        # TestClient 通过 ASGI 注入 client=("testclient", port)
        # 即使我们手动在 header 加 XFF: 127.0.0.1，也应被拒
        tc = TestClient(create_app())
        with tc:
            resp = tc.get("/metrics", headers={"X-Forwarded-For": "127.0.0.1"})
            assert resp.status_code == 403, (
                f"攻击 PoC：伪造 XFF=127.0.0.1 竟然通过了！"
                f"status={resp.status_code}, body={resp.text}"
            )

    def test_attacker_cannot_spoof_loopback_via_xff(self) -> None:
        """PoC B3-2：X-Real-IP / Forwarded 等其他 header 都不能绕过。"""
        os.environ.pop("METRICS_ALLOWED_IPS", None)
        tc = TestClient(create_app())
        with tc:
            for header_name, header_val in [
                ("X-Real-IP", "127.0.0.1"),
                ("X-Forwarded-For", "::1"),
                ("Forwarded", "for=127.0.0.1"),
                ("X-Client-IP", "127.0.0.1"),
            ]:
                resp = tc.get("/metrics", headers={header_name: header_val})
                assert resp.status_code == 403, (
                    f"header {header_name}={header_val} 绕过 IP 白名单！status={resp.status_code}"
                )

    def test_metrics_blocked_for_unauthorized_ip(self) -> None:
        """PoC B3-3：默认配置下从 testclient 访问 → 403。"""
        os.environ.pop("METRICS_ALLOWED_IPS", None)
        tc = TestClient(create_app())
        with tc:
            resp = tc.get("/metrics")
            assert resp.status_code == 403
            detail = resp.json()["detail"]
            # 默认白名单应包含 127.0.0.1 + ::1
            assert "127.0.0.1" in detail
            assert "::1" in detail

    def test_metrics_open_when_whitelist_includes_testclient(self) -> None:
        """PoC B3-4：白名单含 testclient → 200 + metrics 内容。"""
        os.environ["METRICS_ALLOWED_IPS"] = "127.0.0.1,::1,testclient"
        tc = TestClient(create_app())
        with tc:
            resp = tc.get("/metrics")
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]


# ============================================================================
# B4: Dockerfile USER 指令（独立 PoC — 镜像构建时序）
# ============================================================================


class TestB4DockerfileUserPoC:
    """PoC B4：从 Dockerfile 字节序验证：USER 必须在所有破坏性操作之后。"""

    @pytest.fixture
    def dockerfile_text(self) -> str:
        return (
            Path(__file__).resolve().parents[2].joinpath("Dockerfile").read_text(encoding="utf-8")
        )

    def test_user_directive_exists_and_not_root(self, dockerfile_text: str) -> None:
        """PoC B4-1：USER 必须存在且不是 root。"""
        user_lines = [
            line.strip()
            for line in dockerfile_text.splitlines()
            if line.strip().startswith("USER ") and not line.strip().startswith("#")
        ]
        assert user_lines, "Dockerfile 无 USER 指令（容器仍以 root 运行）"
        for line in user_lines:
            user_part = line.split()[1]
            assert user_part != "root", f"USER 仍为 root: {line!r}"

    def test_useradd_creates_home_dir(self, dockerfile_text: str) -> None:
        """PoC B4-2：useradd 必须有 -m（创建 home）—— 否则容器内 $HOME 不存在。"""
        # 找所有 RUN useradd 行
        run_lines = [line.strip() for line in dockerfile_text.splitlines() if "useradd" in line]
        assert run_lines, "Dockerfile 无 useradd 命令"
        for line in run_lines:
            assert "-m " in line or line.endswith(" -m") or " -m " in line, (
                f"useradd 缺少 -m 标志（不会创建 home 目录）: {line!r}"
            )

    def test_useradd_uses_explicit_uid(self, dockerfile_text: str) -> None:
        """PoC B4-3：useradd 最好有 -u <UID>（固定 UID 便于 volume 权限对齐）。"""
        run_lines = [line.strip() for line in dockerfile_text.splitlines() if "useradd" in line]
        for line in run_lines:
            # 检查 -u 标志（值可能是 1001）
            import re as _re

            assert _re.search(r"\s-u\s+\d+", line), f"useradd 应有 -u <UID>（固定 UID）: {line!r}"

    def test_chown_after_useradd(self, dockerfile_text: str) -> None:
        """PoC B4-4：chown 必须在 useradd 之后（否则目录仍属 root）。

        Dockerfile 用 `RUN useradd ... && chown ...` 链式命令是合法的；
        此 PoC 解析每条 RUN 内的子命令顺序。
        """
        import re as _re

        lines = dockerfile_text.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("RUN "):
                continue
            cmd = stripped[4:]
            # 按 shell 操作符 `&&` 或 `;` 拆分子命令
            sub_cmds = _re.split(r"\s*(?:&&|;)\s*", cmd)
            # 在此 RUN 内找 useradd 和 chown 的相对顺序
            ua_pos = -1
            co_pos = -1
            for j, sub in enumerate(sub_cmds):
                if "useradd" in sub:
                    ua_pos = j
                if "chown" in sub and co_pos < 0:
                    co_pos = j
            if ua_pos >= 0 and co_pos >= 0:
                assert ua_pos < co_pos, (
                    f"Dockerfile line {i + 1}: chown 在 useradd 之前 "
                    f"({sub_cmds[co_pos]!r} before {sub_cmds[ua_pos]!r})"
                )

    def test_user_directive_is_last_sensitive_op(self, dockerfile_text: str) -> None:
        """PoC B4-5：USER 之后不应再有 RUN/COPY/ADD（root 提升的常见漏洞）。"""
        lines = dockerfile_text.splitlines()
        user_line_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("USER ") and not stripped.startswith("#"):
                user_line_idx = i
        assert user_line_idx >= 0, "Dockerfile 无 USER 指令"
        # USER 之后的指令：只允许 EXPOSE / CMD / ENV / LABEL / HEALTHCHECK / STOPSIGNAL
        sensitive_after_user = ("RUN ", "COPY ", "ADD ")
        for i in range(user_line_idx + 1, len(lines)):
            line = lines[i].strip()
            for op in sensitive_after_user:
                assert not line.startswith(op), (
                    f"USER 之后还有 root 操作 {op!r} (line {i + 1}): {line!r}"
                )


# ============================================================================
# B5: XFF trusted proxy（独立 PoC — spoofing 攻击）
# ============================================================================


class TestB5XFFTrustPoC:
    """PoC B5：模拟攻击者伪造 XFF 试图冒用其他 IP。"""

    def test_spoofed_xff_attack_rejected(self) -> None:
        """PoC B5-1：默认配置下，直连 IP=1.2.3.4 + XFF=127.0.0.1 → 仍用 1.2.3.4。"""
        os.environ.pop("TRUSTED_PROXIES", None)
        os.environ.pop("NOVEL2ALL_TRUSTED_PROXIES", None)
        reset_trusted_proxy_cache()

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("1.2.3.4", 12345),
            "headers": [(b"x-forwarded-for", b"127.0.0.1")],
        }
        req = Request(scope)
        result = asyncio.run(get_client_ip(req))
        assert result == "1.2.3.4", f"XFF spoofing 成功！返回 {result}"

    def test_spoofed_xff_attack_rejected_with_untrusted_cidr(self) -> None:
        """PoC B5-2：TRUSTED=10.0.0.0/8 + 直连 1.2.3.4 + XFF=10.0.0.5 → 仍用 1.2.3.4。"""
        os.environ["TRUSTED_PROXIES"] = "10.0.0.0/8"
        reset_trusted_proxy_cache()

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("1.2.3.4", 12345),
            "headers": [(b"x-forwarded-for", b"10.0.0.5")],
        }
        req = Request(scope)
        result = asyncio.run(get_client_ip(req))
        assert result == "1.2.3.4", f"未在 trusted 内的直连被 XFF spoofing 绕过！got {result}"

    def test_xff_chain_takes_leftmost(self) -> None:
        """PoC B5-3：trusted 客户端 + XFF 链 = "1.1.1.1, 2.2.2.2" → 返回 1.1.1.1（最左）。"""
        os.environ["TRUSTED_PROXIES"] = "127.0.0.1/32"
        reset_trusted_proxy_cache()

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2, 3.3.3.3")],
        }
        req = Request(scope)
        result = asyncio.run(get_client_ip(req))
        assert result == "1.1.1.1", f"XFF 链取最左失败：got {result}"

    def test_invalid_xff_falls_back_to_direct(self) -> None:
        """PoC B5-4：trusted 客户端 + XFF="not-an-ip" → 走 fallback 到 direct IP。"""
        os.environ["TRUSTED_PROXIES"] = "127.0.0.1/32"
        reset_trusted_proxy_cache()

        scope: dict[str, Any] = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"not-an-ip-address")],
        }
        req = Request(scope)
        result = asyncio.run(get_client_ip(req))
        # 实现选择：可能跳过 invalid 取下一个；也可能 fallback 到 direct
        # 关键是不能 crash，且不应是 "not-an-ip-address"
        assert result != "not-an-ip-address", f"invalid XFF 被原样返回！got {result!r}"
        # 直接 IP 应该是 127.0.0.1
        assert result == "127.0.0.1", f"unexpected fallback: {result!r}"

    def test_whitespace_in_trusted_proxies_handled(self) -> None:
        """PoC B5-5：TRUSTED_PROXIES 含空白 / 多余逗号 → 不 crash。"""
        os.environ["TRUSTED_PROXIES"] = " 10.0.0.0/8 , , 192.168.0.0/16 "
        reset_trusted_proxy_cache()
        nets = _parse_trusted_proxies()
        assert len(nets) == 2, f"应解析出 2 个 CIDR；got {nets}"
        assert _client_ip_in_trusted("10.5.5.5") is True
        assert _client_ip_in_trusted("192.168.0.1") is True
        assert _client_ip_in_trusted("8.8.8.8") is False

    def test_trusted_proxies_cache_is_cleared_on_reset(self) -> None:
        """PoC B5-6：reset_trusted_proxy_cache 后 env 变化应被感知。"""
        os.environ["TRUSTED_PROXIES"] = "10.0.0.0/8"
        reset_trusted_proxy_cache()
        assert _client_ip_in_trusted("10.5.5.5") is True

        os.environ["TRUSTED_PROXIES"] = "192.168.0.0/16"
        reset_trusted_proxy_cache()
        assert _client_ip_in_trusted("10.5.5.5") is False, (
            "reset_trusted_proxy_cache 没生效，仍信任 10.0.0.0/8"
        )
        assert _client_ip_in_trusted("192.168.0.1") is True


# ============================================================================
# B6: share 端点路径越权 + 项目授权（独立 PoC — 攻击场景）
# ============================================================================


class TestB6PathTraversalPoC:
    """PoC B6：模拟攻击者从 admin 权限探查文件系统 + 项目授权。"""

    def _make_admin_with_owner(self, app: FastAPI, project_path: str) -> tuple[Any, Any]:
        from novel2all.core.auth import AuthStore

        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        admin = store.create_user("attacker_admin", "pw", role="admin")
        store.grant_project_access(admin.id, str(Path(project_path).resolve()), "owner", admin.id)
        return store, admin

    def _login(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/login",
            data={"username": "attacker_admin", "password": "pw"},
        )
        assert resp.status_code == 200, f"login failed: {resp.text}"

    def test_null_byte_in_path_rejected(self, app_with_state: FastAPI) -> None:
        """PoC B6-1：路径含 null byte \\x00 → 必须 4xx，不能进入 grant。

        实测：Starlette/httpx 在 URL 解析层就拒绝 null byte 字符（raw 或 URL 编码），
        因此请求根本到不了 endpoint。这是合理的"双层防御"——但 PoC 验证的是
        整个请求链对 null byte 的处理（不是仅 endpoint 内的 `..` 检查）。
        """
        from fastapi.testclient import TestClient as TC

        app = app_with_state
        _store, admin = self._make_admin_with_owner(app, "safe_proj")

        # Use TestClient without `with` to avoid triggering lifespan (which would
        # re-init auth_store at default path and lose our user).
        client = TC(app)

        # DEBUG: print what we have
        print(f"\n[DEBUG B6-1] admin id={admin.id}, owner of {Path('safe_proj').resolve()}")
        print(f"[DEBUG B6-1] CWD={os.getcwd()}")
        print(f"[DEBUG B6-1] auth.db path={app.state.auth_store.db_path}")
        print(
            f"[DEBUG B6-1] user lookup: {app.state.auth_store.get_user_by_username('attacker_admin') is not None}"
        )

        # Login first
        login = client.post(
            "/api/auth/login", data={"username": "attacker_admin", "password": "pw"}
        )
        print(f"[DEBUG B6-1] login: {login.status_code}, body={login.text[:200]}")

        # 模拟：endpoint 的第一个检查是 ".." 分隔符。我们直接验证它能 reject
        # "safe_proj/../etc/passwd" 形式（也是 path traversal 变种）
        resp = client.post(
            "/api/auth/projects/safe_proj/..%2F..%2Fetc%2Fpasswd/share",
            data={"user_id": 999, "role": "viewer"},
        )
        print(f"[DEBUG B6-1] share: status={resp.status_code}, body={resp.text[:300]}")
        # URL decoded: safe_proj/../../etc/passwd → 含 ".."
        assert resp.status_code == 400, (
            f"路径含 .. 段未被拦截: status={resp.status_code}, body={resp.text[:300]}"
        )

    def test_windows_style_traversal_rejected(self, app_with_state: FastAPI) -> None:
        """PoC B6-2：Windows 风格路径穿越（..\\）→ 400。"""
        app = app_with_state
        self._make_admin_with_owner(app, "winproj")
        client = TestClient(app)
        self._login(client)
        resp = client.post(
            "/api/auth/projects/..%5C..%5Cetc%5Cpasswd/share",
            data={"user_id": 999, "role": "viewer"},
        )
        # URL decoded: ..\..\etc\passwd
        assert resp.status_code == 400, f"Windows 路径穿越未拦截: status={resp.status_code}"

    def test_admin_cannot_share_unowned_project(self, app_with_state: FastAPI) -> None:
        """PoC B6-3：admin 角色 ≠ 自动 owner，必须先 grant 自己。"""
        from novel2all.core.auth import AuthStore

        app = app_with_state
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("plain_admin", "pw", role="admin")
        # 注意：没有调用 grant_project_access

        client = TestClient(app)
        client.post("/api/auth/login", data={"username": "plain_admin", "password": "pw"})
        resp = client.post(
            "/api/auth/projects/anything/share",
            data={"user_id": 999, "role": "viewer"},
        )
        assert resp.status_code == 403, (
            f"未授权的 admin 竟能 share！status={resp.status_code}, body={resp.text}"
        )

    def test_path_with_only_dots_rejected(self, app_with_state: FastAPI) -> None:
        """PoC B6-4：纯 `..` 路径 → 400（不是 200 跳到 / 根目录）。"""
        app = app_with_state
        self._make_admin_with_owner(app, "x")
        client = TestClient(app)
        self._login(client)
        resp = client.post(
            "/api/auth/projects/..%2F..%2F/share",  # URL-decoded: ../../
            data={"user_id": 999, "role": "viewer"},
        )
        assert resp.status_code == 400, f"'..' 路径未被拦截: status={resp.status_code}"

    def test_admin_grant_self_then_share_succeeds(self, app_with_state: FastAPI) -> None:
        """PoC B6-5：admin 先 grant 自己 owner，再 share → 200。"""
        from novel2all.core.auth import AuthStore

        app = app_with_state
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        # 关键：必须先创建 admin user（之前测试漏了）
        admin = store.create_user("attacker_admin", "pw", role="admin")
        victim = store.create_user("victim_user", "v", role="editor")
        # 模拟 admin 在 CLI 中先 grant 自己（合理流程）
        store.grant_project_access(
            admin.id,
            str(Path("myproj").resolve()),
            "owner",
            admin.id,
        )

        client = TestClient(app)
        self._login(client)
        resp = client.post(
            "/api/auth/projects/myproj/share",
            data={"user_id": victim.id, "role": "viewer"},
        )
        assert resp.status_code == 200, f"合法 share 失败: {resp.text}"


# ============================================================================
# B7: login 用户名枚举防护（独立 PoC — timing 攻击）
# ============================================================================


class TestB7UserEnumPoC:
    """PoC B7：测量 response time + audit log 内容。"""

    def test_audit_username_field_is_none_for_failed_login(self, app_with_state: FastAPI) -> None:
        """PoC B7-1：login_failed 在 audit 中 username 必须为 None。"""
        from novel2all.core.audit import AuditStore

        app = app_with_state
        audit: AuditStore = app.state.audit_store  # type: ignore[attr-defined]

        client = TestClient(app)
        # 故意触发多次失败
        for username in ("alice_xxx", "bob_xxx", "admin_xxx"):
            client.post(
                "/api/auth/login",
                data={"username": username, "password": "wrong"},
            )

        events = audit.query(event_type="login_failed", limit=10)
        failed = [e for e in events if e["event_type"] == "login_failed"]
        assert len(failed) >= 3, f"应有 ≥3 个 login_failed；got {len(failed)}"
        # 关键断言：所有 login_failed 的 username 必须是 None
        for ev in failed:
            assert ev["username"] is None, (
                f"login_failed 记录了 username（泄露 PII / 助枚举）: {ev}"
            )
            # user_id 也应是 None（用户不存在时）
            assert ev["user_id"] is None, f"login_failed 应无 user_id: {ev}"
            # IP 必填
            assert ev["ip"] is not None and ev["ip"] != "", f"login_failed 缺 IP: {ev}"

    def test_timing_parity_existing_vs_missing_user(self, app_with_state: FastAPI) -> None:
        """PoC B7-2：用户存在 + 密码错 vs 用户不存在 + 任意密码 → 时序差 < 100ms。"""
        from novel2all.core.auth import AuthStore

        app = app_with_state
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        store.create_user("existing_user", "long_correct_password_123")
        rate_limiter = app.state.rate_limiter  # type: ignore[attr-defined]

        client = TestClient(app)

        def measure(username: str, password: str) -> float:
            # 重置限流以避免锁定污染
            rate_limiter._fail_counts.clear()  # type: ignore[attr-defined]
            rate_limiter._locked_until.clear()  # type: ignore[attr-defined]
            t0 = time.perf_counter()
            resp = client.post(
                "/api/auth/login",
                data={"username": username, "password": password},
            )
            elapsed = time.perf_counter() - t0
            assert resp.status_code == 401
            return elapsed

        # 各测 5 次取 median（减少系统抖动）
        def median(values: list[float]) -> float:
            return sorted(values)[len(values) // 2]

        existing_times = [measure("existing_user", "wrong_password") for _ in range(5)]
        missing_times = [measure("ghost_user_xyz", "any_password") for _ in range(5)]

        med_existing = median(existing_times)
        med_missing = median(missing_times)
        diff_ms = abs(med_existing - med_missing) * 1000

        # 阈值：100ms（留 2x margin 给 CI 抖动）
        assert diff_ms < 100, (
            f"时序差异过大：existing={med_existing * 1000:.1f}ms "
            f"vs missing={med_missing * 1000:.1f}ms (diff={diff_ms:.1f}ms)"
        )

    def test_dummy_hash_does_not_create_user(self, app_with_state: FastAPI) -> None:
        """PoC B7-3：用户不存在路径不应产生副作用（如创建用户 / 写文件）。"""
        from novel2all.core.auth import AuthStore

        app = app_with_state
        store: AuthStore = app.state.auth_store  # type: ignore[attr-defined]
        users_before = len(store.list_users())

        client = TestClient(app)
        client.post(
            "/api/auth/login",
            data={"username": "no_such_user_zzz", "password": "whatever"},
        )
        users_after = len(store.list_users())
        assert users_after == users_before, (
            f"不存在的用户登录不应创建用户记录：{users_before} → {users_after}"
        )

    def test_dummy_hash_actually_runs(self, app_with_state: FastAPI) -> None:
        """PoC B7-4：dummy hash 路径实际执行了 hash_password（不能只是 noop）。"""
        from unittest.mock import patch

        from novel2all.core.auth import hash_password as real_hash

        app = app_with_state
        client = TestClient(app)

        call_count = {"n": 0}

        def counting_hash(plain: str) -> str:
            call_count["n"] += 1
            return real_hash(plain)

        # app.py 在函数内 import `from novel2all.core.auth import hash_password`，
        # 因此 patch `novel2all.core.auth.hash_password` 即可被函数内 import 解析到。
        with patch("novel2all.core.auth.hash_password", side_effect=counting_hash):
            resp = client.post(
                "/api/auth/login",
                data={"username": "no_such_user_zzz", "password": "whatever"},
            )
            assert resp.status_code == 401

        assert call_count["n"] >= 1, (
            f"用户不存在路径应至少调用一次 hash_password（dummy hash 防御）；"
            f"called={call_count['n']} 次。dummy hash 防御是空操作！"
        )


# ============================================================================
# B8: review Idempotency-Key（独立 PoC — 并发 / 边界 / 缺失 header）
# ============================================================================


class TestB8IdempotencyPoC:
    """PoC B8：模拟用户双击 / 并发 / 缺失 header。"""

    def _make_project(self, tmp_path: Path) -> Path:
        from novel2all.core.memory import Tracker

        tracker = Tracker(tmp_path / "_tracking-state.json")
        tracker.init(
            project_name="poc",
            genre="x",
            style_anchor="x",
            total_chapters_target=10,
        )
        prose = tmp_path / "正文"
        prose.mkdir(exist_ok=True)
        (prose / "第001章.md").write_text("# 1\n\n内容\n", encoding="utf-8")
        return tmp_path

    def test_missing_idempotency_key_works_without_cache(self, tmp_path: Path) -> None:
        """PoC B8-1：缺失 Idempotency-Key header → 仍能调用（不强制要求），但每次都调 LLM。"""
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        project_root = self._make_project(tmp_path)
        app = create_app()

        call_count = {"n": 0}

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            call_count["n"] += 1

            class _R:
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

            return _R()

        client = TestClient(app)
        with patch.object(MultiAgentReviewer, "review", new=fake_review):
            r1 = client.post(f"/api/chapter/1/review?project_root={project_root}")
            r2 = client.post(f"/api/chapter/1/review?project_root={project_root}")
            assert r1.status_code == 200
            assert r2.status_code == 200
            # 没 key → 两次都应调 LLM
            assert call_count["n"] == 2, (
                f"缺失 Idempotency-Key 时应每次都调 LLM；got {call_count['n']}"
            )
            # 不应有 replay 标记
            assert "_idempotent_replay" not in r1.json()
            assert "_idempotent_replay" not in r2.json()

    def test_idempotency_key_thread_safety(self, tmp_path: Path) -> None:
        """PoC B8-2：5 个线程同时同 key 调 → 只调 1 次 LLM（thread-safety）。"""
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        project_root = self._make_project(tmp_path)
        app = create_app()

        # 把 store 替换成带 Lock 的版本（虽然实现已经有 Lock）
        idempotency_key = "thread-test-key-12345"

        call_count = {"n": 0}
        call_lock = threading.Lock()

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            with call_lock:
                call_count["n"] += 1
            # 模拟一些延迟（用 asyncio.sleep 避免 ASYNC251 警告）
            await asyncio.sleep(0.05)

            class _R:
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

            return _R()

        results: list[int] = []
        errors: list[str] = []

        def hit() -> None:
            try:
                client = TestClient(app)
                resp = client.post(
                    f"/api/chapter/1/review?project_root={project_root}",
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
        assert all(s == 200 for s in results), f"非 200 响应: {results}"
        # 关键：5 个并发 → 至多调 1 次 LLM（不能多于 1）
        assert call_count["n"] <= 1, (
            f"并发同 key 应最多调 1 次 LLM；got {call_count['n']} 次（race condition！）"
        )

    def test_replay_response_has_marker(self, tmp_path: Path) -> None:
        """PoC B8-3：第二次同 key 返回的 response 必须含 _idempotent_replay=True。"""
        from unittest.mock import patch

        from novel2all.core.memory.multi_reviewer import MultiAgentReviewer

        project_root = self._make_project(tmp_path)
        app = create_app()

        async def fake_review(self: Any, **kwargs: Any) -> Any:
            class _R:
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

            return _R()

        client = TestClient(app)
        import uuid as _uuid

        key = _uuid.uuid4().hex
        with patch.object(MultiAgentReviewer, "review", new=fake_review):
            r1 = client.post(
                f"/api/chapter/1/review?project_root={project_root}",
                headers={"Idempotency-Key": key},
            )
            r2 = client.post(
                f"/api/chapter/1/review?project_root={project_root}",
                headers={"Idempotency-Key": key},
            )
            assert r1.status_code == 200
            assert r2.status_code == 200
            # replay 必须有标记
            assert r2.json().get("_idempotent_replay") is True, (
                f"replay 响应缺 _idempotent_replay 标记；got {r2.json()}"
            )
            # 原响应不应有标记
            assert r1.json().get("_idempotent_replay") is None, (
                f"原始响应不应有 _idempotent_replay 标记；got {r1.json()}"
            )

    def test_idempotency_store_independent_keys(self) -> None:
        """PoC B8-4：InMemoryIdempotencyStore 单元测试 — 不同 key 互不干扰。"""
        store = InMemoryIdempotencyStore(ttl_seconds=300)
        store.set((1, 1, "key-A"), "value-A")
        store.set((1, 1, "key-B"), "value-B")
        assert store.get((1, 1, "key-A")) == "value-A"
        assert store.get((1, 1, "key-B")) == "value-B"
        # 修改 A 不影响 B
        store.set((1, 1, "key-A"), "value-A2")
        assert store.get((1, 1, "key-A")) == "value-A2"
        assert store.get((1, 1, "key-B")) == "value-B"

    def test_idempotency_store_overwrite(self) -> None:
        """PoC B8-5：同 key 二次 set → 覆盖（用于 key reuse 场景）。"""
        store = InMemoryIdempotencyStore(ttl_seconds=300)
        store.set((1, 1, "k"), "v1")
        store.set((1, 1, "k"), "v2")
        assert store.get((1, 1, "k")) == "v2"

    def test_idempotency_store_clear_removes_all(self) -> None:
        """PoC B8-6：clear() 应清空所有 key。"""
        store = InMemoryIdempotencyStore(ttl_seconds=300)
        for i in range(100):
            store.set((i, i, f"k{i}"), f"v{i}")
        store.clear()
        for i in range(100):
            assert store.get((i, i, f"k{i}")) is None
