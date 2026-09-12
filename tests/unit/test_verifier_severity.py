"""Verifier 严重程度分类测试。

目标：验证 verifier 的 prompt 设计 + _filter_issues 后处理
- "软"问题（节奏、文风、抽象连贯担忧）应被归为 warning/info
- 只有"硬"问题（角色死而复活、状态硬冲突）才判 critical
- prompt 设计意图用 mock LLM 验证
- _filter_issues 去重 + severity 兜底

注：完整 prompt 测试留给真实 LLM（需要 key），这里主要验证
后处理逻辑 + 设计意图。
"""

from __future__ import annotations

from typing import Any

import pytest

from novel2all.core.memory.tracker import CharacterState, ForeshadowingState, TrackingState
from novel2all.core.memory.verifier import (
    POST_WRITE_PROMPT,
    PRE_WRITE_PROMPT,
    ConsistencyIssue,
    Verifier,
)

# === _filter_issues 行为 ===


class TestFilterIssues:
    def test_empty_input_returns_empty(self) -> None:
        result = Verifier._filter_issues([])
        assert result == []

    def test_valid_severities_preserved(self) -> None:
        issues = [
            ConsistencyIssue(severity="critical", category="character", description="x"),
            ConsistencyIssue(severity="warning", category="style", description="y"),
            ConsistencyIssue(severity="info", category="timeline", description="z"),
        ]
        result = Verifier._filter_issues(issues)
        assert len(result) == 3
        assert [i.severity for i in result] == ["critical", "warning", "info"]

    def test_invalid_severity_falls_back_to_warning(self) -> None:
        """LLM 偶尔返回非标准 severity 时，兜底为 warning。"""
        issues = [
            ConsistencyIssue(severity="CRITICAL", category="x", description="a"),  # 大写
            ConsistencyIssue(severity="error", category="x", description="b"),  # 未知
            ConsistencyIssue(severity="", category="x", description="c"),  # 空
        ]
        result = Verifier._filter_issues(issues)
        assert all(i.severity == "warning" for i in result)
        assert len(result) == 3

    def test_duplicates_removed(self) -> None:
        """同一 (severity, category, description) 只保留一条。"""
        issues = [
            ConsistencyIssue(severity="warning", category="style", description="重复"),
            ConsistencyIssue(severity="warning", category="style", description="重复"),
            ConsistencyIssue(severity="warning", category="style", description="重复"),
        ]
        result = Verifier._filter_issues(issues)
        assert len(result) == 1

    def test_different_descriptions_not_deduplicated(self) -> None:
        issues = [
            ConsistencyIssue(severity="warning", category="style", description="a"),
            ConsistencyIssue(severity="warning", category="style", description="b"),
            ConsistencyIssue(severity="warning", category="style", description="a"),
        ]
        result = Verifier._filter_issues(issues)
        assert len(result) == 2  # a 和 b 各一条


# === has_blocking_issues ===


class TestHasBlockingIssues:
    def test_empty(self) -> None:
        assert Verifier.has_blocking_issues([]) is False

    def test_warning_only(self) -> None:
        assert (
            Verifier.has_blocking_issues(
                [
                    ConsistencyIssue(severity="warning", category="x", description=""),
                ]
            )
            is False
        )

    def test_info_only(self) -> None:
        assert (
            Verifier.has_blocking_issues(
                [
                    ConsistencyIssue(severity="info", category="x", description=""),
                ]
            )
            is False
        )

    def test_critical_blocks(self) -> None:
        assert (
            Verifier.has_blocking_issues(
                [
                    ConsistencyIssue(severity="warning", category="x", description=""),
                    ConsistencyIssue(severity="critical", category="x", description=""),
                ]
            )
            is True
        )

    def test_fallback_severity_after_filter(self) -> None:
        """验证 filter 后 warning 不会变 critical。"""
        issues = [
            ConsistencyIssue(severity="INVALID_VALUE", category="x", description=""),
        ]
        result = Verifier._filter_issues(issues)
        # 兜底为 warning
        assert Verifier.has_blocking_issues(result) is False


# === Mock LLM 场景测试 ===


class MockLLM:
    """记录最近一次的 prompt，结构化输出固定 issues。"""

    def __init__(self, return_issues: list[ConsistencyIssue]):
        self.return_issues = return_issues
        self.last_prompt = ""

    async def complete_structured(self, prompt: str, *, response_model: Any, **kwargs: Any) -> Any:
        self.last_prompt = prompt
        # 模仿 instructor 返回 response_model 实例
        return self.return_issues


class TestPreWriteScenario:
    """pre_write_check 应该按 prompt 设计意图区分 critical/warning。"""

    @pytest.mark.asyncio
    async def test_soft_issues_pass_through(self) -> None:
        """软问题（节奏、文风）应该被 LLM 判为 warning，不阻断。"""
        state = TrackingState(project_name="test", style_anchor="古风")
        state.characters["林雷"] = CharacterState(
            name="林雷",
            location="苍茫镇",
            emotional_state="懵懂",
            last_updated_chapter=0,
        )
        # 模拟 LLM 返回"软"问题
        llm = MockLLM(
            return_issues=[
                ConsistencyIssue(
                    severity="warning",
                    category="foreshadowing",
                    description="建议第 5 章揭示 fs_xxx",
                ),
                ConsistencyIssue(
                    severity="warning", category="style", description="文风与 style_anchor 略有不符"
                ),
            ]
        )
        verifier = Verifier(llm)
        issues = await verifier.pre_write_check(state, "本章大纲：林雷觉醒")
        # 软问题不阻断
        assert Verifier.has_blocking_issues(issues) is False
        assert all(i.severity == "warning" for i in issues)

    @pytest.mark.asyncio
    async def test_hard_issues_block(self) -> None:
        """硬问题（角色死而复活）应该判为 critical，阻断。"""
        state = TrackingState(project_name="test", style_anchor="古风")
        # 林雷父亲第 3 章已死亡
        state.characters["林雷父亲"] = CharacterState(
            name="林雷父亲",
            location="已死亡",
            emotional_state=None,
            last_updated_chapter=3,
        )
        # LLM 判为 critical（角色死而复活）
        llm = MockLLM(
            return_issues=[
                ConsistencyIssue(
                    severity="critical",
                    category="character",
                    description="林雷父亲已在第 3 章死亡，本章却让他活着出现",
                    evidence="state.characters[林雷父亲].location='已死亡'",
                ),
            ]
        )
        verifier = Verifier(llm)
        issues = await verifier.pre_write_check(state, "本章大纲：林雷父亲传授林雷武技")
        assert Verifier.has_blocking_issues(issues) is True


class TestPostWriteScenario:
    """post_write_check 应该按 prompt 设计意图区分 critical/warning。"""

    @pytest.mark.asyncio
    async def test_ai_smell_warning_not_critical(self) -> None:
        """AI 味应该是 warning。"""
        state = TrackingState(project_name="test", style_anchor="古风")
        llm = MockLLM(
            return_issues=[
                ConsistencyIssue(
                    severity="warning",
                    category="ai_smell",
                    description="出现套话'综上所述'",
                    evidence="综上所述，林雷决定...",
                ),
            ]
        )
        verifier = Verifier(llm)
        content = "综上所述，林雷决定继续修炼。"
        issues = await verifier.post_write_check(state, content)
        assert Verifier.has_blocking_issues(issues) is False

    @pytest.mark.asyncio
    async def test_word_count_deviation_info(self) -> None:
        """字数偏离应该是 info。"""
        state = TrackingState(project_name="test", style_anchor="古风")
        llm = MockLLM(
            return_issues=[
                ConsistencyIssue(
                    severity="info",
                    category="style",
                    description="字数偏离目标 2000 字",
                    evidence="实际 1500 字",
                ),
            ]
        )
        verifier = Verifier(llm)
        issues = await verifier.post_write_check(state, "短内容")
        assert Verifier.has_blocking_issues(issues) is False


# === Prompt 设计意图测试 ===


class TestPromptDesign:
    """验证 prompt 包含 critical/warning 判别标准（不依赖真实 LLM）。"""

    def test_pre_prompt_defines_critical_criteria(self) -> None:
        assert "critical" in PRE_WRITE_PROMPT
        assert "角色已被设定为死亡" in PRE_WRITE_PROMPT  # 角色存在性硬伤
        assert "时间线" in PRE_WRITE_PROMPT
        assert "伏笔" in PRE_WRITE_PROMPT
        assert "宁缺毋滥" in PRE_WRITE_PROMPT  # 关键的反过度报警原则

    def test_post_prompt_defines_critical_criteria(self) -> None:
        assert "critical" in POST_WRITE_PROMPT
        assert "宁缺毋滥" in POST_WRITE_PROMPT
        assert "AI 味" in POST_WRITE_PROMPT or "ai_smell" in POST_WRITE_PROMPT

    def test_prompts_have_severity_levels(self) -> None:
        """确保三种 severity 都在 prompt 中明确定义。"""
        for prompt in (PRE_WRITE_PROMPT, POST_WRITE_PROMPT):
            for sev in ("critical", "warning", "info"):
                assert sev in prompt, f"missing {sev} in prompt"

    def test_prompts_distinguish_severity_examples(self) -> None:
        """确保 prompt 区分了"软"和"硬"问题对应的 severity。"""
        for prompt in (PRE_WRITE_PROMPT, POST_WRITE_PROMPT):
            # "warning 适用场景" 应该列出软问题
            assert "warning 适用场景" in prompt or "warning 触发" in prompt
            # "info 适用场景" 应该有
            assert "info 适用场景" in prompt or "info 触发" in prompt


# === _state_to_text 增强 ===


class TestStateToText:
    def test_includes_all_required_sections(self) -> None:
        """state 描述包含项目信息、文风、进度、角色、伏笔、摘要。"""
        state = TrackingState(project_name="测试", style_anchor="古风古韵")
        text = Verifier._state_to_text(state)
        assert "# 项目: 测试" in text
        assert "# 文风: 古风古韵" in text
        assert "# 当前进度: 第 0 章" in text
        assert "# 角色状态" in text
        assert "# 活跃伏笔" in text
        assert "# 最近章节摘要" in text

    def test_includes_foreshadowing_status(self) -> None:
        """伏笔描述包含 status，便于 verifier 判断是否已揭示。"""
        state = TrackingState(project_name="测试")
        state.foreshadowing["fs1"] = ForeshadowingState(
            id="fs1",
            description="玉佩",
            planted_chapter=1,
            status="active",
        )
        state.foreshadowing["fs2"] = ForeshadowingState(
            id="fs2",
            description="身世",
            planted_chapter=5,
            status="revealed",
        )
        text = Verifier._state_to_text(state)
        assert "status=active" in text
        assert "status=revealed" in text

    def test_includes_recent_chapters(self) -> None:
        """最近章节摘要被列出。"""
        state = TrackingState(project_name="test")
        state.recent_chapter_summaries[1] = "第一章摘要"
        state.recent_chapter_summaries[2] = "第二章摘要"
        state.recent_chapter_summaries[3] = "第三章摘要"
        text = Verifier._state_to_text(state)
        assert "第一章摘要" in text
        assert "第三章摘要" in text
