"""V0.30.5 WebUI E2E 测试（playwright + 真实 FastAPI + 无 mock）。

测试范围（真实 chromium headless 浏览器 + 真实 uvicorn + 真实 LLMProvider）：
1. 6 个 /page/* 端点 GET 200 + 含正确 HTML 元素
2. 3 个静态资源（htmx.min.js / htmx-sse.js / alpine.min.js）200 + 大小正确
3. 6 个 /api/* GET JSON 端点返回正确结构（status / skills / roles / models / model/current / cache/stats）
4. /page/write-form 含 Alpine.js x-data 状态机
5. /page/cache-panel 显示 cache stats（命中/未命中/命中率）
6. /page/model-selector 显示 form + 当前 model
7. 跨页面无 JS 错误（捕获 console.error + pageerror）

设计：
- 不 mock LLMProvider：LLMProvider(LLMConfig()) 无 API key 也能实例化（cache_stats() 不调 LLM）
- 跳过需要真实 LLM 调用的端点（如 /api/write/stream/model 的实际流）
- threading + uvicorn.Server 启 TestServer（127.0.0.1 随机端口）
- pytest-playwright chromium 默认 headless
- 不依赖 MINIMAX_API_KEY / DEEPSEEK_API_KEY / ANTHROPIC_API_KEY

CI 集成：
- 标记 @pytest.mark.e2e（CI 跑 pytest 默认 -m "not e2e" 跳过；e2e job 单独跑 -m e2e）
- 需要先 `playwright install chromium`（本地开发用，CI 由 e2e job 处理）
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn

# V0.30.5: 标记为 e2e（CI 默认跳过；专属 e2e job 单独跑）
pytestmark = pytest.mark.e2e


# === Server Fixture（module 级共享，启动一次）===


def _find_free_port() -> int:
    """找一个可用的本地端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url() -> str:
    """启动 FastAPI TestServer，返回 base URL。

    通过环境变量启用 cache（V0.30.2 cache-panel 需要 stats.hits/misses 显示）。
    lifespan 加载 .env 时会被 .env 里的 NOVEL2ALL_LLM_CACHE 覆盖，因此必须在
    create_app 之前设置环境变量（lifespan 用 override=False）。
    """
    import os

    # 确保 cache 启用（覆盖 .env 里的设置，因为 load_dotenv 用 override=False）
    os.environ["NOVEL2ALL_LLM_CACHE"] = "true"

    from novel2all.web.app import create_app

    app = create_app()
    port = _find_free_port()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()

    # 等 server 起来（最长 5s）
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


# === Test 1: 首页 + 静态资源加载 ===


def test_index_page_loads_with_assets(page, server_url: str) -> None:
    """首页 GET / 应返回 200 + 加载 htmx + alpine + htmx-sse。

    验证 base.html 模板正确引用 3 个静态资源。
    """
    resp = page.goto(server_url + "/")
    assert resp is not None
    assert resp.status == 200
    # base.html 必加载 htmx + alpine + htmx-sse（script[src]）
    assert page.locator("script[src$='/static/htmx.min.js']").count() >= 1
    assert page.locator("script[src$='/static/alpine.min.js']").count() >= 1
    assert page.locator("script[src$='/static/htmx-sse.js']").count() >= 1


@pytest.mark.parametrize(
    "asset,min_size_kb",
    [
        ("htmx.min.js", 30),  # ~50KB
        ("htmx-sse.js", 5),  # ~8.9KB
        ("alpine.min.js", 30),  # ~44KB
    ],
)
def test_static_asset_loads(page, server_url: str, asset: str, min_size_kb: int) -> None:
    """3 个静态资源 200 + 大于预期大小（KB）。"""
    resp = page.goto(server_url + f"/static/{asset}")
    assert resp is not None
    assert resp.status == 200
    body = resp.body() if hasattr(resp, "body") else b""
    assert len(body) > min_size_kb * 1024, (
        f"{asset}: too small ({len(body)} bytes, expected >{min_size_kb}KB)"
    )


# === Test 2: 6 个 /page/* 端点全部 200 ===


@pytest.mark.parametrize(
    "path",
    [
        "/page/status",
        "/page/skills",
        "/page/roles",
        "/page/model-selector",
        "/page/write-form",
        "/page/cache-panel",
    ],
)
def test_page_endpoint_returns_200(page, server_url: str, path: str) -> None:
    """6 个 /page/* 端点全部 GET 200。"""
    resp = page.goto(server_url + path)
    assert resp is not None, f"{path}: navigation returned None"
    assert resp.status == 200, f"{path}: status={resp.status}"


# === Test 3: 6 个 /api/* JSON 端点结构正确 ===


def test_api_cache_stats_structure(page, server_url: str) -> None:
    """/api/cache/stats 返回 JSON 含 hits/misses/hit_rate/size/max_size/enabled。"""
    resp = page.goto(server_url + "/api/cache/stats")
    assert resp is not None
    assert resp.status == 200
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    data = json.loads(raw)
    # V0.29.3 LRU cache stats 字段全在
    for key in ("hits", "misses", "hit_rate", "size", "max_size", "enabled"):
        assert key in data, f"missing key: {key}"


def test_api_models_list_nonempty(page, server_url: str) -> None:
    """/api/models 返回 JSON 列表（至少 1 个 ModelConfig）。"""
    resp = page.goto(server_url + "/api/models")
    assert resp is not None
    assert resp.status == 200
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    data = json.loads(raw)
    assert isinstance(data, list)
    assert len(data) >= 1
    # 每条应含 name / anthropic_compat / api_base / api_key_env
    first = data[0]
    for key in ("name", "anthropic_compat"):
        assert key in first, f"missing key in model entry: {key}"


def test_api_model_current_returns_default(page, server_url: str) -> None:
    """/api/model/current 返回当前 default_model。"""
    resp = page.goto(server_url + "/api/model/current")
    assert resp is not None
    assert resp.status == 200
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    data = json.loads(raw)
    assert "model" in data
    assert isinstance(data["model"], str)
    assert len(data["model"]) > 0


@pytest.mark.parametrize(
    "path",
    ["/api/status", "/api/skills", "/api/roles"],
)
def test_api_basic_endpoints_return_json(page, server_url: str, path: str) -> None:
    """/api/status, /api/skills, /api/roles 返回 JSON（dict 或 list）。"""
    resp = page.goto(server_url + path)
    assert resp is not None
    assert resp.status == 200
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    data = json.loads(raw)
    assert data is not None


# === Test 4: Alpine.js 状态机 + 模板渲染验证 ===


def test_write_form_has_alpine_state_machine(page, server_url: str) -> None:
    """/page/write-form 含 Alpine.js x-data 容器（4 态状态机 idle/running/done/error）。"""
    page.goto(server_url + "/page/write-form")
    page.wait_for_load_state("networkidle")
    # V0.30.3 流式编辑器用 Alpine.js 状态机，必含 x-data
    alpine_divs = page.locator("[x-data]").count()
    assert alpine_divs >= 1, "write-form 应至少含 1 个 Alpine.js x-data 容器"


def test_cache_panel_displays_stats(page, server_url: str) -> None:
    """/page/cache-panel 显示 cache stats（命中/未命中/命中率）。

    cache 启用时（NOVEL2ALL_LLM_CACHE=true），Jinja2 模板渲染命中/未命中统计。
    """
    page.goto(server_url + "/page/cache-panel")
    page.wait_for_load_state("networkidle")
    content = page.content()
    # Jinja2 模板：cache 启用时显示 命中: N / 未命中: N / 总计: N
    assert "命中" in content
    assert "未命中" in content
    assert "命中率" in content


def test_model_selector_shows_form(page, server_url: str) -> None:
    """/page/model-selector 显示 form + 当前 model 标识。"""
    page.goto(server_url + "/page/model-selector")
    page.wait_for_load_state("networkidle")
    forms = page.locator("form").count()
    assert forms >= 1, "model-selector 应至少含 1 个 form（model 切换表单）"
    # 应显示当前 model 标识
    content = page.content()
    assert "model" in content.lower()


# === Test 5: 跨页面无 JS 错误（捕获 console + pageerror）===


def test_no_js_errors_on_any_page(page, server_url: str) -> None:
    """访问每个页面，捕获 console.error + pageerror，断言无错误。"""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

    def on_console(msg) -> None:
        if msg.type == "error":
            errors.append(f"console.error: {msg.text}")

    page.on("console", on_console)

    paths = [
        "/",
        "/page/status",
        "/page/skills",
        "/page/roles",
        "/page/model-selector",
        "/page/write-form",
        "/page/cache-panel",
    ]
    for path in paths:
        page.goto(server_url + path)
        page.wait_for_load_state("networkidle")

    # 过滤 favicon 等非页面 bug 的报错
    real_errors = [e for e in errors if "favicon" not in e.lower()]
    assert real_errors == [], f"页面 JS 错误: {real_errors}"


# === Test 6: POST /api/model/switch 切换端点（不实际调 LLM）===


def test_api_model_switch_rejects_unknown_model(page, server_url: str) -> None:
    """POST /api/model/switch 传未知 model 应返回 400 + 错误信息。

    验证 V0.30.1 切换端点的错误处理（不真正切换 model）。
    """
    resp = page.request.post(
        server_url + "/api/model/switch",
        form={"model": "unknown/totally-fake-model"},
    )
    # 400 Bad Request（未知 model）
    assert resp.status == 400
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    data = json.loads(raw)
    # FastAPI HTTPException 返回 {"detail": ...}
    assert "detail" in data
    assert "未知模型" in data["detail"] or "unknown" in data["detail"].lower()


# === Test 7: 17 业务端点可达性 smoke test ===


def test_all_business_endpoints_reachable(page, server_url: str) -> None:
    """所有 17 业务端点（不含 SSE 流式）返回非 5xx。"""
    endpoints = [
        # 6 page GET
        ("GET", "/page/status"),
        ("GET", "/page/skills"),
        ("GET", "/page/roles"),
        ("GET", "/page/model-selector"),
        ("GET", "/page/write-form"),
        ("GET", "/page/cache-panel"),
        # 7 api GET
        ("GET", "/api/status"),
        ("GET", "/api/skills"),
        ("GET", "/api/roles"),
        ("GET", "/api/cache/stats"),
        ("GET", "/api/models"),
        ("GET", "/api/model/current"),
        # 1 api POST（错误路径）
        ("POST", "/api/model/switch"),
        # 静态资源
        ("GET", "/static/htmx.min.js"),
        ("GET", "/static/htmx-sse.js"),
        ("GET", "/static/alpine.min.js"),
    ]
    for method, path in endpoints:
        if method == "GET":
            resp = page.request.get(server_url + path)
        else:
            resp = page.request.post(server_url + path, form={"model": "unknown"})
        # 不应是 5xx（404 / 400 是合理的）
        assert resp.status < 500, f"{method} {path}: 5xx error ({resp.status})"
