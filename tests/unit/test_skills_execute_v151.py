"""V1.5.1 Sprint 1：skill execute + status SSE 端点测试。

测试目标（已知问题 #1 修复）：
  - POST /api/skills/{name}/execute 立即返回 task_id
  - GET /api/skills/{name}/status?task_id=... 返回 SSE 流
  - 完整事件序列：started → chunk → progress(save/extract/merge) → done
  - 错误处理：未知 skill / 未知 task_id / 项目未初始化
  - 复用现有 pipeline.write_chapter（不重新发明轮子）

参考：playbook §13 API 兜底方案 + docs/frontend-development-playbook.md §4

测试模式说明：
  - **必须用** ``with TestClient(app) as client:`` 上下文管理器。
    原因：lifespan 上下文在 ``__enter__`` 时启动 → 初始化 ``app.state.active_pipelines``
    和 ``skill_tasks``；无 lifespan → 后台 bg_task 启动后访问这些字段会 KeyError。
  - execute 端点 spawn 的 asyncio.Task + status SSE 流必须共享同一 event loop；
    context manager 保证 portal 复用。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel2all.web.app import create_app

# === 辅助函数：解析 SSE 流 ===


def _read_sse_events(response_body: str) -> list[tuple[str, dict]]:
    """解析 SSE 流，提取 (event, data) 元组列表。

    复用 test_web_sse.py 的 _read_sse_events 模式（保持向后兼容）。
    """
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


# === Fixtures ===


@pytest.fixture
def initialized_project(tmp_path: Path) -> Path:
    """创建已初始化的项目目录（带 _tracking-state.json + 细纲）。"""
    from novel2all.core.memory import Tracker

    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(
        project_name="Sprint 1 测试",
        genre="玄幻",
        style_anchor="古风古韵",
        total_chapters_target=10,
    )
    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir()
    (outline_dir / "细纲_第001章.md").write_text(
        "# 第 1 章：测试细纲\n\n林雷觉醒血脉。\n", encoding="utf-8"
    )
    return tmp_path


# === 测试 1：POST /execute 立即返回 task_id ===


class TestExecuteEndpoint:
    """V1.5.1：POST /api/skills/{name}/execute 端点基础行为。"""

    def test_execute_returns_task_id_immediately(
        self, initialized_project: Path
    ) -> None:
        """POST /execute 立即返回 task_id + status=started（不等 pipeline 完成）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps({"chapter": 1, "skip_pre_write": True}),
                    "project_root": str(initialized_project),
                },
            )

            assert response.status_code == 200
            body = response.json()
            assert "task_id" in body
            assert len(body["task_id"]) == 8  # uuid4 hex[:8]
            assert body["status"] == "started"
            assert body["skill"] == "story-long-write"
            assert "project_root" in body
            assert isinstance(body["started_at"], (int, float))

    def test_execute_unknown_skill_returns_404(self, initialized_project: Path) -> None:
        """POST /execute 未知 skill 名 → 404 + 列出可用 skill。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/skills/no-such-skill/execute",
                data={
                    "params": "{}",
                    "project_root": str(initialized_project),
                },
            )

            assert response.status_code == 404
            body = response.json()
            assert "未注册" in body["detail"]
            # 应列出可用 skill 帮助用户
            assert "story-long-write" in body["detail"]

    def test_execute_invalid_params_returns_400(self, initialized_project: Path) -> None:
        """POST /execute params 不是合法 JSON → 400。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": "这不是 JSON",
                    "project_root": str(initialized_project),
                },
            )

            assert response.status_code == 400
            body = response.json()
            assert "JSON" in body["detail"]


# === 测试 2：GET /status SSE 端点（不依赖 lifespan 状态） ===


class TestStatusEndpoint:
    """V1.5.1：GET /api/skills/{name}/status SSE 流端点。"""

    def test_status_unknown_task_id_returns_error_event(self) -> None:
        """GET /status?task_id=<不存在> → SSE error 事件 + 立即关闭。"""
        app = create_app()
        with TestClient(app) as client:
            with client.stream(
                "GET",
                "/api/skills/story-long-write/status",
                params={"task_id": "deadbeef"},
            ) as response:
                assert response.headers["content-type"].startswith("text/event-stream")
                body = response.read().decode("utf-8")

            events = _read_sse_events(body)
            assert len(events) >= 1
            error_events = [e for e in events if e[0] == "error"]
            assert len(error_events) == 1
            assert "不存在或已完成" in error_events[0][1]["message"]

    def test_status_content_type_is_sse(self) -> None:
        """GET /status Content-Type 必须是 text/event-stream。"""
        app = create_app()
        with TestClient(app) as client:
            with client.stream(
                "GET",
                "/api/skills/story-long-write/status",
                params={"task_id": "00000000"},
            ) as response:
                assert response.headers["content-type"].startswith("text/event-stream")


# === 测试 3：端到端 SSE 流验证（lifespan + monkeypatch LLM） ===


class TestExecuteStatusIntegration:
    """V1.5.1：execute → status SSE 端到端验证（用 mock LLM）。"""

    def test_full_flow_emits_started_chunk_progress_done(
        self,
        initialized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """完整流程应发出 started → chunk* → progress → done 事件。"""
        from novel2all.core.memory.extractor import ExtractedChapterInfo
        from novel2all.core.provider import LLMProvider

        async def fake_stream(self, prompt, system=None, **kwargs):
            for chunk in ["林雷", "觉醒", "血脉", "。"]:
                yield chunk

        async def fake_complete_structured(self, prompt, response_model, **kwargs):
            """Mock LLM.complete_structured 让 extractor 和 verifier 不依赖真实 API。

            V0.21 pipeline 在 write_chapter 完成后会调 extractor.extract →
            complete_structured(ExtractedChapterInfo)，以及 verifier.post_write_check →
            complete_structured(list[ConsistencyIssue])。
            """
            if response_model is ExtractedChapterInfo:
                return ExtractedChapterInfo.model_validate(
                    {"chapter": 1, "character_updates": []}
                )
            # verifier.post_write_check → list[ConsistencyIssue]
            return []

        monkeypatch.setattr(LLMProvider, "stream", fake_stream)
        monkeypatch.setattr(LLMProvider, "complete_structured", fake_complete_structured)

        app = create_app()
        with TestClient(app) as client:
            # Step 1: POST /execute 启动 task
            exec_resp = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps(
                        {"chapter": 1, "skip_pre_write": True, "min_chars": 0}
                    ),
                    "project_root": str(initialized_project),
                },
            )
            assert exec_resp.status_code == 200
            task_id = exec_resp.json()["task_id"]

            # Step 2: GET /status 订阅 SSE 流
            with client.stream(
                "GET",
                "/api/skills/story-long-write/status",
                params={"task_id": task_id},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                body = response.read().decode("utf-8")

        events = _read_sse_events(body)

        # 验证事件序列
        assert any(e[0] == "started" for e in events)
        chunk_events = [e for e in events if e[0] == "chunk"]
        assert len(chunk_events) >= 1
        collected = "".join(e[1]["text"] for e in chunk_events)
        assert collected == "林雷觉醒血脉。"

        # 验证 progress 三阶段（save/extract/merge）
        progress_events = [e for e in events if e[0] == "progress"]
        progress_phases = {e[1]["phase"] for e in progress_events}
        assert "save" in progress_phases
        assert "extract" in progress_phases
        assert "merge" in progress_phases

        # 验证 done 事件
        done_events = [e for e in events if e[0] == "done"]
        assert len(done_events) == 1
        assert done_events[0][1]["content_chars"] == len("林雷觉醒血脉。")
        assert "output_path" in done_events[0][1]
        assert done_events[0][1]["task_id"] == task_id

    def test_execute_returns_immediately_does_not_wait_for_pipeline(
        self,
        initialized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /execute 必须立即返回（不等 LLM 流）。"""
        import time

        from novel2all.core.provider import LLMProvider

        async def slow_stream(self, prompt, system=None, **kwargs):
            import asyncio

            for chunk in ["一", "二", "三"]:
                await asyncio.sleep(0.1)  # 模拟慢 LLM
                yield chunk

        monkeypatch.setattr(LLMProvider, "stream", slow_stream)

        app = create_app()
        with TestClient(app) as client:
            start = time.time()
            response = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps({"chapter": 1, "skip_pre_write": True}),
                    "project_root": str(initialized_project),
                },
            )
            elapsed = time.time() - start

            # execute 必须立即返回（< 0.5s），即使 pipeline 还在跑
            assert response.status_code == 200
            assert elapsed < 0.5
            assert response.json()["status"] == "started"


# === 测试 4：边界 case（项目未初始化 / skill_name 张冠李戴） ===


class TestSkillExecuteEdgeCases:
    """V1.5.1：skill execute 边界情况。"""

    def test_execute_project_uninitialized_returns_error(
        self, tmp_path: Path
    ) -> None:
        """POST /execute 项目未初始化 → 200（task 启动）+ status SSE 含 error 事件。"""
        # 注意：execute 端点不预校验（异步启动），错误通过 SSE 流返回
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        app = create_app()
        with TestClient(app) as client:
            exec_resp = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps({"chapter": 1}),
                    "project_root": str(empty_dir),
                },
            )
            assert exec_resp.status_code == 200
            task_id = exec_resp.json()["task_id"]

            # status SSE 应发 error 事件
            with client.stream(
                "GET",
                "/api/skills/story-long-write/status",
                params={"task_id": task_id},
            ) as response:
                body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) >= 1
        assert "项目未初始化" in error_events[0][1]["message"]

    def test_status_skill_name_mismatch_returns_error(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GET /status?task_id=X 但 skill_name 与 execute 时不符 → SSE error 事件。

        验证 skill_name 校验逻辑（防止 task_id 张冠李戴）。
        """
        from novel2all.core.provider import LLMProvider

        async def fake_stream(self, prompt, system=None, **kwargs):
            for chunk in ["ok"]:
                yield chunk

        monkeypatch.setattr(LLMProvider, "stream", fake_stream)

        app = create_app()
        with TestClient(app) as client:
            # 用 story-long-write 启动
            exec_resp = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps({"chapter": 1, "skip_pre_write": True, "min_chars": 0}),
                    "project_root": str(initialized_project),
                },
            )
            task_id = exec_resp.json()["task_id"]

            # 用错的 skill_name 订阅 → 应立即 error
            with client.stream(
                "GET",
                "/api/skills/story-long-analyze/status",
                params={"task_id": task_id},
            ) as response:
                body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) == 1
        assert "不匹配" in error_events[0][1]["message"]


# === 测试 5：HTTP 客户端契约（与前端 React Query hook 兼容） ===


class TestSkillExecuteHTTPContract:
    """V1.5.1：HTTP 响应契约与前端 React Query hook 兼容。"""

    def test_execute_response_schema_matches_frontend_zod(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POST /execute 返回字段匹配 SkillExecuteResponseSchema（前端校验）。"""
        from novel2all.core.provider import LLMProvider

        async def fake_stream(self, prompt, system=None, **kwargs):
            for chunk in ["ok"]:
                yield chunk

        monkeypatch.setattr(LLMProvider, "stream", fake_stream)

        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps({"chapter": 1, "skip_pre_write": True, "min_chars": 0}),
                    "project_root": str(initialized_project),
                },
            )

            body = response.json()
            # SkillExecuteResponseSchema 字段：task_id, status, started_at
            assert "task_id" in body
            assert "status" in body
            assert body["status"] in ("queued", "running", "started", "done")
            # started_at 是 optional
            if "started_at" in body:
                assert isinstance(body["started_at"], (int, float))

    def test_status_sse_event_names_match_frontend_expectations(
        self,
        initialized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SSE 事件名必须匹配 useSkillStream 订阅的 event 名称（chunk/progress/done/error）。"""
        from novel2all.core.provider import LLMProvider

        async def fake_stream(self, prompt, system=None, **kwargs):
            for chunk in ["测试"]:
                yield chunk

        monkeypatch.setattr(LLMProvider, "stream", fake_stream)

        app = create_app()
        with TestClient(app) as client:
            exec_resp = client.post(
                "/api/skills/story-long-write/execute",
                data={
                    "params": json.dumps({"chapter": 1, "skip_pre_write": True, "min_chars": 0}),
                    "project_root": str(initialized_project),
                },
            )
            task_id = exec_resp.json()["task_id"]

            with client.stream(
                "GET",
                "/api/skills/story-long-write/status",
                params={"task_id": task_id},
            ) as response:
                body = response.read().decode("utf-8")

        events = _read_sse_events(body)
        event_names = {e[0] for e in events}

        # 前端 useSkillStream 订阅的事件名（api/skills.ts 的 useSkillStream.ts）
        expected_events = {"started", "chunk", "progress", "done"}
        assert expected_events.issubset(event_names), (
            f"缺失前端订阅的事件: {expected_events - event_names}"
        )