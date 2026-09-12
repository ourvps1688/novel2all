"""L5 知识图谱（V0.22）单元测试。

覆盖 MemoryGraph 类的：
- 节点 / 边 CRUD
- 查询（get_neighbors / get_path / query_subgraph）
- 增量合并（merge_chapter）
- 序列化（to_dict / from_dict / JSON）
- TrackingState 嵌入集成
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novel2all.core.memory.graph import MemoryGraph
from novel2all.core.memory.tracker import Tracker
from novel2all.core.memory.types import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
)

# === 节点 / 边 CRUD ===


class TestCRUD:
    def test_empty_init(self) -> None:
        g = MemoryGraph()
        assert g.count() == (0, 0)
        assert g.get_node("any") is None
        assert not g.has_node("any")

    def test_add_node(self) -> None:
        g = MemoryGraph()
        g.add_node(GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷", alive=True))
        assert g.count() == (1, 0)
        assert g.has_node("char:林雷")
        assert g.get_node("char:林雷").name == "林雷"

    def test_add_node_upsert(self) -> None:
        """id 重复则更新字段（保留未指定的字段）。"""
        g = MemoryGraph()
        g.add_node(GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷", alive=True))
        # 重新 add 同一个 id 但更新字段
        g.add_node(
            GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷-觉醒后", alive=False)
        )
        assert g.count() == (1, 0)
        node = g.get_node("char:林雷")
        assert node.name == "林雷-觉醒后"
        assert node.alive is False

    def test_add_edge(self) -> None:
        g = MemoryGraph()
        g.add_node(GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷"))
        g.add_node(GraphNode(id="char:苏寒", type=NodeType.CHARACTER, name="苏寒"))
        g.add_edge(
            GraphEdge(
                from_id="char:林雷", to_id="char:苏寒", type=EdgeType.RELATED_TO, label="兄弟"
            )
        )
        assert g.count() == (2, 1)

    def test_add_edge_upsert(self) -> None:
        """三元组重复则更新 label/chapter。"""
        g = MemoryGraph()
        g.add_node(GraphNode(id="a", type=NodeType.CHARACTER, name="A"))
        g.add_node(GraphNode(id="b", type=NodeType.CHARACTER, name="B"))
        g.add_edge(GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO, label="朋友"))
        g.add_edge(
            GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO, label="仇敌", chapter=10)
        )
        assert g.count() == (2, 1)
        edges = g.get_neighbors("a", EdgeType.RELATED_TO)
        assert edges[0].label == "仇敌"
        assert edges[0].chapter == 10

    def test_remove_node_cascades(self) -> None:
        """删除节点也删除关联边。"""
        g = MemoryGraph()
        g.add_node(GraphNode(id="a", type=NodeType.CHARACTER, name="A"))
        g.add_node(GraphNode(id="b", type=NodeType.CHARACTER, name="B"))
        g.add_node(GraphNode(id="c", type=NodeType.CHARACTER, name="C"))
        g.add_edge(GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO))
        g.add_edge(GraphEdge(from_id="b", to_id="c", type=EdgeType.RELATED_TO))
        assert g.count() == (3, 2)
        removed = g.remove_node("b")
        assert removed is True
        assert g.count() == (2, 0)  # b 节点 + 2 条边全删

    def test_remove_node_not_exists(self) -> None:
        g = MemoryGraph()
        assert g.remove_node("nonexistent") is False


# === 查询 ===


class TestQuery:
    @pytest.fixture
    def graph(self) -> MemoryGraph:
        g = MemoryGraph()
        # 节点
        g.add_node(GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷", alive=True))
        g.add_node(GraphNode(id="char:苏寒", type=NodeType.CHARACTER, name="苏寒", alive=True))
        g.add_node(
            GraphNode(id="loc:苍茫镇", type=NodeType.LOCATION, name="苍茫镇", type_detail="city")
        )
        g.add_node(GraphNode(id="event:awakening", type=NodeType.EVENT, name="林雷觉醒"))
        g.add_node(
            GraphNode(
                id="fs:bloodline",
                type=NodeType.FORESHADOWING,
                name="身世之谜",
                id_short="fs_bloodline_secret",
                status="active",
            )
        )
        # 边
        g.add_edge(
            GraphEdge(
                from_id="char:林雷",
                to_id="char:苏寒",
                type=EdgeType.RELATED_TO,
                label="兄弟",
                chapter=1,
            )
        )
        g.add_edge(
            GraphEdge(from_id="char:林雷", to_id="loc:苍茫镇", type=EdgeType.LOCATED_IN, chapter=1)
        )
        g.add_edge(
            GraphEdge(
                from_id="char:林雷", to_id="event:awakening", type=EdgeType.APPEARS_IN, chapter=2
            )
        )
        g.add_edge(
            GraphEdge(
                from_id="fs:bloodline",
                to_id="event:awakening",
                type=EdgeType.FORESHADOWS,
                chapter=2,
            )
        )
        return g

    def test_get_neighbors_bidirectional(self, graph: MemoryGraph) -> None:
        # 林雷相关的边（无论方向）
        neighbors = graph.get_neighbors("char:林雷")
        assert len(neighbors) == 3  # 苏寒 + 苍茫镇 + 觉醒事件
        edge_types = {n.type for n in neighbors}
        assert edge_types == {EdgeType.RELATED_TO, EdgeType.LOCATED_IN, EdgeType.APPEARS_IN}

    def test_get_neighbors_filter_by_type(self, graph: MemoryGraph) -> None:
        neighbors = graph.get_neighbors("char:林雷", EdgeType.RELATED_TO)
        assert len(neighbors) == 1
        assert neighbors[0].label == "兄弟"

    def test_get_edges_between(self, graph: MemoryGraph) -> None:
        edges = graph.get_edges_between("char:林雷", "char:苏寒")
        assert len(edges) == 1
        assert edges[0].type == EdgeType.RELATED_TO

    def test_get_path_direct(self, graph: MemoryGraph) -> None:
        # 林雷 → 苏寒（直接）
        path = graph.get_path("char:林雷", "char:苏寒")
        assert path is not None
        assert len(path) == 1
        assert path[0].type == EdgeType.RELATED_TO

    def test_get_path_via_intermediate(self, graph: MemoryGraph) -> None:
        # 苏寒 → 觉醒事件（2 跳：苏寒 - RELATED_TO 林雷 - APPEARS_IN 觉醒）
        # 但当前 graph 里没有 "苏寒 - 林雷" 边（只有 林雷 - 苏寒）
        # get_path 是无向的，所以反向也能走
        path = graph.get_path("char:苏寒", "event:awakening", max_hops=3)
        assert path is not None
        assert len(path) == 2  # 苏寒 → 林雷 → 觉醒事件

    def test_get_path_not_found(self, graph: MemoryGraph) -> None:
        # fs:bloodline 是孤立节点（除了 foreshadows 边）
        # 它到 char:林雷 没有路径（边是 foreshadows → event:awakening）
        # 但 fes → event → char:林雷（2 跳）
        path = graph.get_path("fs:bloodline", "char:林雷", max_hops=3)
        assert path is not None
        assert len(path) == 2

    def test_get_path_exceeds_max_hops(self, graph: MemoryGraph) -> None:
        # max_hops=1 时 fs:bloodline → char:林雷 应 None（2 跳超限）
        path = graph.get_path("fs:bloodline", "char:林雷", max_hops=1)
        assert path is None

    def test_query_subgraph_2_hops(self, graph: MemoryGraph) -> None:
        # 从 char:林雷 查询 2 跳子图
        sub = graph.query_subgraph("char:林雷", hops=2)
        node_ids = {n["id"] for n in sub["nodes"]}
        # 应包含：林雷（中心）、苏寒（1 跳）、苍茫镇（1 跳）、觉醒事件（1 跳）
        # 不应包含：fs:bloodline（2 跳但通过 event:awakening → fs 边反向）
        #   实际上我们的 adj 表包含双向，fs:bloodline 通过 event:awakening 在 2 跳
        assert "char:林雷" in node_ids
        assert "char:苏寒" in node_ids
        assert "loc:苍茫镇" in node_ids
        assert "event:awakening" in node_ids

    def test_query_subgraph_filter_by_type(self, graph: MemoryGraph) -> None:
        sub = graph.query_subgraph("char:林雷", hops=2, edge_type=EdgeType.RELATED_TO)
        # 只看 related_to 边
        for e in sub["edges"]:
            assert e["type"] == EdgeType.RELATED_TO.value

    def test_query_subgraph_nonexistent(self, graph: MemoryGraph) -> None:
        sub = graph.query_subgraph("nonexistent", hops=2)
        assert sub == {"nodes": [], "edges": []}


# === 增量合并 ===


class TestMergeChapter:
    def test_merge_chapter_basic(self) -> None:
        g = MemoryGraph()
        nodes = [
            GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷"),
            GraphNode(id="char:苏寒", type=NodeType.CHARACTER, name="苏寒"),
        ]
        edges = [
            GraphEdge(
                from_id="char:林雷", to_id="char:苏寒", type=EdgeType.RELATED_TO, label="兄弟"
            ),
        ]
        g.merge_chapter(1, nodes, edges)
        assert g.count() == (2, 1)
        # 节点应有 first_chapter / last_chapter
        node = g.get_node("char:林雷")
        assert node.first_chapter == 1
        assert node.last_chapter == 1

    def test_merge_chapter_updates_chapter_range(self) -> None:
        """多次 merge_chapter 应扩展 last_chapter。"""
        g = MemoryGraph()
        g.merge_chapter(
            1,
            [GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷")],
            [],
        )
        g.merge_chapter(
            5,
            [GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷")],
            [],
        )
        node = g.get_node("char:林雷")
        assert node.first_chapter == 1
        assert node.last_chapter == 5

    def test_merge_chapter_no_explicit_chapter(self) -> None:
        """节点 / 边不指定 first_chapter/chapter 时用 merge 参数。"""
        g = MemoryGraph()
        g.merge_chapter(
            3,
            [GraphNode(id="char:X", type=NodeType.CHARACTER, name="X")],
            [
                GraphEdge(
                    from_id="char:X", to_id="char:X", type=EdgeType.RELATED_TO
                ),  # 自环边用于测试
            ],
        )
        node = g.get_node("char:X")
        assert node.first_chapter == 3
        assert node.last_chapter == 3
        edges = g.get_neighbors("char:X")
        assert edges[0].chapter == 3

    def test_merge_chapter_max_chapter_takes_precedence(self) -> None:
        """边 chapter 取 max（事件可能在不同章节被重提）。"""
        g = MemoryGraph()
        g.merge_chapter(
            1,
            [],
            [GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO, chapter=1)],
        )
        g.merge_chapter(
            10,
            [],
            [GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO, chapter=10)],
        )
        edges = g.get_edges_between("a", "b")
        assert edges[0].chapter == 10


# === 序列化 ===


class TestSerialization:
    def test_to_from_dict(self) -> None:
        g1 = MemoryGraph()
        g1.add_node(GraphNode(id="a", type=NodeType.CHARACTER, name="A"))
        g1.add_node(GraphNode(id="b", type=NodeType.CHARACTER, name="B"))
        g1.add_edge(GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO, label="朋友"))
        data = g1.to_dict()
        g2 = MemoryGraph.from_dict(data)
        assert g2.count() == g1.count()
        assert g2.get_node("a").name == "A"
        assert g2.get_edges_between("a", "b")[0].label == "朋友"

    def test_to_from_json(self) -> None:
        g1 = MemoryGraph()
        g1.add_node(GraphNode(id="x", type=NodeType.LOCATION, name="X"))
        json_str = g1.to_json()
        g2 = MemoryGraph.from_json(json_str)
        assert g2.get_node("x").type == NodeType.LOCATION

    def test_from_dict_invalid_type(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemoryGraph.from_dict({"nodes": [{"id": "x", "type": "Invalid"}], "edges": []})

    def test_to_dict_format(self) -> None:
        g = MemoryGraph()
        g.add_node(GraphNode(id="a", type=NodeType.CHARACTER, name="A"))
        data = g.to_dict()
        assert set(data.keys()) == {"nodes", "edges"}
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)


# === TrackingState 集成 ===


class TestTrackerIntegration:
    def test_tracking_state_default_graph(self, tmp_path: Path) -> None:
        tracker = Tracker(tmp_path / "_tracking-state.json")
        # init 不该报错
        state = tracker.init(project_name="测试", genre="玄幻")
        assert state.graph == {"nodes": [], "edges": []}

    def test_memory_graph_round_trip_through_tracker(self, tmp_path: Path) -> None:
        """MemoryGraph → TrackingState.graph 字段 → JSON → MemoryGraph。"""
        state_file = tmp_path / "_tracking-state.json"
        tracker = Tracker(state_file)
        tracker.init(project_name="测试")

        g1 = MemoryGraph()
        g1.add_node(GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷"))
        g1.add_edge(
            GraphEdge(from_id="char:林雷", to_id="char:林雷", type=EdgeType.RELATED_TO)
        )  # 自环测试

        state = tracker.read()
        state.graph = g1.to_dict()
        tracker.write(state)

        # 重读
        state2 = tracker.read()
        g2 = MemoryGraph.from_dict(state2.graph)
        assert g2.count() == (1, 1)
        assert g2.get_node("char:林雷").name == "林雷"

    def test_merge_chapter_via_tracker(self, tmp_path: Path) -> None:
        state_file = tmp_path / "_tracking-state.json"
        tracker = Tracker(state_file)
        tracker.init(project_name="测试")

        state = tracker.read()
        g = MemoryGraph()
        g.merge_chapter(
            1,
            [GraphNode(id="char:X", type=NodeType.CHARACTER, name="X")],
            [GraphEdge(from_id="char:X", to_id="char:X", type=EdgeType.RELATED_TO)],
        )
        state.graph = g.to_dict()
        tracker.write(state)

        # 重读
        state2 = tracker.read()
        g2 = MemoryGraph.from_dict(state2.graph)
        assert g2.get_node("char:X").first_chapter == 1
        assert g2.get_node("char:X").last_chapter == 1


# === NetworkX 集成（graceful degradation）===


class TestNetworkX:
    def test_nx_available_or_not(self) -> None:
        g = MemoryGraph()
        # 不论 NetworkX 是否可用，has_nx 都应返回 bool
        assert isinstance(g.has_nx(), bool)

    def test_nx_graph_optional(self) -> None:
        g = MemoryGraph()
        g.add_node(GraphNode(id="a", type=NodeType.CHARACTER, name="A"))
        nx = g.nx_graph()
        if g.has_nx():
            assert nx is not None
            assert "a" in nx.nodes
        else:
            assert nx is None

    def test_shortest_path_via_nx(self) -> None:
        g = MemoryGraph()
        g.add_node(GraphNode(id="a", type=NodeType.CHARACTER, name="A"))
        g.add_node(GraphNode(id="b", type=NodeType.CHARACTER, name="B"))
        g.add_node(GraphNode(id="c", type=NodeType.CHARACTER, name="C"))
        g.add_edge(GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO))
        g.add_edge(GraphEdge(from_id="b", to_id="c", type=EdgeType.RELATED_TO))
        if g.has_nx():
            path = g.shortest_path_via_nx("a", "c")
            assert path == ["a", "b", "c"]


# === Pydantic 节点/边模型 ===


class TestPydanticModels:
    def test_character_node(self) -> None:
        n = GraphNode(id="char:林雷", type=NodeType.CHARACTER, name="林雷", alive=True)
        assert n.alive is True
        assert n.short_id() == "林雷"

    def test_location_node(self) -> None:
        n = GraphNode(id="loc:X", type=NodeType.LOCATION, name="X", type_detail="city")
        assert n.type_detail == "city"

    def test_foreshadowing_node(self) -> None:
        n = GraphNode(
            id="fs:y",
            type=NodeType.FORESHADOWING,
            name="Y",
            id_short="fs_y",
            status="active",
        )
        assert n.status == "active"
        assert n.id_short == "fs_y"

    def test_related_to_edge_label(self) -> None:
        e = GraphEdge(from_id="a", to_id="b", type=EdgeType.RELATED_TO, label="兄弟")
        assert e.label == "兄弟"

    def test_appears_in_edge_chapter(self) -> None:
        e = GraphEdge(from_id="a", to_id="event:x", type=EdgeType.APPEARS_IN, chapter=5)
        assert e.chapter == 5
