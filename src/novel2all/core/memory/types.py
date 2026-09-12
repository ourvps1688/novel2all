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


# === L5 知识图谱（V0.22）===


class NodeType(str, Enum):
    """知识图谱节点类型。"""

    CHARACTER = "Character"
    LOCATION = "Location"
    FORESHADOWING = "Foreshadowing"
    EVENT = "Event"
    ITEM = "Item"


class EdgeType(str, Enum):
    """知识图谱边类型。"""

    APPEARS_IN = "appears_in"  # Character → Event
    LOCATED_IN = "located_in"  # Character → Location
    OWNS = "owns"  # Character → Item
    RELATED_TO = "related_to"  # Character → Character
    FORESHADOWS = "foreshadows"  # Foreshadowing → Event
    CAUSED_BY = "caused_by"  # Event → Event
    SET_IN = "set_in"  # Event → Location


class GraphNode(BaseModel):
    """知识图谱节点。

    ID 格式:
      - Character: "char:林雷"
      - Location: "loc:苍茫镇"
      - Foreshadowing: "fs:bloodline_secret"
      - Event: "event:awakening_ch2"
      - Item: "item:玉佩"
    """

    id: str
    type: NodeType
    name: str
    # Character 字段
    alive: bool | None = None  # 仅 Character
    # Location 字段
    type_detail: str | None = None  # 仅 Location (city/sect/wild/...)
    # Foreshadowing 字段
    id_short: str | None = None  # 仅 Foreshadowing
    status: str | None = None  # 仅 Foreshadowing (active/advanced/revealed)
    # Event 字段
    in_world_time: str | None = None
    # 通用：起止章节
    first_chapter: int | None = None
    last_chapter: int | None = None

    def short_id(self) -> str:
        """返回去掉前缀的短 ID（仅用于显示）。"""
        if ":" in self.id:
            return self.id.split(":", 1)[1]
        return self.id


class GraphEdge(BaseModel):
    """知识图谱边。"""

    from_id: str  # 节点 id
    to_id: str  # 节点 id
    type: EdgeType
    label: str | None = None  # 仅 related_to 需要（如"兄弟"）
    chapter: int | None = None  # 边产生章节（用于时间线）


class GraphData(BaseModel):
    """图谱数据集合，嵌入 TrackingState.graph 字段。"""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def node_index(self) -> dict[str, GraphNode]:
        """返回 {id: node} 索引。"""
        return {n.id: n for n in self.nodes}

    def edge_index(self) -> dict[tuple[str, str, str], GraphEdge]:
        """返回 {(from_id, to_id, type): edge} 索引。"""
        return {(e.from_id, e.to_id, e.type.value): e for e in self.edges}
