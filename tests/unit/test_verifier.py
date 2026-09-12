"""Verifier 单元测试。"""

from __future__ import annotations

from novel2all.core.memory.tracker import CharacterState, ForeshadowingState, TrackingState
from novel2all.core.memory.verifier import ConsistencyIssue, Verifier


def test_has_blocking_issues_empty() -> None:
    """测试空问题列表。"""
    assert Verifier.has_blocking_issues([]) is False


def test_has_blocking_issues_warning_only() -> None:
    """测试只有 warning 的列表。"""
    issues = [
        ConsistencyIssue(
            severity="warning",
            category="character",
            description="test",
        )
    ]
    assert Verifier.has_blocking_issues(issues) is False


def test_has_blocking_issues_with_critical() -> None:
    """测试有 critical 的列表。"""
    issues = [
        ConsistencyIssue(
            severity="warning",
            category="character",
            description="warning",
        ),
        ConsistencyIssue(
            severity="critical",
            category="timeline",
            description="critical",
        ),
    ]
    assert Verifier.has_blocking_issues(issues) is True


def test_state_to_text_basic() -> None:
    """测试 state 转 text。"""
    state = TrackingState(
        project_name="测试",
        style_anchor="古风古韵",
    )
    state.characters["林雷"] = CharacterState(
        name="林雷",
        location="玉兰城",
        emotional_state="好奇",
    )
    state.foreshadowing["fs_001"] = ForeshadowingState(
        id="fs_001",
        description="戒指",
        planted_chapter=1,
        status="active",
    )
    state.recent_chapter_summaries[3] = "第3章摘要"

    text = Verifier._state_to_text(state)
    assert "# 项目: 测试" in text
    assert "古风古韵" in text
    assert "林雷" in text
    assert "玉兰城" in text
    assert "fs_001" in text
    assert "第3章摘要" in text
