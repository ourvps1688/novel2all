"""自动提取器。

写完一章后，自动用 LLM 提取关键信息（角色变化、伏笔、时间线），
然后 merge 到 TrackingState。

claudecode 的 tracker 是手工维护的，本模块是 novel2all 的关键创新。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from novel2all.core.memory.tracker import (
    CharacterState,
    ForeshadowingState,
    TimelineEvent,
    TrackingState,
)


class CharacterUpdate(BaseModel):
    """一个角色的状态变化。"""

    name: str
    location: str | None = None
    emotional_state: str | None = None
    motivation: str | None = None
    knowledge_added: list[str] = Field(default_factory=list)
    relationships_changed: list[str] = Field(default_factory=list)


class ForeshadowingUpdate(BaseModel):
    """伏笔状态变化。"""

    id: str
    description: str
    planted_chapter: int | None = None
    status: str  # "active" | "advanced" | "revealed" | "abandoned"
    notes: str | None = None


class TimelineEventUpdate(BaseModel):
    """时间线事件。"""

    in_world_time: str
    location: str
    characters: list[str]
    summary: str
    author_only: bool = False


class ContinuityIssue(BaseModel):
    """本章自检发现的连续性问题。"""

    severity: str  # "critical" | "warning" | "info"
    category: str  # "character" | "foreshadowing" | "timeline" | "setting"
    description: str


class ExtractedChapterInfo(BaseModel):
    """LLM 提取的结构化信息（instructor 输出）。"""

    chapter: int
    character_updates: list[CharacterUpdate] = Field(default_factory=list)
    foreshadowing_planted: list[ForeshadowingUpdate] = Field(default_factory=list)
    foreshadowing_changed: list[ForeshadowingUpdate] = Field(default_factory=list)
    timeline_events: list[TimelineEventUpdate] = Field(default_factory=list)
    summary: str = ""  # 200 字内本章摘要
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list)


EXTRACTION_PROMPT = """你是小说连续性审计员。分析本章正文，提取结构化信息。

## 已有状态（参考）
{previous_state}

## 本章正文
{content}

## 任务
返回严格 JSON，包含以下字段：

- `chapter`: 本章编号
- `character_updates`: 角色状态变化列表
  - 每条包含: name, location, emotional_state, motivation, knowledge_added, relationships_changed
- `foreshadowing_planted`: 本章新埋下的伏笔
- `foreshadowing_changed`: 本章状态发生变化的伏笔（推进 / 揭示 / 弃用）
- `timeline_events`: 本章时间线事件
- `summary`: 200 字内本章摘要
- `continuity_issues`: 你发现的任何连续性问题（角色性格漂移、伏笔断裂、时间线冲突、设定矛盾）

注意：
- 只记录本章**确实发生**的变化，不要推测
- continuity_issues 必须严格：critical 表示明确冲突，warning 表示可疑，info 表示建议
- summary 要简洁但保留关键情节转折

只返回 JSON，不要其他文字。
"""


class Extractor:
    """从章节正文中提取结构化信息。"""

    def __init__(self, llm: Any):  # llm: LLMProvider
        self.llm = llm

    async def extract(
        self,
        chapter: int,
        content: str,
        previous_state: TrackingState,
    ) -> ExtractedChapterInfo:
        """提取本章关键信息。"""
        previous_state_dict = self._state_to_prompt_dict(previous_state)
        prompt = EXTRACTION_PROMPT.format(
            previous_state=json.dumps(previous_state_dict, ensure_ascii=False, indent=2),
            content=content,
        )

        # 用 instructor + LLM 做结构化输出
        result = await self.llm.complete_structured(
            prompt=prompt,
            response_model=ExtractedChapterInfo,
        )
        # 确保 chapter 是传入的 chapter（防止 LLM 误判）
        result.chapter = chapter
        return result

    @staticmethod
    def apply_to_state(
        state: TrackingState,
        extracted: ExtractedChapterInfo,
    ) -> TrackingState:
        """把提取结果应用到 state。"""
        # 1. 角色更新
        for char_update in extracted.character_updates:
            existing = state.characters.get(char_update.name)
            new_state = CharacterState(
                name=char_update.name,
                location=char_update.location or (existing.location if existing else None),
                emotional_state=char_update.emotional_state
                or (existing.emotional_state if existing else None),
                motivation=char_update.motivation or (existing.motivation if existing else None),
                knowledge=list(
                    set((existing.knowledge if existing else []) + char_update.knowledge_added)
                ),
                last_updated_chapter=extracted.chapter,
            )
            state.characters[char_update.name] = new_state

        # 2. 新埋伏笔
        for fs in extracted.foreshadowing_planted:
            state.foreshadowing[fs.id] = ForeshadowingState(
                id=fs.id,
                description=fs.description,
                planted_chapter=extracted.chapter,
                status=fs.status,
                notes=fs.notes,
            )

        # 3. 已有伏笔状态变化
        for fs in extracted.foreshadowing_changed:
            existing = state.foreshadowing.get(fs.id)
            if existing:
                existing.status = fs.status
                existing.notes = fs.notes or existing.notes
            else:
                # 之前没记录，但本章揭示了——补建
                state.foreshadowing[fs.id] = ForeshadowingState(
                    id=fs.id,
                    description=fs.description,
                    planted_chapter=extracted.chapter,  # 推测
                    status=fs.status,
                    notes=fs.notes,
                )

        # 4. 时间线事件
        for event in extracted.timeline_events:
            state.timeline.append(
                TimelineEvent(
                    chapter=extracted.chapter,
                    in_world_time=event.in_world_time,
                    location=event.location,
                    characters=event.characters,
                    summary=event.summary,
                    author_only=event.author_only,
                )
            )
        state.timeline.sort(key=lambda e: e.chapter)

        # 5. 最近章节摘要
        state.recent_chapter_summaries[extracted.chapter] = extracted.summary
        state.last_updated_chapter = extracted.chapter

        return state

    @staticmethod
    def _state_to_prompt_dict(state: TrackingState) -> dict:
        """压缩 state 给 prompt 用（避免太长）。"""
        return {
            "project_name": state.project_name,
            "last_chapter": state.last_updated_chapter,
            "characters": {
                name: {
                    "location": c.location,
                    "emotional": c.emotional_state,
                    "motivation": c.motivation,
                }
                for name, c in state.characters.items()
            },
            "active_foreshadowing": [
                {"id": fs.id, "description": fs.description, "planted": fs.planted_chapter}
                for fs in state.foreshadowing.values()
                if fs.status == "active"
            ],
            "recent_summaries": dict(list(state.recent_chapter_summaries.items())[-5:]),
        }
