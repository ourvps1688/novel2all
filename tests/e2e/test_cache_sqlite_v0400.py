"""V0.40：SQLite cache backend UI playwright E2E 测试。

测试范围（mock-free, 仅验证端点 + 模板）：
1. /api/cache/stats 端点可达
2. cache_panel 模板含 backend 字段展示
3. stats JSON 含 backend/lock_backend 字段
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

pytestmark = pytest.mark.e2e


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url() -> str:
    """启动 FastAPI TestServer，启用 cache（让 backend 字段可见）。"""
    import os

    # V0.40：启用 cache + 内存 backend（测试端点 + 模板）
    os.environ["NOVEL2ALL_LLM_CACHE"] = "true"
    from novel2all.web.app import create_app

    app = create_app()
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Server failed to start on port {port}")
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)
    # 清理 env
    os.environ.pop("NOVEL2ALL_LLM_CACHE", None)


# === Test 1: 端点可达 + JSON 结构 ===


def test_cache_stats_endpoint_returns_backend_field(page, server_url: str) -> None:
    """V0.40：/api/cache/stats 应含 backend 字段。"""
    resp = page.request.get(server_url + "/api/cache/stats")
    assert resp.status == 200
    data = resp.json()
    assert "backend" in data, "V0.40: stats 应含 backend 字段"
    assert data["backend"] in ("memory", "json", "sqlite"), (
        f"backend 应是 memory/json/sqlite，实际={data['backend']}"
    )
    assert "lock_backend" in data, "V0.40: stats 应含 lock_backend 字段"


def test_cache_stats_endpoint_includes_lock_backend(page, server_url: str) -> None:
    """V0.40：/api/cache/stats 含 lock_backend（memory="none" / json=fcntl/msvcrt/none / sqlite="sqlite"）。"""
    resp = page.request.get(server_url + "/api/cache/stats")
    data = resp.json()
    assert data["lock_backend"] in ("none", "fcntl", "msvcrt", "sqlite")


# === Test 2: cache_panel 模板含 backend 展示 ===


def test_cache_panel_template_shows_backend(page, server_url: str) -> None:
    """V0.40：/page/cache-panel 应展示 backend 名称（memory/json/sqlite）。"""
    resp = page.goto(server_url + "/page/cache-panel")
    assert resp is not None
    assert resp.status == 200
    content = page.content()
    # 模板应渲染 backend 名称（默认 memory，因为 fixture 没设 sqlite）
    assert "memory" in content, "模板应展示 backend 名称（默认 memory）"
    # 也应展示"后端"标签
    assert "后端" in content, "V0.40: 模板应有「后端」标签"


# === Test 3: 跨页面无 JS 错误 ===


def test_no_js_errors_on_cache_panel(page, server_url: str) -> None:
    """V0.40：cache-panel 页加载后无 JS 错误。"""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None,
    )
    page.goto(server_url + "/page/cache-panel")
    page.wait_for_load_state("networkidle")
    real_errors = [e for e in errors if "favicon" not in e and "404" not in e]
    assert not real_errors, f"V0.40: JS 错误: {real_errors[:3]}"
