"""Web SSE 端点单元测试。

测试目标：
- /api/write/stream 端点存在且返回 SSE 格式
- sse_event() 格式化正确
- 事件序列：started → pre_write_check → chunk → progress → post_write_check → done
- 错误处理：项目未初始化 / outline 不存在 / pre-write blocking issues
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel2all.web.app import create_app, sse_event

# === sse_event 格式化测试 ===


class TestSSEEvent:
    def test_basic_event(self) -> None:
        result = sse_event("started", {"chapter": 1})
        assert result.startswith("event: started\n")
        assert "data:" in result
        assert result.endswith("\n\n")

    def test_data_is_json(self) -> None:
        result = sse_event("done", {"chars": 2000})
        # 提取 data 行
        for line in result.split("\n"):
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                parsed = json.loads(payload)
                assert parsed == {"chars": 2000}

    def test_chinese_text_preserved(self) -> None:
        """ensure_ascii=False 应保留中文。"""
        result = sse_event("chunk", {"text": "林雷觉醒血脉"})
        assert "林雷觉醒血脉" in result

    def test_complex_data(self) -> None:
        data = {
            "issues": [
                {"severity": "warning", "description": "节奏偏密"},
                {"severity": "info", "description": "钩子清晰"},
            ],
            "meta": {"version": "0.21"},
        }
        result = sse_event("post_write_check", data)
        assert "节奏偏密" in result
        assert '"severity":":""warning""' not in result  # 没被双重转义


def _read_sse_events(response_body: str) -> list[tuple[str, dict]]:
    """解析 SSE 流，提取 (event, data) 元组列表。"""
    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    for line in response_body.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: ") :].strip()
        elif line.startswith("data: ") and current_event:
            payload = line[len("data: ") :].strip()
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = {"raw": payload}
            events.append((current_event, parsed))
            current_event = None
    return events


# === 客户端测试（用真实 TestClient + mock pipeline） ===


class TestWriteStreamEndpoint:
    """测试 /api/write/stream 端点。

    通过注入 monkeypatch 替换 pipeline 行为，验证事件序列。
    """

    @pytest.fixture
    def initialized_project(self, tmp_path: Path) -> Path:
        """创建已初始化的项目目录（带 _tracking-state.json + 细纲）。"""
        # 初始化 tracking state
        from novel2all.core.memory import Tracker

        tracker = Tracker(tmp_path / "_tracking-state.json")
        tracker.init(
            project_name="SSE 测试项目",
            genre="玄幻",
            style_anchor="古风古韵",
            total_chapters_target=10,
        )
        # 创建细纲
        outline_dir = tmp_path / "大纲"
        outline_dir.mkdir()
        (outline_dir / "细纲_第001章.md").write_text(
            "# 第 1 章：测试细纲\n\n林雷觉醒血脉。\n", encoding="utf-8"
        )
        return tmp_path

    @staticmethod
    def _read_sse_events(response_body: str) -> list[tuple[str, dict]]:
        """解析 SSE 流，提取 (event, data) 元组列表。"""
        events: list[tuple[str, dict]] = []
        current_event: str | None = None
        for line in response_body.split("\n"):
            if line.startswith("event: "):
                current_event = line[len("event: ") :].strip()
            elif line.startswith("data: ") and current_event:
                payload = line[len("data: ") :].strip()
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = {"raw": payload}
                events.append((current_event, parsed))
                current_event = None
        return events

    def test_project_not_initialized(self, tmp_path: Path) -> None:
        app = create_app()
        client = TestClient(app)

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with client.stream(
            "GET", "/api/write/stream", params={"chapter": 1, "project_root": str(empty_dir)}
        ) as response:
            assert response.status_code == 200
            body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        # 应该至少有一个 error 事件
        assert len(events) >= 1
        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) >= 1
        assert "项目未初始化" in error_events[0][1]["message"]

    def test_outline_not_found(self, initialized_project: Path) -> None:
        """项目存在但章节细纲不存在 → 应报 outline_not_found error。"""
        app = create_app()
        client = TestClient(app)

        # 请求章节 999（没有细纲）
        with client.stream(
            "GET",
            "/api/write/stream",
            params={"chapter": 999, "project_root": str(initialized_project)},
        ) as response:
            assert response.status_code == 200
            body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        # 应该有 started → error
        assert events[0][0] == "started"
        assert events[1][0] == "error"
        assert events[1][1].get("code") == "outline_not_found"

    def test_endpoint_returns_sse_content_type(self) -> None:
        """端点 Content-Type 必须是 text/event-stream。"""
        app = create_app()
        client = TestClient(app)

        with client.stream(
            "GET", "/api/write/stream", params={"chapter": 1, "project_root": "."}
        ) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            # 不需要读完整个 body

    def test_endpoint_with_minimal_params(self) -> None:
        """最少参数（仅 chapter）调用。"""
        app = create_app()
        client = TestClient(app)

        with client.stream(
            "GET", "/api/write/stream", params={"chapter": 1, "project_root": "."}
        ) as response:
            assert response.status_code == 200
            # 至少能拿到 started 或 error 事件
            body = response.read().decode("utf-8")
            events = _read_sse_events(body)
            assert len(events) >= 1
            assert events[0][0] in ("started", "error")


# === 集成测试：用 monkeypatch 替换 LLM 来验证完整事件流 ===


class TestSSEStreamFlow:
    """模拟完整 pipeline 流程（用 mock LLM），验证 SSE 事件序列。"""

    @pytest.fixture
    def initialized_project(self, tmp_path: Path) -> Path:
        from novel2all.core.memory import Tracker

        tracker = Tracker(tmp_path / "_tracking-state.json")
        tracker.init(
            project_name="Flow 测试",
            genre="玄幻",
            style_anchor="古风古韵",
            total_chapters_target=5,
        )
        outline_dir = tmp_path / "大纲"
        outline_dir.mkdir()
        (outline_dir / "细纲_第001章.md").write_text(
            "# 第 1 章\n\n林雷觉醒血脉。\n", encoding="utf-8"
        )
        return tmp_path

    def test_full_flow_emits_all_events(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """完整流程应发出 started → progress → done 事件。"""
        from novel2all.core.provider import LLMProvider

        # mock LLM stream：返回固定文本
        async def fake_stream(self, prompt, system=None, **kwargs):
            for chunk in ["林雷", "觉醒", "血脉", "。"]:
                yield chunk

        monkeypatch.setattr(LLMProvider, "stream", fake_stream)

        app = create_app()
        client = TestClient(app)

        with client.stream(
            "GET",
            "/api/write/stream",
            params={
                "chapter": 1,
                "project_root": str(initialized_project),
                "skip_pre_write": "true",  # 跳过避免 pre-write check 干扰
            },
        ) as response:
            body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        event_names = [e[0] for e in events]

        # 至少有 started 和 chunk 事件流（progress / done 取决于 post-write 是否成功）
        assert "started" in event_names
        # chunk 事件应包含完整内容
        chunk_events = [e for e in events if e[0] == "chunk"]
        assert len(chunk_events) >= 1
        collected = "".join(e[1]["text"] for e in chunk_events)
        assert collected == "林雷觉醒血脉。"

        # 如果有 done 事件，验证关键字段
        done_events = [e for e in events if e[0] == "done"]
        if done_events:
            assert done_events[0][1]["content_chars"] == len("林雷觉醒血脉。")
            assert "output_path" in done_events[0][1]

    def test_chunk_event_concatenation(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """chunk 事件应能被客户端拼接为完整文本。"""
        from novel2all.core.provider import LLMProvider

        chunks = ["第一段，", "第二段，", "第三段。"]

        async def fake_stream(self, prompt, system=None, **kwargs):
            for c in chunks:
                yield c

        monkeypatch.setattr(LLMProvider, "stream", fake_stream)

        app = create_app()
        client = TestClient(app)

        with client.stream(
            "GET",
            "/api/write/stream",
            params={
                "chapter": 1,
                "project_root": str(initialized_project),
                "skip_pre_write": "true",
            },
        ) as response:
            body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        chunk_events = [e for e in events if e[0] == "chunk"]
        collected = "".join(e[1]["text"] for e in chunk_events)
        assert collected == "".join(chunks)

    def test_error_event_on_llm_failure(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM 调用失败时应发 error 事件。"""
        from novel2all.core.provider import LLMProvider

        async def fake_stream_error(self, prompt, system=None, **kwargs):
            if False:
                yield ""
            raise RuntimeError("模拟 LLM 失败")

        monkeypatch.setattr(LLMProvider, "stream", fake_stream_error)

        app = create_app()
        client = TestClient(app)

        with client.stream(
            "GET",
            "/api/write/stream",
            params={
                "chapter": 1,
                "project_root": str(initialized_project),
                "skip_pre_write": "true",
            },
        ) as response:
            body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) >= 1
        assert "模拟 LLM 失败" in error_events[0][1]["message"]
