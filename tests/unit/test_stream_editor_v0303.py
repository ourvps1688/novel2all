"""V0.30.3：流式编辑器升级测试。

V0.30.3 让 WebUI 流式章节写作变成"现代 IDE 体验"：
- HTMX SSE extension 真实接入（不是 hx-on 累加 textarea）
- Alpine.js 状态机：idle / running / done / error
- 实时字数统计
- 错误处理：失败时显示错误信息
- 断线重连：HTMX SSE 1.x 原生支持

实施细节：
- 新增 htmx-sse.js 静态文件（HTMX SSE extension 2.2.2，本地化 8.9KB）
- base.html 加载 htmx-sse.js
- write_form.html 重写：Alpine.js x-data + 状态机 + 字数统计
- hx-on::sse-message 调 Alpine appendChunk() 方法

测试覆盖：
- htmx-sse.js 静态文件存在且可访问
- base.html 引用 htmx-sse.js
- write_form.html 含：
  - HTMX SSE 配置（hx-ext="sse" + sse-swap="message"）
  - Alpine.js 状态机（x-data 含 status/content/charCount）
  - 字数统计显示（x-text="charCount"）
  - 错误状态显示
  - 按钮 disabled 状态（status='running'）
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel2all.web.app import create_app


class TestSSEExtensionV0303:
    """V0.30.3：HTMX SSE extension 本地化。"""

    def test_htmx_sse_static_file_exists(self) -> None:
        """web/static/htmx-sse.js 存在且可访问。"""
        from pathlib import Path

        path = Path("src/novel2all/web/static/htmx-sse.js")
        assert path.exists(), "htmx-sse.js 应存在于 web/static/"
        assert path.stat().st_size > 1000, "htmx-sse.js 应 > 1KB"

    def test_htmx_sse_served_by_static_mount(self) -> None:
        """/static/htmx-sse.js 返回 200 + JS content-type。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/static/htmx-sse.js")
            assert response.status_code == 200
            assert "javascript" in response.headers["content-type"]
            # 应含 SSE 扩展代码特征
            content = response.text
            assert "Server Sent Events" in content or "htmx" in content.lower()

    def test_base_html_loads_htmx_sse(self) -> None:
        """base.html 引用 htmx-sse.js（让所有页面可用 SSE）。"""
        from pathlib import Path

        base = Path("src/novel2all/web/templates/base.html").read_text(encoding="utf-8")
        assert "htmx-sse.js" in base, "base.html 应加载 htmx-sse.js"
        # 加载顺序：htmx → htmx-sse → alpine
        htmx_pos = base.find("htmx.min.js")
        sse_pos = base.find("htmx-sse.js")
        alpine_pos = base.find("alpine.min.js")
        assert htmx_pos < sse_pos < alpine_pos, "htmx → htmx-sse → alpine 加载顺序"


class TestStreamEditorV0303:
    """V0.30.3：write_form.html 流式编辑器升级。"""

    def test_write_form_has_alpine_state_machine(self) -> None:
        """write_form.html 含 Alpine.js 状态机（status/content/charCount）。"""
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        # x-data 含状态字段
        assert "x-data=" in form
        assert "status:" in form, "Alpine state 应有 status 字段"
        assert "content" in form, "Alpine state 应有 content 字段"
        assert "charCount" in form, "Alpine state 应有 charCount 字数字段"

    def test_write_form_has_alpine_state_transitions(self) -> None:
        """Alpine state 有 4 个状态：idle/running/done/error。"""
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        # 状态字符串
        for state in ["idle", "running", "done", "error"]:
            assert f"'{state}'" in form or f'"{state}"' in form, f"Alpine state 应含 {state} 状态"

    def test_write_form_has_htmx_sse_integration(self) -> None:
        """write_form.html 配置 HTMX SSE（hx-ext + sse-swap）。"""
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        assert 'hx-ext="sse"' in form, "应启用 htmx-sse extension"
        assert 'sse-swap="message"' in form, "应配置 SSE message swap"

    def test_write_form_has_sse_event_handlers(self) -> None:
        """Alpine + htmx-sse 事件处理器（sse-before-message/sse-message/sse-after-message）。"""
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        assert "hx-on::sse-before-message" in form, "应有 sse-before-message"
        assert "hx-on::sse-message" in form, "应有 sse-message"
        assert "hx-on::sse-after-message" in form, "应有 sse-after-message"

    def test_write_form_has_char_count_display(self) -> None:
        """write_form.html 含字数显示（x-text="charCount"）。"""
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        # 字数显示
        assert "字数" in form
        assert 'x-text="charCount"' in form

    def test_write_form_has_error_display(self) -> None:
        """write_form.html 含错误状态显示。"""
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        # 错误显示
        assert "errorMsg" in form
        # status === 'error' 时显示
        assert "status === 'error'" in form

    def test_write_form_button_disabled_during_running(self) -> None:
        """V0.31：运行中按钮应 disabled（:disabled="status === 'running' || status === 'cancelling'"）。

        V0.31 新增 cancelling 状态（用户按「停止」后），按钮在 cancelling 期间也禁用。
        """
        from pathlib import Path

        form = Path("src/novel2all/web/templates/write_form.html").read_text(encoding="utf-8")
        assert ':disabled="status' in form, "按钮应根据 status 禁用"
        # V0.31：取消状态也算禁用，至少 2 个表单元素（input + select + 提交按钮）应禁用
        assert form.count(":disabled=\"status === 'running' || status === 'cancelling'\"") >= 2, (
            "至少 2 个表单元素应根据 running/cancelling 状态禁用"
        )

    def test_write_form_endpoint_still_works(self) -> None:
        """/api/write/stream/model 端点仍可用（V0.30.3 不破坏后端）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/write/stream/model",
                data={
                    "chapter": 1,
                    "project_root": "D:/nonexistent",
                },
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body = response.text
            # 应是 SSE 格式
            assert "error" in body or "started" in body
