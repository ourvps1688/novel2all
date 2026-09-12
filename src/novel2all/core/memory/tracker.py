"""_tracking-state.json 引擎。

从 claudecode 0.7.10 fork 并扩展：
- 原版：手工维护
- novel2all：自动 merge（来自 Extractor 的输出）
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class CharacterState(BaseModel):
    """角色当前快照。"""

    name: str
    location: str | None = None
    emotional_state: str | None = None
    motivation: str | None = None
    knowledge: list[str] = Field(default_factory=list)
    last_updated_chapter: int | None = None


class ForeshadowingState(BaseModel):
    """伏笔状态。"""

    id: str
    description: str
    planted_chapter: int
    status: str = "active"  # "active" | "advanced" | "revealed" | "abandoned"
    expected_reveal_chapter: int | None = None
    notes: str | None = None


class TimelineEvent(BaseModel):
    """时间线事件。"""

    chapter: int
    in_world_time: str  # 例如"景和三年 春"
    location: str
    characters: list[str]
    summary: str
    author_only: bool = False  # True 表示读者尚未知道的真相


class TrackingState(BaseModel):
    """项目跟踪状态：单文件 _tracking-state.json 的完整 schema。"""

    schema_version: int = 2
    project_name: str
    genre: str | None = None
    style_anchor: str | None = None  # 文风锚点（如"古风古韵"）
    total_chapters_target: int | None = None
    total_word_count_target: int | None = None

    characters: dict[str, CharacterState] = Field(default_factory=dict)
    foreshadowing: dict[str, ForeshadowingState] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)

    # L5 知识图谱（V0.22+）
    graph: dict = Field(
        default_factory=lambda: {"nodes": [], "edges": []}
    )  # 用 dict 避免循环依赖，graph.py 的 MemoryGraph.to_dict() 直接兼容

    # 最近章节摘要（用于 L3 滑动窗口）
    recent_chapter_summaries: dict[int, str] = Field(default_factory=dict)

    last_updated_chapter: int = 0
    last_updated_at: datetime | None = None


class Tracker:
    """读写 _tracking-state.json 的引擎。

    用法：
        tracker = Tracker(project_root / "_tracking-state.json")
        state = tracker.read()
        state.characters["林雷"] = CharacterState(name="林雷", ...)
        tracker.write(state)
    """

    def __init__(self, state_file: Path):
        self.state_file = state_file

    def exists(self) -> bool:
        return self.state_file.exists()

    def read(self) -> TrackingState:
        """读取状态。文件不存在时返回默认状态。"""
        if not self.exists():
            raise FileNotFoundError(
                f"Tracking state not found: {self.state_file}. Run `novel2all setup` first."
            )
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        return TrackingState.model_validate(data)

    def write(self, state: TrackingState) -> None:
        """写回状态。"""
        state.last_updated_at = datetime.now(tz=UTC)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            state.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def init(
        self,
        project_name: str,
        genre: str | None = None,
        style_anchor: str | None = None,
        total_chapters_target: int | None = None,
        total_word_count_target: int | None = None,
    ) -> TrackingState:
        """初始化新项目状态。"""
        state = TrackingState(
            project_name=project_name,
            genre=genre,
            style_anchor=style_anchor,
            total_chapters_target=total_chapters_target,
            total_word_count_target=total_word_count_target,
        )
        self.write(state)
        return state

    def merge(
        self,
        state: TrackingState,
        *,
        character_updates: dict[str, CharacterState] | None = None,
        foreshadowing_updates: dict[str, ForeshadowingState] | None = None,
        new_timeline_events: list[TimelineEvent] | None = None,
        new_chapter_summary: tuple[int, str] | None = None,
    ) -> TrackingState:
        """merge 增量更新到状态。"""
        if character_updates:
            for name, char in character_updates.items():
                existing = state.characters.get(name)
                if existing:
                    # merge 字段（保留未更新的字段）
                    merged = existing.model_copy(update=char.model_dump(exclude_unset=True))
                    state.characters[name] = merged
                else:
                    state.characters[name] = char

        if foreshadowing_updates:
            for fid, fs in foreshadowing_updates.items():
                state.foreshadowing[fid] = fs

        if new_timeline_events:
            # 去重 + 追加
            existing_chapters = {(e.chapter, e.summary) for e in state.timeline}
            for event in new_timeline_events:
                if (event.chapter, event.summary) not in existing_chapters:
                    state.timeline.append(event)
            state.timeline.sort(key=lambda e: e.chapter)

        if new_chapter_summary:
            chapter_num, summary = new_chapter_summary
            state.recent_chapter_summaries[chapter_num] = summary
            state.last_updated_chapter = chapter_num

        # 写回文件
        self.write(state)

        return state

    # === 查询辅助 ===

    def get_character(self, name: str) -> CharacterState | None:
        return self.read().characters.get(name)

    def get_active_foreshadowing(self) -> list[ForeshadowingState]:
        return [fs for fs in self.read().foreshadowing.values() if fs.status == "active"]

    def get_recent_summaries(self, n: int = 5) -> list[tuple[int, str]]:
        state = self.read()
        sorted_chapters = sorted(state.recent_chapter_summaries.keys(), reverse=True)
        return [(ch, state.recent_chapter_summaries[ch]) for ch in sorted_chapters[:n]]
