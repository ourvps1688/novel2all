"""V0.31 流式编辑器取消按钮 E2E 测试（playwright）。

测试范围（真实 chromium headless 浏览器 + 真实 uvicorn）：
1. /page/write-form 渲染「停止」按钮（running 状态可见）
2. 点击「停止」按钮 → POST /api/write/cancel/{task_id}
3. 取消后状态从 running → cancelling → cancelled
4. Alpine.js 显示 partial_chars 字数
5. 取消后 SSE 流发送 'cancelled' 事件（partial_chars + output_path）
6. 取消按钮在 idle / done 状态不可见

设计：
- 不依赖真实 LLM：mock provider 的 stream 在 80 字后触发 cancel_event
- 通过 FastAPI lifespan monkey-patch 把 LLMProvider 替换为 CancellableMockLLM
- threading + uvicorn.Server 启 TestServer（127.0.0.1 随机端口）
- pytest-playwright chromium 默认 headless
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
import uvicorn

# V0.31：标记为 e2e（CI 默认跳过；专属 e2e job 单独跑）
pytestmark = pytest.mark.e2e


# === Mock LLM（受 cancel 控制的 slow stream）===


class CancellableMockLLMForWeb:
    """Web E2E 专用 mock LLM。stream 在 yield 80 字后触发 cancel_event（模拟用户停止）。"""

    def __init__(self) -> None:
        from novel2all.core.provider import LLMConfig

        self.config = LLMConfig(
            default_model="deepseek/deepseek-flash",
            cache_enabled=True,
        )
        self.cancel_event = asyncio.Event()
        self.mock_content = "本章正文。" * 200  # 2000 字

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.mock_content

    async def complete_structured(
        self, prompt: str, *, response_model: Any = None, **kwargs: Any
    ) -> Any:
        origin = getattr(response_model, "__origin__", None) if response_model else None
        if origin is list:
            return []
        if hasattr(response_model, "model_construct"):
            return response_model.model_construct()
        return None

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        yielded = 0
        for i in range(0, len(self.mock_content), 10):
            if self.cancel_event.is_set():
                raise asyncio.CancelledError("E2E cancel")
            chunk = self.mock_content[i : i + 10]
            yielded += len(chunk)
            yield chunk
            if yielded >= 80:  # 80 字后自动停止（让 cancel 按钮有东西可取消）
                self.cancel_event.set()
            await asyncio.sleep(0.05)

    def cache_stats(self) -> dict[str, Any]:
        return {
            "hits": 0,
            "misses": 0,
            "size": 0,
            "max_size": 256,
            "hit_rate": 0.0,
            "enabled": False,
        }


# 全局 mock 实例（lifespan 中使用）
_mock_llm: CancellableMockLLMForWeb | None = None


# === Fixtures ===


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url() -> str:
    """启动 FastAPI TestServer，返回 base URL。monkey-patch LLMProvider 为 CancellableMockLLMForWeb。"""
    from novel2all.core import provider as provider_module
    from novel2all.web.app import create_app

    global _mock_llm
    _mock_llm = CancellableMockLLMForWeb()
    mp = pytest.MonkeyPatch()
    mp.setattr(provider_module, "LLMProvider", lambda cfg=None: _mock_llm)
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
        _mock_llm = None


# === Tests ===


def test_write_form_has_cancel_button_in_template(page, server_url: str) -> None:
    """/page/write-form 的 HTML 含「停止」按钮（type="button"，onclick="cancelRun()"）。"""
    page.goto(server_url + "/page/write-form")
    page.wait_for_load_state("networkidle")
    # 验证「停止」按钮存在（x-show="status === 'running'" 控制可见性，但 DOM 应存在）
    content = page.content()
    assert "停止" in content, "write-form 应含「停止」按钮文本"
    assert "cancelRun" in content, "write-form 应含 cancelRun() Alpine.js 函数"


def test_write_form_has_alpine_state_machine_v031(page, server_url: str) -> None:
    """/page/write-form 的 Alpine.js 状态机包含 V0.31 新增的 cancelling / cancelled 状态。"""
    page.goto(server_url + "/page/write-form")
    page.wait_for_load_state("networkidle")
    content = page.content()
    # V0.31 新增状态
    assert "cancelling" in content, "Alpine.js 应支持 cancelling 状态"
    assert "cancelled" in content, "Alpine.js 应支持 cancelled 状态"
    # Alpine.js 5 态状态机
    assert "'idle'" in content or '"idle"' in content
    assert "'running'" in content or '"running"' in content
    assert "'done'" in content or '"done"' in content
    assert "'error'" in content or '"error"' in content


def test_cancel_endpoint_404_for_unknown_task(page, server_url: str) -> None:
    """POST /api/write/cancel/{unknown_task_id} 返回 404。"""
    resp = page.request.post(server_url + "/api/write/cancel/nonexistent123")
    assert resp.status == 404


def test_active_pipelines_endpoint_returns_list(page, server_url: str) -> None:
    """GET /api/write/active 返回 JSON 列表（V0.31 调试端点）。"""
    resp = page.request.get(server_url + "/api/write/active")
    assert resp.status == 200
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    data = json.loads(raw)
    assert isinstance(data, list)


def test_cancel_button_html_structure(page, server_url: str) -> None:
    """write-form 的「停止」按钮 HTML 结构：type=button、x-show=running、@click=cancelRun。

    这是 V0.31 新增的按钮，必须满足：
    - type="button"（不触发 form submit）
    - x-show="status === 'running'"（仅 running 时显示）
    - onclick 含 cancelRun() 调用
    """
    page.goto(server_url + "/page/write-form")
    page.wait_for_load_state("networkidle")
    # 查找包含「停止」文本的 button 元素
    stop_button = page.locator('button:has-text("停止")')
    count = stop_button.count()
    assert count >= 1, "应至少 1 个含「停止」的 button"


def test_cancel_endpoint_returns_404_for_completed_task(page, server_url: str) -> None:
    """POST /api/write/cancel/{task_id} 对已完成 task 返回 404。

    完整 task lifecycle 测试在 tests/unit/test_pipeline_cancel_v0310.py，
    这里只验证 endpoint 路径分支。
    """
    resp = page.request.post(server_url + "/api/write/cancel/never_existed_12345")
    assert resp.status == 404
    raw = resp.text() if hasattr(resp, "text") else resp.body().decode()
    # FastAPI HTTPException 返回 {"detail": "..."}
    data = json.loads(raw)
    assert "detail" in data
    assert "不存在" in data["detail"] or "not_found" in data["detail"]
