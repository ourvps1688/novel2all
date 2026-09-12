"""Extractor 单元测试。"""

from __future__ import annotations

from novel2all.core.memory.extractor import (
    CharacterUpdate,
    ExtractedChapterInfo,
    Extractor,
    ForeshadowingUpdate,
    TimelineEventUpdate,
)
from novel2all.core.memory.tracker import TrackingState


def test_apply_to_state_empty() -> None:
    """测试应用到空 state。"""
    state = TrackingState(project_name="测试")
    extracted = ExtractedChapterInfo(
        chapter=5,
        summary="测试摘要",
    )
    Extractor.apply_to_state(state, extracted)
    assert state.last_updated_chapter == 5
    assert state.recent_chapter_summaries[5] == "测试摘要"


def test_apply_to_state_with_characters() -> None:
    """测试应用到带角色的 state。"""
    state = TrackingState(project_name="测试")
    extracted = ExtractedChapterInfo(
        chapter=5,
        character_updates=[
            CharacterUpdate(
                name="林雷",
                location="玉兰城",
                emotional_state="好奇",
                motivation="变强",
                knowledge_added=["遇到霍格"],
            )
        ],
        summary="林雷与霍格相遇",
    )
    Extractor.apply_to_state(state, extracted)

    assert "林雷" in state.characters
    assert state.characters["林雷"].location == "玉兰城"
    assert state.characters["林雷"].emotional_state == "好奇"
    assert "遇到霍格" in state.characters["林雷"].knowledge


def test_apply_to_state_with_foreshadowing() -> None:
    """测试应用到带伏笔的 state。"""
    state = TrackingState(project_name="测试")
    extracted = ExtractedChapterInfo(
        chapter=1,
        foreshadowing_planted=[
            ForeshadowingUpdate(
                id="fs_001",
                description="神秘戒指",
                status="active",
            )
        ],
    )
    Extractor.apply_to_state(state, extracted)

    assert "fs_001" in state.foreshadowing
    assert state.foreshadowing["fs_001"].planted_chapter == 1


def test_apply_to_state_with_timeline() -> None:
    """测试时间线事件。"""
    state = TrackingState(project_name="测试")
    extracted = ExtractedChapterInfo(
        chapter=1,
        timeline_events=[
            TimelineEventUpdate(
                in_world_time="景和三年 春",
                location="玉兰城",
                characters=["林雷"],
                summary="林雷离家",
            )
        ],
    )
    Extractor.apply_to_state(state, extracted)

    assert len(state.timeline) == 1
    assert state.timeline[0].chapter == 1
    assert state.timeline[0].location == "玉兰城"


def test_state_to_prompt_dict() -> None:
    """测试 state 转 prompt dict。"""
    from novel2all.core.memory.tracker import CharacterState, ForeshadowingState

    state = TrackingState(project_name="测试")
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
    state.recent_chapter_summaries[3] = "第 3 章摘要"

    prompt_dict = Extractor._state_to_prompt_dict(state)
    assert prompt_dict["project_name"] == "测试"
    assert "林雷" in prompt_dict["characters"]
    assert len(prompt_dict["active_foreshadowing"]) == 1
    assert prompt_dict["active_foreshadowing"][0]["id"] == "fs_001"
