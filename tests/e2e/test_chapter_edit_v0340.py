"""V0.34 章节编辑器 E2E 测试（playwright）。

测试范围（真实 chromium + 真实 uvicorn）：
1. /page/chapter-edit 渲染 Alpine.js 状态机
2. 编辑器 textarea 存在
3. 「加载章节」「保存修改」「撤销修改」「AI 扩写」4 个按钮
4. /api/chapter/1/save POST 端点可访问
5. /api/chapter/1/expand POST 端点可访问
6. 模板含 x-data 7 态状态机
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

# V0.34：标记为 e2e（CI 默认跳过；专属 e2e job 跑）
pytestmark = pytest.mark.e2e


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url() -> str:
    """启动 FastAPI TestServer，返回 base URL。"""
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


# === Tests ===


def test_chapter_edit_page_loads(page, server_url: str) -> None:
    """V0.34：/page/chapter-edit 渲染 HTML 200。"""
    resp = page.goto(server_url + "/page/chapter-edit")
    assert resp is not None
    assert resp.status == 200
    # 模板含关键内容
    content = page.content()
    assert "章节编辑器" in content
    assert "textarea" in content.lower()
    assert "x-data" in content


def test_chapter_edit_has_all_four_buttons(page, server_url: str) -> None:
    """V0.34：编辑器含 4 个按钮：加载章节 / 保存修改 / 撤销修改 / AI 扩写。"""
    page.goto(server_url + "/page/chapter-edit")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "加载章节" in content
    assert "保存修改" in content
    assert "撤销修改" in content
    assert "AI 扩写" in content


def test_chapter_edit_has_textarea(page, server_url: str) -> None:
    """V0.34：编辑器含 textarea（手动编辑区域）。"""
    page.goto(server_url + "/page/chapter-edit")
    page.wait_for_load_state("networkidle")
    # 查找 textarea
    textareas = page.locator("textarea")
    count = textareas.count()
    assert count >= 1, "V0.34 编辑器应至少 1 个 textarea"


def test_chapter_edit_has_alpine_state_machine_v034(page, server_url: str) -> None:
    """V0.34：Alpine.js 状态机 7 态（idle/loading/loaded/saving/saved/expanding/error）。"""
    page.goto(server_url + "/page/chapter-edit")
    page.wait_for_load_state("networkidle")
    content = page.content()
    # 7 态
    for state in ["idle", "loading", "loaded", "saving", "saved", "expanding", "error"]:
        assert state in content, f"应含状态: {state}"


def test_chapter_edit_save_endpoint_exists(page, server_url: str) -> None:
    """V0.34：POST /api/chapter/1/save 端点可访问（无项目时返回 404）。"""
    resp = page.request.post(
        server_url + "/api/chapter/1/save",
        form={"content": "test", "project_root": "D:/nonexistent"},
    )
    # 项目不存在时返回 404（合理）
    assert resp.status == 404


def test_chapter_edit_expand_endpoint_exists(page, server_url: str) -> None:
    """V0.34：POST /api/chapter/1/expand 端点可访问。"""
    resp = page.request.post(
        server_url + "/api/chapter/1/expand",
        form={"project_root": "D:/nonexistent"},
    )
    # 项目不存在时返回 404（合理）
    assert resp.status == 404


def test_chapter_edit_template_in_index_page(page, server_url: str) -> None:
    """V0.34：index.html 含 chapter-edit div 引用（HTMX hx-get 触发 /page/chapter-edit 加载）。"""
    # Use page.request to get raw HTML（HTMX 替换前的内容）
    response = page.request.get(server_url + "/")
    assert response.status == 200
    body = response.text()
    # 应含 HTMX hx-get 引用 /page/chapter-edit
    assert "/page/chapter-edit" in body
    assert 'id="chapter-edit"' in body
    assert 'hx-get="/page/chapter-edit"' in body
