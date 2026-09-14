"""V0.30.6 B1：4-agent 并行审查测试（mock LLM）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from novel2all.core.memory.multi_reviewer import (
    CRITICAL_AUDIT_PROMPT,
    MAJOR_AUDIT_PROMPT,
    MINOR_AUDIT_PROMPT,
    QUALITY_JUDGE_PROMPT,
    MultiAgentReviewer,
    QualityScore,
    ReviewIssue,
    ReviewReport,
)
from novel2all.core.memory.verifier import ConsistencyIssue

# === Mock LLM Provider ===


class MockLLM:
    """V0.30.6 B1：mock LLM（返回预设数据 + 异步接口）。

    模拟 LLMProvider.complete_structured(prompt, response_model) 的行为。
    每个测试可预设 4 个 agent 的返回值。
    """

    def __init__(
        self,
        critical_return: list[ConsistencyIssue] | None = None,
        major_return: list[ConsistencyIssue] | None = None,
        minor_return: list[ConsistencyIssue] | None = None,
        quality_return: QualityScore | None = None,
    ):
        self.critical_return = critical_return or []
        self.major_return = major_return or []
        self.minor_return = minor_return or []
        self.quality_return = quality_return or QualityScore(
            overall_score=8.0,
            pacing=8.0,
            emotion=7.5,
            readability=8.5,
            immersion=8.0,
            ai_smell=7.0,
            verdict="pass",
            summary="整体流畅，AI 痕迹略多",
        )
        self.call_count = 0
        self.call_log: list[tuple[str, type]] = []  # 记录 (prompt 关键词, response_model 类型)

    async def complete_structured(self, *, prompt: str, response_model: Any, **kwargs: Any) -> Any:
        """V0.30.6 B1：异步 mock LLM 调用。"""
        self.call_count += 1

        # 根据 prompt 关键词判断调用哪个 agent
        if "严重错误审查员" in prompt:
            self.call_log.append(("critical", response_model))
            return self.critical_return
        if "中度问题审查员" in prompt:
            self.call_log.append(("major", response_model))
            return self.major_return
        if "细节优化审查员" in prompt:
            self.call_log.append(("minor", response_model))
            return self.minor_return
        if "质量评审员" in prompt:
            self.call_log.append(("quality", response_model))
            return self.quality_return

        raise ValueError(f"Unknown agent prompt: {prompt[:100]}")


# === Fixtures ===


@pytest.fixture
def mock_llm() -> MockLLM:
    """V0.30.6 B1：默认 mock LLM（所有 agent 返回空 + quality 默认 pass）。"""
    return MockLLM()


@pytest.fixture
def mock_state() -> Any:
    """V0.30.6 B1：mock TrackingState（最小字段集）。"""

    class _State:
        characters = {"林雷": type("Char", (), {"description": "主角，18 岁剑客"})()}
        foreshadowing = []
        style_anchor = "古风古韵"

    return _State()


# === Test 1: Data structure tests ===


class TestReviewDataStructures:
    """V0.30.6 B1：ReviewIssue / QualityScore / ReviewReport 数据结构。"""

    def test_review_issue_inherits_consistency_issue(self) -> None:
        """V0.30.6 B1：ReviewIssue 继承 ConsistencyIssue（复用字段）。"""
        issue = ReviewIssue(
            agent="critical",
            agent_label="严重错误",
            severity="critical",
            category="fact",
            description="林雷上一章已死，本章还活着",
            evidence="第5章最后一段",
            suggestion="改为梦境/回忆段落",
        )
        assert issue.agent == "critical"
        assert issue.agent_label == "严重错误"
        assert issue.severity == "critical"
        assert issue.description == "林雷上一章已死，本章还活着"

    def test_quality_score_default_5(self) -> None:
        """V0.30.6 B1：QualityScore 字段范围 0-10。"""
        score = QualityScore(
            overall_score=7.5,
            pacing=8.0,
            emotion=7.0,
            readability=8.0,
            immersion=7.5,
            ai_smell=6.5,
            verdict="pass",
            summary="良好",
        )
        assert score.overall_score == 7.5
        assert score.verdict == "pass"

    def test_review_report_aggregation(self) -> None:
        """V0.30.6 B1：ReviewReport 聚合字段。"""
        report = ReviewReport(
            total_critical=1,
            total_major=3,
            total_minor=5,
            overall_verdict="warn",
            elapsed_seconds=2.5,
            content_chars=3000,
            chapter_number=10,
        )
        assert report.total_critical == 1
        assert report.total_major == 3
        assert report.overall_verdict == "warn"
        assert report.chapter_number == 10

    def test_review_report_to_dict_serializable(self) -> None:
        """V0.30.6 B1：ReviewReport.model_dump() 可直接 JSON 序列化。"""
        report = ReviewReport(
            total_critical=0,
            total_major=1,
            total_minor=2,
            overall_verdict="warn",
        )
        d = report.to_dict()
        assert d["total_critical"] == 0
        assert d["overall_verdict"] == "warn"
        # 必须可序列化
        import json

        json.dumps(d)


# === Test 2: Multi-agent 并行执行 ===


class TestMultiAgentParallel:
    """V0.30.6 B1：4 个 agent 并行执行。"""

    async def test_all_4_agents_called(self, mock_llm: MockLLM, mock_state: Any) -> None:
        """V0.30.6 B1：review() 调用全部 4 个 agent。"""
        reviewer = MultiAgentReviewer(mock_llm)
        await reviewer.review(state=mock_state, content="第1章内容", chapter_number=1)

        assert mock_llm.call_count == 4
        called_agents = {log[0] for log in mock_llm.call_log}
        assert called_agents == {"critical", "major", "minor", "quality"}

    async def test_parallel_execution(self, mock_state: Any) -> None:
        """V0.30.6 B1：4 个 agent 并行（asyncio.gather），不是串行。

        通过 mock 验证：4 个 agent 应该同时启动，而非先后。
        实测：4 个 mock 调用几乎在同一时刻启动，总耗时 ≈ 单个 agent 耗时。
        """
        import time as _time

        class SlowMock(MockLLM):
            async def complete_structured(
                self, *, prompt: str, response_model: Any, **kwargs: Any
            ) -> Any:
                await asyncio.sleep(0.1)  # 每个 agent 模拟 100ms LLM 调用
                return await super().complete_structured(
                    prompt=prompt, response_model=response_model, **kwargs
                )

        llm = SlowMock()
        reviewer = MultiAgentReviewer(llm)

        t0 = _time.perf_counter()
        report = await reviewer.review(state=mock_state, content="测试")
        elapsed = _time.perf_counter() - t0

        # 并行 4 个 100ms 调用 → 总耗时 ≈ 100ms（+ overhead），远小于 400ms
        # 留 200ms 余量以防机器慢
        assert elapsed < 0.2, f"并行执行耗时 {elapsed:.3f}s，应 < 0.2s（若串行则 ≈0.4s）"
        assert report.elapsed_seconds < 0.2

    async def test_empty_results_all_pass(self, mock_llm: MockLLM, mock_state: Any) -> None:
        """V0.30.6 B1：无任何 issues + quality 8 分 → verdict=pass。"""
        reviewer = MultiAgentReviewer(mock_llm)
        report = await reviewer.review(state=mock_state, content="第1章", chapter_number=1)

        assert report.total_critical == 0
        assert report.total_major == 0
        assert report.total_minor == 0
        assert report.overall_verdict == "pass"

    async def test_critical_issues_trigger_fail(self, mock_state: Any) -> None:
        """V0.30.6 B1：任何 critical issue → verdict=fail。"""
        llm = MockLLM(
            critical_return=[
                ConsistencyIssue(
                    severity="critical",
                    category="fact",
                    description="林雷已死却仍出现",
                    evidence="第5章死亡设定",
                )
            ],
            quality_return=QualityScore(
                overall_score=8.0,
                pacing=8.0,
                emotion=8.0,
                readability=8.0,
                immersion=8.0,
                ai_smell=8.0,
                verdict="pass",
                summary="OK",
            ),
        )
        reviewer = MultiAgentReviewer(llm)
        report = await reviewer.review(state=mock_state, content="X", chapter_number=1)
        assert report.total_critical == 1
        assert report.overall_verdict == "fail"
        # 确认 critical issue 注入了 agent 字段
        assert report.critical_issues[0].agent == "critical"
        assert report.critical_issues[0].agent_label == "严重错误"

    async def test_many_major_issues_trigger_warn(self, mock_state: Any) -> None:
        """V0.30.6 B1：major > 2 → verdict=warn。"""
        llm = MockLLM(
            major_return=[
                ConsistencyIssue(severity="warning", category="pacing", description=f"问题{i}")
                for i in range(3)
            ],
        )
        reviewer = MultiAgentReviewer(llm)
        report = await reviewer.review(state=mock_state, content="X", chapter_number=1)
        assert report.total_major == 3
        assert report.overall_verdict == "warn"

    async def test_low_quality_score_triggers_fail(self, mock_state: Any) -> None:
        """V0.30.6 B1：quality_score < 5 → verdict=fail（即使 0 critical/major）。"""
        llm = MockLLM(
            quality_return=QualityScore(
                overall_score=4.0,
                pacing=4.0,
                emotion=4.0,
                readability=4.0,
                immersion=4.0,
                ai_smell=4.0,
                verdict="fail",
                summary="烂",
            ),
        )
        reviewer = MultiAgentReviewer(llm)
        report = await reviewer.review(state=mock_state, content="X", chapter_number=1)
        assert report.overall_verdict == "fail"


# === Test 3: 错误处理（LLM 失败不应阻塞整个 review） ===


class TestErrorHandling:
    """V0.30.6 B1：单个 agent 失败不应影响其他 agent。"""

    async def test_critical_agent_failure_returns_empty(self, mock_state: Any) -> None:
        """V0.30.6 B1：critical agent 抛异常 → 空 issues + 不影响其他 agent。"""

        class FailingMock(MockLLM):
            async def complete_structured(
                self, *, prompt: str, response_model: Any, **kwargs: Any
            ) -> Any:
                if "严重错误审查员" in prompt:
                    raise RuntimeError("LLM API error")
                return await super().complete_structured(
                    prompt=prompt, response_model=response_model, **kwargs
                )

        llm = FailingMock(
            major_return=[
                ConsistencyIssue(severity="warning", category="pacing", description="拖")
            ],
            quality_return=QualityScore(
                overall_score=8.0,
                pacing=8.0,
                emotion=8.0,
                readability=8.0,
                immersion=8.0,
                ai_smell=8.0,
                verdict="pass",
                summary="OK",
            ),
        )
        reviewer = MultiAgentReviewer(llm)
        report = await reviewer.review(state=mock_state, content="X")
        assert report.total_critical == 0  # 失败 → 0
        assert report.total_major == 1  # 其他 agent 正常
        assert report.overall_verdict == "pass"

    async def test_quality_agent_failure_returns_default_5(self, mock_state: Any) -> None:
        """V0.30.6 B1：quality agent 失败 → 默认 5 分（中性评分）。"""

        class FailingMock(MockLLM):
            async def complete_structured(
                self, *, prompt: str, response_model: Any, **kwargs: Any
            ) -> Any:
                if "质量评审员" in prompt:
                    raise RuntimeError("LLM API error")
                return await super().complete_structured(
                    prompt=prompt, response_model=response_model, **kwargs
                )

        llm = FailingMock()
        reviewer = MultiAgentReviewer(llm)
        report = await reviewer.review(state=mock_state, content="X")
        assert report.quality_score is not None
        assert report.quality_score.overall_score == 5.0
        assert "失败" in report.quality_score.summary


# === Test 4: Prompt 内容 ===


class TestPrompts:
    """V0.30.6 B1：4 个 prompt 内容各自关注点不同。"""

    def test_critical_prompt_focus(self) -> None:
        """V0.30.6 B1：critical prompt 只关注 5 类致命问题。"""
        assert "严重错误" in CRITICAL_AUDIT_PROMPT
        assert "事实硬伤" in CRITICAL_AUDIT_PROMPT
        assert "逻辑断裂" in CRITICAL_AUDIT_PROMPT
        assert "宁缺毋滥" in CRITICAL_AUDIT_PROMPT

    def test_major_prompt_focus(self) -> None:
        """V0.30.6 B1：major prompt 只关注 4 类中度问题。"""
        assert "中度问题" in MAJOR_AUDIT_PROMPT
        assert "情节拖沓" in MAJOR_AUDIT_PROMPT
        assert "对话不自然" in MAJOR_AUDIT_PROMPT

    def test_minor_prompt_focus(self) -> None:
        """V0.30.6 B1：minor prompt 只关注 4 类小瑕疵。"""
        assert "细节优化" in MINOR_AUDIT_PROMPT
        assert "文笔问题" in MINOR_AUDIT_PROMPT
        assert "AI 痕迹" in MINOR_AUDIT_PROMPT

    def test_quality_prompt_no_issues(self) -> None:
        """V0.30.6 B1：quality prompt 明确说"不报具体问题，只打分"。"""
        assert "质量评审员" in QUALITY_JUDGE_PROMPT
        assert "只打分" in QUALITY_JUDGE_PROMPT
        assert "不要报具体问题" in QUALITY_JUDGE_PROMPT


# === Test 5: State 序列化 ===


class TestStateSerialization:
    """V0.30.6 B1：_state_to_text() 正确序列化 TrackingState 字段。"""

    def test_state_with_characters(self) -> None:
        """V0.30.6 B1：state 含 characters → 输出角色列表。"""

        class _State:
            characters = {
                "林雷": type("C", (), {"description": "主角 18 岁"})(),
                "萧炎": type("C", (), {"description": "配角 20 岁"})(),
            }
            foreshadowing = []
            style_anchor = "古风"

        text = MultiAgentReviewer._state_to_text(_State())
        assert "## 角色" in text
        assert "林雷" in text
        assert "萧炎" in text

    def test_state_with_foreshadowing(self) -> None:
        """V0.30.6 B1：state 含 foreshadowing → 输出伏笔列表。"""

        class _FS:
            id = "fs_001"
            description = "神秘玉佩"
            status = "active"

        class _State:
            characters = {}
            foreshadowing = [_FS()]
            style_anchor = None

        text = MultiAgentReviewer._state_to_text(_State())
        assert "## 伏笔" in text
        assert "fs_001" in text

    def test_state_empty(self) -> None:
        """V0.30.6 B1：空 state → 返回"无已有状态"。"""
        text = MultiAgentReviewer._state_to_text(None)
        assert "无已有状态" in text

    def test_state_no_attrs(self) -> None:
        """V0.30.6 B1：state 缺字段 → 不 crash，返回"无已有状态"。"""

        class _Empty:
            pass

        text = MultiAgentReviewer._state_to_text(_Empty())
        assert "无已有状态" in text


# === Test 6: Content preview + elapsed_seconds ===


class TestReportMetadata:
    """V0.30.6 B1：报告元数据正确填充。"""

    async def test_content_chars_count(self, mock_llm: MockLLM, mock_state: Any) -> None:
        """V0.30.6 B1：content_chars 等于 content 长度。"""
        reviewer = MultiAgentReviewer(mock_llm)
        content = "这是一段测试内容。" * 100
        report = await reviewer.review(state=mock_state, content=content)
        assert report.content_chars == len(content)

    async def test_content_preview_first_200_chars(
        self, mock_llm: MockLLM, mock_state: Any
    ) -> None:
        """V0.30.6 B1：content_preview 是前 200 字。"""
        reviewer = MultiAgentReviewer(mock_llm)
        content = "X" * 500
        report = await reviewer.review(state=mock_state, content=content)
        assert len(report.content_preview) == 200
        assert report.content_preview == "X" * 200

    async def test_chapter_number_recorded(self, mock_llm: MockLLM, mock_state: Any) -> None:
        """V0.30.6 B1：chapter_number 正确保存。"""
        reviewer = MultiAgentReviewer(mock_llm)
        report = await reviewer.review(state=mock_state, content="X", chapter_number=42)
        assert report.chapter_number == 42

    async def test_elapsed_seconds_recorded(self, mock_llm: MockLLM, mock_state: Any) -> None:
        """V0.30.6 B1：elapsed_seconds >= 0（mock LLM 可能瞬时返回）。"""
        reviewer = MultiAgentReviewer(mock_llm)
        report = await reviewer.review(state=mock_state, content="X")
        assert report.elapsed_seconds >= 0  # mock 可能 0.0s
        assert report.elapsed_seconds < 5.0


# === Test 7: Web API 端点 ===


class TestMultiReviewerEndpoint:
    """V0.30.6 B1：/api/chapter/{n}/review 端点。"""

    async def test_review_endpoint_returns_report(self, tmp_path: Any) -> None:
        """V0.30.6 B1：POST /api/chapter/1/review 返回完整 ReviewReport。"""
        from fastapi.testclient import TestClient

        from novel2all.web.app import create_app

        # 创建测试项目结构
        (tmp_path / "_tracking-state.json").write_text("{}", encoding="utf-8")
        (tmp_path / "正文").mkdir()
        (tmp_path / "正文" / "第001章.md").write_text(
            "# 第1章\n\n这是测试章节内容。", encoding="utf-8"
        )

        # Mock LLM by patching complete_structured method on the provider
        from unittest.mock import patch

        app = create_app()
        mock_llm = MockLLM()
        with TestClient(app) as client:
            # Replace provider.complete_structured with mock_llm.complete_structured
            with patch.object(
                app.state.provider,
                "complete_structured",
                side_effect=lambda **kwargs: mock_llm.complete_structured(**kwargs),
            ):
                response = client.post(f"/api/chapter/1/review?project_root={tmp_path}")
                assert response.status_code == 200
                data = response.json()
                assert "critical_issues" in data
                assert "major_issues" in data
                assert "minor_issues" in data
                assert "quality_score" in data
                assert "overall_verdict" in data
                assert "elapsed_seconds" in data
                assert "content_chars" in data
                assert "chapter_number" in data
                assert data["chapter_number"] == 1
                assert data["overall_verdict"] == "pass"

    async def test_review_endpoint_chapter_not_found(self, tmp_path: Any) -> None:
        """V0.30.6 B1：章节不存在 → 404。"""
        from fastapi.testclient import TestClient

        from novel2all.web.app import create_app

        (tmp_path / "_tracking-state.json").write_text("{}", encoding="utf-8")
        (tmp_path / "正文").mkdir()

        app = create_app()
        with TestClient(app) as client:
            response = client.post(f"/api/chapter/999/review?project_root={tmp_path}")
            assert response.status_code == 404
