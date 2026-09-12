"""memory 类型定义。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MemoryLayer(str, Enum):
    """5 层记忆层级。"""

    CORE = "core"  # 永远加载：核心设定 / 文风基线
    CHARACTER = "character"  # 按需加载：本章涉及的角色状态
    RECENT = "recent"  # 滑动窗口：最近 N 章摘要
    EVENT = "event"  # 向量检索：相关历史事件
    GRAPH = "graph"  # 知识图谱：tool call 按需查询


class MemoryItem(BaseModel):
    """一条记忆。"""

    content: str
    source: str  # 文件路径或检索来源
    layer: MemoryLayer
    relevance: float = 1.0  # 0-1，检索召回的相关性
    token_count: int = 0
    timestamp: datetime | None = None


class MemoryContext(BaseModel):
    """一次写作任务加载的完整 memory。"""

    core: list[MemoryItem] = Field(default_factory=list)
    character: list[MemoryItem] = Field(default_factory=list)
    recent: list[MemoryItem] = Field(default_factory=list)
    events: list[MemoryItem] = Field(default_factory=list)
    graph: list[MemoryItem] = Field(default_factory=list)

    def iter_all(self) -> Iterator[MemoryItem]:
        yield from self.core
        yield from self.character
        yield from self.recent
        yield from self.events
        yield from self.graph

    @property
    def total_tokens(self) -> int:
        return sum(item.token_count for item in self.iter_all())

    def to_system_sections(self) -> list[str]:
        """组装成 LLM system message 段落。"""
        sections: list[str] = []
        if self.core:
            sections.append("# 核心设定\n" + "\n\n".join(i.content for i in self.core))
        if self.character:
            sections.append("# 角色状态\n" + "\n\n".join(i.content for i in self.character))
        if self.recent:
            sections.append("# 最近章节\n" + "\n\n".join(i.content for i in self.recent))
        if self.events:
            sections.append("# 相关历史事件\n" + "\n\n".join(i.content for i in self.events))
        if self.graph:
            sections.append("# 知识图谱片段\n" + "\n\n".join(i.content for i in self.graph))
        return sections


class MemoryConfig(BaseModel):
    """memory 加载策略。"""

    core_token_budget: int = 3000
    character_token_budget: int = 4000
    recent_chapter_count: int = 5
    recent_token_budget: int = 6000
    event_top_k: int = 8
    event_token_budget: int = 5000
    auto_extract_after_write: bool = True
    auto_embed_after_write: bool = True
    pre_write_check_blocking: bool = True
