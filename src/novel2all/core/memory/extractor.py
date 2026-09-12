"""自动提取器。

写完一章后，自动用 LLM 提取关键信息（角色变化、伏笔、时间线、L5 知识图谱节点/边），
然后 merge 到 TrackingState。

claudecode 的 tracker 是手工维护的，本模块是 novel2all 的关键创新。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from novel2all.core.memory.graph import MemoryGraph
from novel2all.core.memory.tracker import (
    CharacterState,
    ForeshadowingState,
    TimelineEvent,
    TrackingState,
)
from novel2all.core.memory.types import EdgeType, NodeType


class ContinuityIssue(BaseModel):
    """本章自检发现的连续性问题。

    本地定义避免循环 import（verifier.py 也有同名类，5 字段版本）。
    字段保持与 verifier.py 一致：severity / category / description（必填非空）。
    """

    severity: str  # "critical" | "warning" | "info"
    category: str  # "character" | "foreshadowing" | "timeline" | "setting" | "style" | "ai_smell"
    description: str




# === V0.22 L5 知识图谱增量提取 ===

# 允许的节点类型（用于 LLM prompt 约束）
_GRAPH_NODE_TYPES = [t.value for t in NodeType]
_GRAPH_EDGE_TYPES = [t.value for t in EdgeType]



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




class GraphNodeUpdate(BaseModel):
    """从章节提取的图谱节点。"""

    id: str  # 例如 "char:林雷" / "loc:苍茫镇" / "fs:bloodline_secret" / "event:awakening" / "item:玉佩"
    type: str  # 必须是 _GRAPH_NODE_TYPES 之一
    name: str
    alive: bool | None = None  # Character 专用
    type_detail: str | None = None  # Location 专用
    id_short: str | None = None  # Foreshadowing 专用
    status: str | None = None  # Foreshadowing 专用 (active/advanced/revealed/abandoned)
    in_world_time: str | None = None  # Event 专用

    def validate_type(self) -> str | None:
        """验证 type 字段，返回错误信息或 None。"""
        if self.type not in _GRAPH_NODE_TYPES:
            return f"Invalid node type '{self.type}', expected one of {_GRAPH_NODE_TYPES}"
        return None


class GraphEdgeUpdate(BaseModel):
    """从章节提取的图谱边。"""

    from_id: str
    to_id: str
    type: str  # 必须是 _GRAPH_EDGE_TYPES 之一
    label: str | None = None  # related_to 专用（如"兄弟"）

    def validate_type(self) -> str | None:
        if self.type not in _GRAPH_EDGE_TYPES:
            return f"Invalid edge type '{self.type}', expected one of {_GRAPH_EDGE_TYPES}"
        return None


class ExtractedGraphData(BaseModel):
    """从一章提取的图谱节点和边。"""

    nodes: list[GraphNodeUpdate] = Field(default_factory=list)
    edges: list[GraphEdgeUpdate] = Field(default_factory=list)

    def to_memory_graph(self) -> MemoryGraph:
        """转换为 MemoryGraph 实例（id / type 校验失败会跳过）。"""
        g = MemoryGraph()
        for n in self.nodes:
            if n.validate_type():
                continue  # 跳过非法 type
            try:
                from novel2all.core.memory.types import GraphNode

                g.add_node(
                    GraphNode(
                        id=n.id,
                        type=NodeType(n.type),
                        name=n.name,
                        alive=n.alive,
                        type_detail=n.type_detail,
                        id_short=n.id_short,
                        status=n.status,
                        in_world_time=n.in_world_time,
                    )
                )
            except (ValueError, Exception):
                continue  # skip invalid node
        for e in self.edges:
            if e.validate_type():
                continue
            try:
                from novel2all.core.memory.types import GraphEdge

                g.add_edge(
                    GraphEdge(
                        from_id=e.from_id,
                        to_id=e.to_id,
                        type=EdgeType(e.type),
                        label=e.label,
                    )
                )
            except (ValueError, Exception):
                continue  # skip invalid edge
        return g


class ExtractedChapterInfo(BaseModel):
    """LLM 提取的结构化信息（instructor 输出）。"""

    chapter: int
    character_updates: list[CharacterUpdate] = Field(default_factory=list)
    foreshadowing_planted: list[ForeshadowingUpdate] = Field(default_factory=list)
    foreshadowing_changed: list[ForeshadowingUpdate] = Field(default_factory=list)
    timeline_events: list[TimelineEventUpdate] = Field(default_factory=list)
    summary: str = ""  # 200 字内本章摘要
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list)
    # V0.22 L5 知识图谱增量
    graph: ExtractedGraphData = Field(default_factory=ExtractedGraphData)


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
- `graph`: 本章新出现 / 发生变化的图谱节点和边：
  - `nodes`: 节点列表（id 必须以 "char:" / "loc:" / "fs:" / "event:" / "item:" 前缀开头）
    - 每条: id, type (Character/Location/Foreshadowing/Event/Item), name
    - Character 节点: alive (true/false/null)
    - Location 节点: type_detail (city/sect/wild/...)
    - Foreshadowing 节点: id_short, status (active/advanced/revealed/abandoned)
    - Event 节点: in_world_time
  - `edges`: 边列表
    - 每条: from_id, to_id, type
    - type 可选值: appears_in / located_in / owns / related_to / foreshadows / caused_by / set_in
    - related_to 边的 from/to 之间需要"label"标注关系（如"兄弟"）

注意：
- 只记录本章**确实出现或发生关系变化**的节点和边，不要推测已存在但本章无变化的
- id 格式: "类型:名称"，例: "char:林雷"、"loc:苍茫镇"、"fs:身世之谜"、"event:觉醒时刻"
- 已有节点不要重复（参考"已有状态"里的 graph 字段）
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
        """提取本章关键信息（含 L5 图谱增量）。"""
        previous_state_dict = self._state_to_prompt_dict(previous_state)
        prompt = EXTRACTION_PROMPT.format(
            previous_state=json.dumps(previous_state_dict, ensure_ascii=False, indent=2),
            content=content,
        )

        # 用 instructor + LLM 做结构化输出
        try:
            result = await self.llm.complete_structured(
                prompt=prompt,
                response_model=ExtractedChapterInfo,
            )
        except Exception as e:
            # 失败兜底：返回空结果（不阻断主流程）
            # 用 dict 构造避免循环 import / 类名引用
            return ExtractedChapterInfo.model_validate(
                {
                    "chapter": chapter,
                    "continuity_issues": [
                        {
                            "severity": "warning",
                            "category": "setting",
                            "description": f"LLM extraction failed: {e}",
                        }
                    ],
                }
            )

        # 确保 chapter 是传入的 chapter（防止 LLM 误判）
        result.chapter = chapter
        return result

    @staticmethod
    def apply_to_state(
        state: TrackingState,
        extracted: ExtractedChapterInfo,
    ) -> TrackingState:
        """把提取结果应用到 state（含 L5 图谱 merge）。"""
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

        # 6. V0.22 L5 知识图谱增量
        if extracted.graph.nodes or extracted.graph.edges:
            # MemoryGraph.merge_chapter 会自动扩展 first/last_chapter
            graph = MemoryGraph.from_dict(state.graph)
            graph.merge_chapter(
                extracted.chapter,
                [
                    n
                    for n in [
                        # type: ignore[arg-type]
                        _node_update_to_graph_node(n, extracted.chapter)
                        for n in extracted.graph.nodes
                    ]
                    if n is not None
                ],
                [
                    e
                    for e in [
                        # type: ignore[arg-type]
                        _edge_update_to_graph_edge(edge, extracted.chapter)
                        for edge in extracted.graph.edges
                    ]
                    if e is not None
                ],
            )
            state.graph = graph.to_dict()

        return state

    @staticmethod
    def _state_to_prompt_dict(state: TrackingState) -> dict:
        """压缩 state 给 prompt 用（避免太长）。"""
        result = {
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
            # V0.22 L5 知识图谱概要（避免 prompt 过长）
            "graph": _graph_summary_for_prompt(state.graph),
        }
        return result


# === V0.22 helper：GraphNodeUpdate / EdgeUpdate → GraphNode / GraphEdge ===


def _node_update_to_graph_node(
    update: GraphNodeUpdate, chapter: int
):  # type: ignore[valid-type]
    """从 GraphNodeUpdate 转换到 GraphNode（带验证）。"""
    from novel2all.core.memory.types import GraphNode

    if update.type not in _GRAPH_NODE_TYPES:
        return None
    try:
        return GraphNode(
            id=update.id,
            type=NodeType(update.type),
            name=update.name,
            alive=update.alive,
            type_detail=update.type_detail,
            id_short=update.id_short,
            status=update.status,
            in_world_time=update.in_world_time,
            first_chapter=chapter,
            last_chapter=chapter,
        )
    except (ValueError, Exception):
        return None


def _edge_update_to_graph_edge(
    update: GraphEdgeUpdate, chapter: int
):  # type: ignore[valid-type]
    """从 GraphEdgeUpdate 转换到 GraphEdge（带验证）。"""
    from novel2all.core.memory.types import GraphEdge

    if update.type not in _GRAPH_EDGE_TYPES:
        return None
    try:
        return GraphEdge(
            from_id=update.from_id,
            to_id=update.to_id,
            type=EdgeType(update.type),
            label=update.label,
            chapter=chapter,
        )
    except (ValueError, Exception):
        return None


def _graph_summary_for_prompt(graph_dict: dict) -> dict:
    """压缩 graph 字段给 prompt（避免过长）。"""
    nodes = graph_dict.get("nodes", [])
    edges = graph_dict.get("edges", [])

    def _node_brief(n: dict) -> str:
        # 简化节点描述
        ntype = n.get("type", "Unknown")
        name = n.get("name", n.get("id", "?"))
        extra = ""
        if ntype == "Character" and n.get("alive") is False:
            extra = " (已死)"
        elif ntype == "Foreshadowing":
            extra = f" [{n.get('status', '?')}]"
        return f"- {n.get('id', '?')} ({ntype}): {name}{extra}"

    def _edge_brief(e: dict) -> str:
        label = f' "{e.get("label")}"' if e.get("label") else ""
        return f"- {e.get('from_id')} --{e.get('type')}--> {e.get('to_id')}{label}"

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_brief": [_node_brief(n) for n in nodes[:30]],  # 截断到 30 个
        "edge_brief": [_edge_brief(e) for e in edges[:50]],  # 截断到 50 个
    }

