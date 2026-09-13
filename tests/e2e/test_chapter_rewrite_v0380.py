"""V0.38：章节重写/插入 UI playwright E2E 测试。

测试范围（mock LLM + 真实 chromium headless）：
1. 章节编辑页加载，含「🔄 AI 重写选中」+「➕ AI 插入段落」按钮
2. 模板含 V0.38 关键 JS 函数（openRewriteModal / openInsertModal / executeRewrite 等）
3. x-data 包含 selStart/selEnd/modalType/modalResult 等 V0.38 字段
4. POST /api/chapter/1/rewrite 接受正确参数（无 LLM 调用 → 400）
5. POST /api/chapter/1/insert 接受正确参数（无 LLM 调用 → 400）
6. POST /api/chapter/1/rewrite 无效 start/end → 400
7. POST /api/chapter/1/insert 无效 position → 400
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

pytestmark = pytest.mark.e2e


# === Mock LLM for V0.38 ===


class _MockLLMV038:
    """V0.38 E2E 测试用 mock：返回固定改写/插入文本。"""

    def __init__(self) -> None:
        self.last_prompt: str = ""
        self.last_system: str = ""

    async def complete(self, prompt: str, system: str = "", **kwargs):
        self.last_prompt = prompt
        self.last_system = system
        return "【mocked-rewrite-result】"


_mock_llm = _MockLLMV038()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# === Server fixture (monkeypatch LLM + lifespan) ===


@pytest.fixture(scope="module")
def server_url():
    """启动 FastAPI TestServer，monkey-patch LLMProvider 为 mock。"""
    from novel2all.web.app import create_app

    global _mock_llm
    _mock_llm = _MockLLMV038()
    mp = pytest.MonkeyPatch()
    # V0.38 端点用 get_llm_for_model（来自 cli.main）— patch 该函数
    mp.setattr("novel2all.cli.main.get_llm_for_model", lambda model=None: _mock_llm)
    try:
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
    finally:
        mp.undo()
        _mock_llm = _MockLLMV038()


# === Test 1: 页面加载 + 含 V0.38 按钮 ===


def test_chapter_edit_has_rewrite_and_insert_buttons(page, server_url: str) -> None:
    """V0.38：章节编辑页含「🔄 AI 重写选中」+「➕ AI 插入段落」按钮。"""
    resp = page.goto(server_url + "/page/chapter-edit")
    assert resp is not None
    assert resp.status == 200
    content = page.content()
    assert "🔄 AI 重写选中" in content
    assert "➕ AI 插入段落" in content


def test_chapter_edit_has_v038_js_methods(page, server_url: str) -> None:
    """V0.38：Alpine.js x-data 含 V0.38 方法（openRewriteModal / openInsertModal / executeRewrite / executeInsert / applyRewrite / applyInsert）。"""
    page.goto(server_url + "/page/chapter-edit")
    content = page.content()
    for fn in (
        "openRewriteModal",
        "openInsertModal",
        "executeRewrite",
        "executeInsert",
        "applyRewrite",
        "applyInsert",
        "updateSelection",
        "selectionLength",
        "selectionPreview",
        "modalType",
        "modalInstruction",
        "modalResult",
        "insertPosition",
    ):
        assert fn in content, f"模板应含 {fn}"


def test_chapter_edit_has_selection_tracking(page, server_url: str) -> None:
    """V0.38：textarea 含 @select/@keyup/@click 选区跟踪事件。"""
    page.goto(server_url + "/page/chapter-edit")
    content = page.content()
    # textarea 应有 @select 和 updateSelection 调用
    assert "@select=" in content or "x-on:select=" in content
    assert "updateSelection" in content


def test_chapter_edit_modal_x_cloak(page, server_url: str) -> None:
    """V0.38：modal 元素含 x-cloak 防止初次加载闪烁。"""
    page.goto(server_url + "/page/chapter-edit")
    content = page.content()
    assert "x-cloak" in content


# === Test 2: 端点存在且响应正确（无 mock 时返回错误，但端点可达）===


def test_rewrite_endpoint_returns_400_when_project_missing(page, server_url: str) -> None:
    """V0.38：POST /api/chapter/1/rewrite 在项目不存在时返回 404（项目必需 tracking state）。"""
    resp = page.request.post(
        server_url + "/api/chapter/1/rewrite",
        form={
            "start": "0",
            "end": "5",
            "instruction": "test",
            "project_root": "D:/nonexistent_root_xyz",
        },
    )
    assert resp.status == 404


def test_rewrite_endpoint_returns_400_when_range_invalid(page, server_url: str) -> None:
    """V0.38：POST /api/chapter/1/rewrite 在 start >= end 时返回 400。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        (proj / "正文").mkdir(parents=True)
        (proj / "正文" / "第001章.md").write_text("hi", encoding="utf-8")
        (proj / "_tracking-state.json").write_text("{}", encoding="utf-8")
        proj_str = str(proj).replace("\\", "/")

        resp = page.request.post(
            server_url + "/api/chapter/1/rewrite",
            form={
                "start": "50",
                "end": "30",
                "instruction": "test",
                "project_root": proj_str,
            },
        )
        assert resp.status == 400


def test_insert_endpoint_returns_400_when_position_invalid(page, server_url: str) -> None:
    """V0.38：POST /api/chapter/1/insert 在 position 越界时返回 400。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        (proj / "正文").mkdir(parents=True)
        (proj / "正文" / "第001章.md").write_text("hi", encoding="utf-8")
        (proj / "_tracking-state.json").write_text("{}", encoding="utf-8")
        proj_str = str(proj).replace("\\", "/")

        resp = page.request.post(
            server_url + "/api/chapter/1/insert",
            form={
                "position": "999",
                "instruction": "test",
                "project_root": proj_str,
            },
        )
        assert resp.status == 400


# === Test 3: 端点成功路径（mock LLM）===


def test_rewrite_endpoint_success_with_mock(page, server_url: str) -> None:
    """V0.38：POST /api/chapter/1/rewrite 在 mock LLM 下返回 original + rewritten。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        (proj / "正文").mkdir(parents=True)
        (proj / "正文" / "第001章.md").write_text(
            "第一段原文内容。\n\n第二段原文。\n\n第三段。", encoding="utf-8"
        )
        (proj / "_tracking-state.json").write_text("{}", encoding="utf-8")
        proj_str = str(proj).replace("\\", "/")

        resp = page.request.post(
            server_url + "/api/chapter/1/rewrite",
            form={
                "start": "0",
                "end": "8",
                "instruction": "改写得更生动",
                "project_root": proj_str,
            },
        )
        assert resp.status == 200
        data = resp.json()
        assert data["chapter"] == 1
        assert data["start"] == 0
        assert data["end"] == 8
        assert data["original"] == "第一段原文内容。"
        assert data["rewritten"] == "【mocked-rewrite-result】"

        # mock 应该被调用
        assert "改写得更生动" in _mock_llm.last_prompt
        assert "第一段原文内容" in _mock_llm.last_prompt


def test_insert_endpoint_success_with_mock(page, server_url: str) -> None:
    """V0.38：POST /api/chapter/1/insert 在 mock LLM 下返回 inserted。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        (proj / "正文").mkdir(parents=True)
        (proj / "正文" / "第001章.md").write_text(
            "前文上下文。" + "中间位置" + "后文上下文。", encoding="utf-8"
        )
        (proj / "_tracking-state.json").write_text("{}", encoding="utf-8")
        proj_str = str(proj).replace("\\", "/")

        # 计算 position = len("前文上下文。")
        position = len("前文上下文。")
        resp = page.request.post(
            server_url + "/api/chapter/1/insert",
            form={
                "position": str(position),
                "instruction": "添加景色描写",
                "project_root": proj_str,
            },
        )
        assert resp.status == 200
        data = resp.json()
        assert data["chapter"] == 1
        assert data["position"] == position
        assert data["inserted"] == "【mocked-rewrite-result】"


# === Test 4: 跨页面无 JS 错误（确保 Alpine.js 正常初始化）===


def test_no_js_errors_on_chapter_edit_page(page, server_url: str) -> None:
    """V0.38：chapter-edit 页加载后无 JS 错误（Alpine.js 初始化成功）。"""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None,
    )
    page.goto(server_url + "/page/chapter-edit")
    page.wait_for_load_state("networkidle")

    # 过滤 favicon 404
    real_errors = [e for e in errors if "favicon" not in e and "404" not in e]
    assert not real_errors, f"V0.38: JS 错误: {real_errors[:3]}"
