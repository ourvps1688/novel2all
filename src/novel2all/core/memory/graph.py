"""L5 知识图谱：结构化关系网。

V0.22 新增。解决"角色关系模糊"和"伏笔因果链"问题。

设计原则：
- 节点/边用 Pydantic 严格类型
- 嵌入 TrackingState.graph 字段（JSON 兼容）
- 暴露 NetworkX 内部表示（用于高级算法）
- 三层降级：NetworkX 不可用 → 纯 Python dict 兜底
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from novel2all.core.memory.types import (
    EdgeType,
    GraphData,
    GraphEdge,
    GraphNode,
)


class GraphError(Exception):
    """图谱操作错误。"""


class MemoryGraph:
    """知识图谱核心类。

    用法：
        graph = MemoryGraph()
        graph.add_node(GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷"))
        graph.add_edge(GraphEdge(from_id="char:林雷", to_id="char:苏寒",
                                    type=EdgeType.RELATED_TO, label="兄弟"))
        for edge in graph.get_neighbors("char:林雷"):
            print(edge)
    """

    def __init__(self, data: GraphData | dict | None = None) -> None:
        """从 GraphData / dict / None 构造。"""
        if data is None:
            self._data = GraphData()
        elif isinstance(data, GraphData):
            self._data = data
        elif isinstance(data, dict):
            self._data = GraphData.model_validate(data)
        else:
            raise GraphError(f"Unsupported data type: {type(data)}")

        # 尝试加载 NetworkX（不可用时降级）
        self._nx: Any | None = None
        try:
            import networkx as nx

            self._nx = nx
            # 用无向图（小说人物关系无方向性：林雷-苏寒 兄弟不分方向）
            self._nx_graph: Any | None = nx.Graph()
            self._sync_nx_from_data()
        except ImportError:
            # NetworkX 不可用，禁用 nx_* 系列方法
            self._nx_graph = None

    # === 核心 CRUD ===

    def add_node(self, node: GraphNode) -> None:
        """添加节点（id 重复则更新字段）。"""
        existing = self._data.node_index().get(node.id)
        if existing:
            # 更新字段（保留未指定的字段）
            merged = existing.model_copy(update=node.model_dump(exclude_unset=True))
            self._data.nodes = [merged if n.id == node.id else n for n in self._data.nodes]
        else:
            self._data.nodes.append(node)

        if self._nx_graph is not None:
            self._nx_graph.add_node(
                node.id,
                type=node.type.value,
                name=node.name,
                data=node.model_dump(),
            )

    def add_edge(self, edge: GraphEdge) -> None:
        """添加边（from_id / to_id / type 三元组重复则更新 label/chapter）。"""
        key = (edge.from_id, edge.to_id, edge.type.value)
        existing = self._data.edge_index().get(key)
        if existing:
            merged = existing.model_copy(update=edge.model_dump(exclude_unset=True))
            self._data.edges = [
                merged if (e.from_id, e.to_id, e.type.value) == key else e for e in self._data.edges
            ]
        else:
            self._data.edges.append(edge)

        if self._nx_graph is not None:
            self._nx_graph.add_edge(
                edge.from_id,
                edge.to_id,
                type=edge.type.value,
                label=edge.label,
                chapter=edge.chapter,
            )

    def remove_node(self, node_id: str) -> bool:
        """删除节点及关联边。返回是否实际删除。"""
        before_nodes = len(self._data.nodes)
        before_edges = len(self._data.edges)
        self._data.nodes = [n for n in self._data.nodes if n.id != node_id]
        self._data.edges = [
            e for e in self._data.edges if e.from_id != node_id and e.to_id != node_id
        ]
        if self._nx_graph is not None and node_id in self._nx_graph:
            self._nx_graph.remove_node(node_id)
        return len(self._data.nodes) < before_nodes or len(self._data.edges) < before_edges

    def get_node(self, node_id: str) -> GraphNode | None:
        """获取节点。"""
        return self._data.node_index().get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._data.node_index()

    # === 查询 ===

    def get_neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[GraphEdge]:
        """获取节点的所有邻居边（双向：from_id 或 to_id == node_id）。"""
        results = []
        for e in self._data.edges:
            if (e.from_id == node_id or e.to_id == node_id) and (
                edge_type is None or e.type == edge_type
            ):
                results.append(e)
        return results

    def get_edges_between(self, from_id: str, to_id: str) -> list[GraphEdge]:
        """获取两个节点之间的所有边（任意方向、任意 type）。"""
        return [
            e
            for e in self._data.edges
            if (e.from_id == from_id and e.to_id == to_id)
            or (e.from_id == to_id and e.to_id == from_id)
        ]

    def get_path(self, from_id: str, to_id: str, max_hops: int = 3) -> list[GraphEdge] | None:
        """BFS 查找两节点间最短路径（最多 max_hops 跳）。

        Returns: 边列表 [e1, e2, ...]，或 None（不可达）。
        """
        if from_id == to_id:
            return []
        if not self.has_node(from_id) or not self.has_node(to_id):
            return None

        # 邻接表
        adj: dict[str, list[GraphEdge]] = defaultdict(list)
        for e in self._data.edges:
            adj[e.from_id].append(e)
            adj[e.to_id].append(e)  # 无向图视角

        # BFS
        from collections import deque

        queue = deque([(from_id, [])])  # (current_node, path_edges)
        visited = {from_id}
        while queue:
            cur, path = queue.popleft()
            if cur == to_id:
                return path
            if len(path) >= max_hops:
                continue
            for e in adj[cur]:
                # 边连接的"另一端"
                next_node = e.to_id if e.from_id == cur else e.from_id
                if next_node in visited:
                    continue
                new_path = path + [e]
                if next_node == to_id:
                    return new_path
                visited.add(next_node)
                queue.append((next_node, new_path))
        return None

    def query_subgraph(
        self, center: str, hops: int = 2, edge_type: EdgeType | None = None
    ) -> dict[str, Any]:
        """BFS 查询子图（中心节点 + N 跳内的所有节点和边）。"""
        if not self.has_node(center):
            return {"nodes": [], "edges": []}

        from collections import deque

        queue = deque([(center, 0)])
        visited = {center}
        sub_nodes: list[GraphNode] = [self.get_node(center)]  # type: ignore[arg-type]
        sub_edges: list[GraphEdge] = []

        adj: dict[str, list[GraphEdge]] = defaultdict(list)
        for e in self._data.edges:
            adj[e.from_id].append(e)
            adj[e.to_id].append(e)

        while queue:
            cur, depth = queue.popleft()
            if depth >= hops:
                continue
            for e in adj[cur]:
                if edge_type is not None and e.type != edge_type:
                    continue
                next_node = e.to_id if e.from_id == cur else e.from_id
                if next_node not in visited:
                    visited.add(next_node)
                    n = self.get_node(next_node)
                    if n:
                        sub_nodes.append(n)
                    sub_edges.append(e)
                    queue.append((next_node, depth + 1))

        return {
            "nodes": [n.model_dump() for n in sub_nodes],
            "edges": [e.model_dump() for e in sub_edges],
        }

    def iter_nodes(self) -> Iterator[GraphNode]:
        yield from self._data.nodes

    def iter_edges(self) -> Iterator[GraphEdge]:
        yield from self._data.edges

    def count(self) -> tuple[int, int]:
        """返回 (节点数, 边数)。"""
        return len(self._data.nodes), len(self._data.edges)

    # === 增量合并 ===

    def merge_chapter(
        self,
        chapter: int,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """合并一章新增的节点/边。

        节点：upsert（id 重复更新字段；first_chapter 取 existing+new+chapter 三者最小，
              last_chapter 取三者最大）。
        边：upsert（from/to/type 三元组重复更新 label/chapter，chapter 取 max）。
        """
        for node in nodes:
            existing = self.get_node(node.id)
            if existing:
                # first_chapter = min(existing, node, chapter)（存在的最小）
                firsts = [
                    c
                    for c in (existing.first_chapter, node.first_chapter, chapter)
                    if c is not None
                ]
                if firsts:
                    node.first_chapter = min(firsts)
                # last_chapter = max(existing, node, chapter)（存在的最大）
                lasts = [
                    c for c in (existing.last_chapter, node.last_chapter, chapter) if c is not None
                ]
                if lasts:
                    node.last_chapter = max(lasts)
            else:
                # 全新节点
                if node.first_chapter is None:
                    node.first_chapter = chapter
                if node.last_chapter is None:
                    node.last_chapter = chapter
            self.add_node(node)

        for edge in edges:
            existing_key = (edge.from_id, edge.to_id, edge.type.value)
            existing = self._data.edge_index().get(existing_key)
            if existing and existing.chapter is not None:
                # 取 max
                edge.chapter = max(
                    c for c in (edge.chapter, existing.chapter, chapter) if c is not None
                )
            elif edge.chapter is None:
                edge.chapter = chapter
            self.add_edge(edge)

    # === 序列化 ===

    def to_dict(self) -> dict[str, Any]:
        """导出 dict（兼容 TrackingState.graph 字段）。"""
        return {
            "nodes": [n.model_dump() for n in self._data.nodes],
            "edges": [e.model_dump() for e in self._data.edges],
        }

    def to_json(self) -> str:
        """导出 JSON 字符串。"""
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryGraph:
        """从 dict 构造。"""
        return cls(data)

    @classmethod
    def from_json(cls, json_str: str) -> MemoryGraph:
        """从 JSON 字符串构造。"""
        import json

        return cls(json.loads(json_str))

    # === NetworkX 高级查询 ===

    def has_nx(self) -> bool:
        """NetworkX 是否可用。"""
        return self._nx_graph is not None

    def nx_graph(self) -> Any | None:
        """暴露 NetworkX DiGraph 用于高级算法（pagerank / community detection 等）。

        None 表示 NetworkX 不可用。
        """
        return self._nx_graph

    def shortest_path_via_nx(self, from_id: str, to_id: str) -> list[str] | None:
        """用 NetworkX 算最短路径（要求 nx_graph 可用）。

        NetworkX 的 shortest_path 是函数式 API（不是 graph 实例方法）。
        """
        if self._nx is None or self._nx_graph is None:
            return None
        try:
            return self._nx.shortest_path(self._nx_graph, from_id, to_id)
        except (self._nx.NetworkXNoPath, self._nx.NodeNotFound):
            return None

    # === 内部 ===

    def _sync_nx_from_data(self) -> None:
        """从 _data 重建 NetworkX 图。"""
        if self._nx_graph is None:
            return
        self._nx_graph.clear()
        for n in self._data.nodes:
            self._nx_graph.add_node(n.id, data=n.model_dump())
        for e in self._data.edges:
            self._nx_graph.add_edge(
                e.from_id, e.to_id, type=e.type.value, label=e.label, chapter=e.chapter
            )
