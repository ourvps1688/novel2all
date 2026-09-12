"""Tracker 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novel2all.core.memory.tracker import (
    CharacterState,
    ForeshadowingState,
    TimelineEvent,
    Tracker,
)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """创建临时项目目录。"""
    (tmp_path / "设定").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    return tmp_path


def test_init(tmp_project: Path) -> None:
    """测试初始化。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    state = tracker.init(
        project_name="测试小说",
        genre="玄幻",
        style_anchor="古风古韵",
        total_chapters_target=400,
        total_word_count_target=2_000_000,
    )

    assert state.project_name == "测试小说"
    assert state.genre == "玄幻"
    assert state.style_anchor == "古风古韵"
    assert state.total_chapters_target == 400
    assert state.total_word_count_target == 2_000_000
    assert (tmp_project / "_tracking-state.json").exists()


def test_read(tmp_project: Path) -> None:
    """测试读取。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    tracker.init(project_name="测试")
    state = tracker.read()

    assert state.project_name == "测试"


def test_read_nonexistent(tmp_project: Path) -> None:
    """测试读取不存在的文件。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    with pytest.raises(FileNotFoundError):
        tracker.read()


def test_exists(tmp_project: Path) -> None:
    """测试 exists。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    assert not tracker.exists()
    tracker.init(project_name="测试")
    assert tracker.exists()


def test_merge_character(tmp_project: Path) -> None:
    """测试 merge 角色。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    state = tracker.init(project_name="测试")

    state = tracker.merge(
        state,
        character_updates={
            "林雷": CharacterState(
                name="林雷",
                location="玉兰城",
                emotional_state="好奇",
                motivation="成为强者",
            ),
        },
    )
    assert "林雷" in state.characters
    assert state.characters["林雷"].location == "玉兰城"

    # 第二次 merge（部分字段更新）
    state = tracker.merge(
        state,
        character_updates={
            "林雷": CharacterState(
                name="林雷",
                emotional_state="紧张",
                knowledge=["遇到霍格"],
            ),
        },
    )
    # 保留未更新的字段
    assert state.characters["林雷"].location == "玉兰城"
    # 更新已有字段
    assert state.characters["林雷"].emotional_state == "紧张"
    # 合并列表
    assert "遇到霍格" in state.characters["林雷"].knowledge


def test_merge_foreshadowing(tmp_project: Path) -> None:
    """测试 merge 伏笔。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    state = tracker.init(project_name="测试")

    state = tracker.merge(
        state,
        foreshadowing_updates={
            "fs_001": ForeshadowingState(
                id="fs_001",
                description="神秘戒指",
                planted_chapter=1,
                status="active",
            ),
        },
    )
    assert "fs_001" in state.foreshadowing
    assert state.foreshadowing["fs_001"].status == "active"


def test_merge_timeline(tmp_project: Path) -> None:
    """测试 merge 时间线。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    state = tracker.init(project_name="测试")

    state = tracker.merge(
        state,
        new_timeline_events=[
            TimelineEvent(
                chapter=1,
                in_world_time="景和三年 春",
                location="玉兰城",
                characters=["林雷"],
                summary="林雷离家",
            ),
        ],
    )
    assert len(state.timeline) == 1
    assert state.timeline[0].chapter == 1


def test_merge_recent_summary(tmp_project: Path) -> None:
    """测试 merge 最近章节摘要。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    state = tracker.init(project_name="测试")

    state = tracker.merge(
        state,
        new_chapter_summary=(5, "林雷与霍格相遇"),
    )
    assert state.recent_chapter_summaries[5] == "林雷与霍格相遇"
    assert state.last_updated_chapter == 5


def test_get_active_foreshadowing(tmp_project: Path) -> None:
    """测试查询活跃伏笔。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    tracker.init(project_name="测试")

    tracker.merge(
        tracker.read(),
        foreshadowing_updates={
            "fs_001": ForeshadowingState(
                id="fs_001", description="active", planted_chapter=1, status="active"
            ),
            "fs_002": ForeshadowingState(
                id="fs_002", description="revealed", planted_chapter=1, status="revealed"
            ),
        },
    )

    active = tracker.get_active_foreshadowing()
    assert len(active) == 1
    assert active[0].id == "fs_001"


def test_get_recent_summaries(tmp_project: Path) -> None:
    """测试查询最近摘要。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    state = tracker.init(project_name="测试")

    for ch in [1, 2, 3, 4, 5]:
        state = tracker.merge(state, new_chapter_summary=(ch, f"第{ch}章摘要"))

    recent = tracker.get_recent_summaries(n=3)
    assert len(recent) == 3
    # 按时间倒序
    assert recent[0][0] == 5
    assert recent[1][0] == 4
    assert recent[2][0] == 3
