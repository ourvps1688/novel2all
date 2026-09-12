"""Extractor L5 图谱增量提取（V0.22）单元测试。

不调真实 LLM —— 用 mock provider 验证 Extractor 完整流程：
- ExtractedChapterInfo.graph 字段解析
- ExtractedGraphData → MemoryGraph 转换（含 type 校验）
- apply_to_state 把 graph 合并到 TrackingState
- graph 节点/边缺失时优雅降级
- LLM 失败兜底（不阻断主流程）
"""

from __future__ import annotations

from typing import Any

import pytest

from novel2all.core.memory.extractor import (
    ExtractedChapterInfo,
    ExtractedGraphData,
    Extractor,
    GraphEdgeUpdate,
    GraphNodeUpdate,
    _graph_summary_for_prompt,
)
from novel2all.core.memory.tracker import Tracker

# === Mock LLM Provider ===


class MockLLM:
    """Mock LLM provider，complete_structured 返回预设结果。"""

    def __init__(self, response: Any = None, raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc
        self.last_prompt: str = ""
        self.last_response_model: type = None  # type: ignore[assignment]

    async def complete_structured(self, *, prompt, response_model, **_):
        self.last_prompt = prompt
        self.last_response_model = response_model
        if self.raise_exc:
            raise self.raise_exc
        if self.response is not None:
            return self.response
        # 默认返回空
        return response_model.model_construct()


# === ExtractedGraphData + GraphNodeUpdate/EdgeUpdate 基础 ===


class TestGraphUpdateModels:
    def test_graph_node_update_valid(self) -> None:
        n = GraphNodeUpdate(id="char:林雷", type="Character", name="林雷", alive=True)
        assert n.validate_type() is None

    def test_graph_node_update_invalid_type(self) -> None:
        n = GraphNodeUpdate(id="x:1", type="Invalid", name="x")
        err = n.validate_type()
        assert err is not None
        assert "Invalid node type" in err

    def test_graph_edge_update_valid(self) -> None:
        e = GraphEdgeUpdate(from_id="char:林雷", to_id="char:苏寒", type="related_to", label="兄弟")
        assert e.validate_type() is None

    def test_graph_edge_update_invalid_type(self) -> None:
        e = GraphEdgeUpdate(from_id="a", to_id="b", type="random")
        assert e.validate_type() is not None

    def test_extracted_graph_data_defaults(self) -> None:
        g = ExtractedGraphData()
        assert g.nodes == []
        assert g.edges == []


# === ExtractedGraphData → MemoryGraph 转换 ===


class TestToMemoryGraph:
    def test_basic_conversion(self) -> None:
        g = ExtractedGraphData(
            nodes=[
                GraphNodeUpdate(id="char:林雷", type="Character", name="林雷", alive=True),
                GraphNodeUpdate(id="char:苏寒", type="Character", name="苏寒", alive=True),
            ],
            edges=[
                GraphEdgeUpdate(
                    from_id="char:林雷", to_id="char:苏寒", type="related_to", label="兄弟"
                ),
            ],
        )
        mg = g.to_memory_graph()
        assert mg.count() == (2, 1)
        assert mg.get_path("char:林雷", "char:苏寒") is not None

    def test_skip_invalid_type(self) -> None:
        """非法 type 的节点/边应被静默跳过。

        注：合法边会自动创建端点节点（MemoryGraph.add_edge 设计行为）。
        """
        g = ExtractedGraphData(
            nodes=[
                GraphNodeUpdate(id="char:林雷", type="Character", name="林雷"),
                GraphNodeUpdate(id="x:bad", type="InvalidType", name="bad"),  # 跳过
            ],
            edges=[
                GraphEdgeUpdate(from_id="char:林雷", to_id="x:bad", type="weird_type"),  # 跳过
                GraphEdgeUpdate(from_id="char:林雷", to_id="char:苏寒", type="related_to"),
            ],
        )
        mg = g.to_memory_graph()
        # 合法节点 char:林雷 + char:苏寒（苏寒由边自动创建）
        # 非法节点 x:bad 不存在
        # 合法边 林雷→苏寒 1 条；非法 weird_type 边不创建
        assert mg.count() == (2, 1)
        assert mg.has_node("char:林雷")
        assert mg.has_node("char:苏寒")
        assert not mg.has_node("x:bad")

    def test_foreshadowing_node_fields(self) -> None:
        g = ExtractedGraphData(
            nodes=[
                GraphNodeUpdate(
                    id="fs:bloodline",
                    type="Foreshadowing",
                    name="身世之谜",
                    id_short="fs_bloodline_secret",
                    status="active",
                ),
            ],
            edges=[],
        )
        mg = g.to_memory_graph()
        node = mg.get_node("fs:bloodline")
        assert node is not None
        assert node.id_short == "fs_bloodline_secret"
        assert node.status == "active"

    def test_empty_graph(self) -> None:
        g = ExtractedGraphData()
        mg = g.to_memory_graph()
        assert mg.count() == (0, 0)


# === Extractor.extract mock LLM ===


class TestExtractWithMock:
    @pytest.fixture
    def state(self, tmp_path):
        tracker = Tracker(tmp_path / "_tracking-state.json")
        return tracker.init(project_name="图谱提取测试", genre="玄幻")

    @pytest.mark.asyncio
    async def test_extract_with_graph_data(self, state) -> None:
        """LLM 返回带 graph 数据的 ExtractedChapterInfo，Extractor 正常解析。"""
        llm_response = ExtractedChapterInfo.model_construct(
            chapter=5,
            character_updates=[],
            foreshadowing_planted=[],
            foreshadowing_changed=[],
            timeline_events=[],
            summary="林雷觉醒",
            continuity_issues=[],
            graph=ExtractedGraphData(
                nodes=[
                    GraphNodeUpdate(id="char:林雷", type="Character", name="林雷"),
                ],
                edges=[],
            ),
        )
        llm = MockLLM(response=llm_response)
        ext = Extractor(llm)
        result = await ext.extract(
            chapter=1,  # 测试覆盖
            content="林雷觉醒血脉之力。",
            previous_state=state,
        )
        # chapter 被强制覆盖为传入值
        assert result.chapter == 1
        assert result.summary == "林雷觉醒"
        assert len(result.graph.nodes) == 1
        assert result.graph.nodes[0].id == "char:林雷"

    @pytest.mark.asyncio
    async def test_extract_prompt_includes_graph_section(self, state) -> None:
        """prompt 应包含 graph 字段说明。"""
        llm = MockLLM()
        ext = Extractor(llm)
        await ext.extract(chapter=1, content="测试", previous_state=state)
        assert "graph" in llm.last_prompt
        assert "nodes" in llm.last_prompt
        assert "edges" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_extract_llm_failure_graceful_degradation(self, state) -> None:
        """LLM 失败时返回空 + warning，不抛异常。"""
        llm = MockLLM(raise_exc=RuntimeError("模拟 LLM 网络错误"))
        ext = Extractor(llm)
        result = await ext.extract(chapter=5, content="林雷觉醒", previous_state=state)
        # 失败兜底：返回空结果 + 1 个 warning
        assert result.chapter == 5
        assert len(result.continuity_issues) == 1
        assert result.continuity_issues[0].severity == "warning"
        assert "LLM extraction failed" in result.continuity_issues[0].description
        # 其它字段为空
        assert result.character_updates == []
        assert result.graph.nodes == []
        assert result.graph.edges == []


# === apply_to_state 图谱合并 ===


class TestApplyGraphToState:
    def test_apply_graph_basic(self, tmp_path) -> None:
        """图谱节点/边被合并到 state.graph。"""
        tracker = Tracker(tmp_path / "_tracking-state.json")
        state = tracker.init(project_name="测试")
        extracted = ExtractedChapterInfo.model_construct(
            chapter=2,
            character_updates=[],
            foreshadowing_planted=[],
            foreshadowing_changed=[],
            timeline_events=[],
            summary="",
            continuity_issues=[],
            graph=ExtractedGraphData(
                nodes=[
                    GraphNodeUpdate(id="char:林雷", type="Character", name="林雷", alive=True),
                    GraphNodeUpdate(
                        id="loc:苍茫镇", type="Location", name="苍茫镇", type_detail="city"
                    ),
                ],
                edges=[
                    GraphEdgeUpdate(from_id="char:林雷", to_id="loc:苍茫镇", type="located_in"),
                ],
            ),
        )
        Extractor.apply_to_state(state, extracted)
        # 验证 state.graph 已更新
        assert len(state.graph["nodes"]) == 2
        assert len(state.graph["edges"]) == 1

    def test_apply_graph_updates_existing_node(self, tmp_path) -> None:
        """节点已存在，merge 应保留并扩展 last_chapter。"""
        tracker = Tracker(tmp_path / "_tracking-state.json")
        state = tracker.init(project_name="测试")
        # 预先有 char:林雷（第 1 章）
        state.graph = {
            "nodes": [
                {
                    "id": "char:林雷",
                    "type": "Character",
                    "name": "林雷",
                    "alive": True,
                    "first_chapter": 1,
                    "last_chapter": 1,
                }
            ],
            "edges": [],
        }
        # 第 3 章再出现林雷
        extracted = ExtractedChapterInfo.model_construct(
            chapter=3,
            character_updates=[],
            foreshadowing_planted=[],
            foreshadowing_changed=[],
            timeline_events=[],
            summary="",
            continuity_issues=[],
            graph=ExtractedGraphData(
                nodes=[GraphNodeUpdate(id="char:林雷", type="Character", name="林雷")],
                edges=[],
            ),
        )
        Extractor.apply_to_state(state, extracted)
        # 林雷节点的 first/last chapter 应扩展
        lin = next(n for n in state.graph["nodes"] if n["id"] == "char:林雷")
        assert lin["first_chapter"] == 1
        assert lin["last_chapter"] == 3

    def test_apply_graph_empty(self, tmp_path) -> None:
        """空 graph 数据不应改变 state.graph。"""
        tracker = Tracker(tmp_path / "_tracking-state.json")
        state = tracker.init(project_name="测试")
        before = state.graph.copy()
        extracted = ExtractedChapterInfo.model_construct(
            chapter=2,
            character_updates=[],
            foreshadowing_planted=[],
            foreshadowing_changed=[],
            timeline_events=[],
            summary="",
            continuity_issues=[],
        )
        Extractor.apply_to_state(state, extracted)
        # state.graph 保持默认空
        assert state.graph == before or state.graph == {"nodes": [], "edges": []}

    def test_apply_graph_invalid_type_skipped(self, tmp_path) -> None:
        """非法 type 的节点/边被静默跳过，不阻塞主流程。

        注：合法边会自动创建端点节点（MemoryGraph.add_edge 设计行为）。
        """
        tracker = Tracker(tmp_path / "_tracking-state.json")
        state = tracker.init(project_name="测试")
        extracted = ExtractedChapterInfo.model_construct(
            chapter=1,
            character_updates=[],
            foreshadowing_planted=[],
            foreshadowing_changed=[],
            timeline_events=[],
            summary="",
            continuity_issues=[],
            graph=ExtractedGraphData(
                nodes=[
                    GraphNodeUpdate(id="char:林雷", type="Character", name="林雷"),
                    GraphNodeUpdate(id="bad:x", type="InvalidType", name="x"),  # 跳过
                ],
                edges=[
                    GraphEdgeUpdate(from_id="char:林雷", to_id="char:苏寒", type="related_to"),
                ],
            ),
        )
        # 不应抛异常
        Extractor.apply_to_state(state, extracted)
        # 非法节点 (bad:x) 被跳过；林雷和苏寒都被加（边自动建端点）
        node_ids = [n["id"] for n in state.graph["nodes"]]
        assert "bad:x" not in node_ids
        assert "char:林雷" in node_ids
        assert "char:苏寒" in node_ids  # 由 add_edge 自动建
        # 只 1 条边（合法那条；非法 weird_type 应被跳过）
        assert len(state.graph["edges"]) == 1
        # 且有 2 个节点
        assert len(state.graph["nodes"]) == 2


# === graph_summary_for_prompt 辅助函数 ===


class TestGraphSummaryForPrompt:
    def test_empty(self) -> None:
        result = _graph_summary_for_prompt({"nodes": [], "edges": []})
        assert result["node_count"] == 0
        assert result["edge_count"] == 0
        assert result["node_brief"] == []
        assert result["edge_brief"] == []

    def test_truncation(self) -> None:
        """> 30 节点 / > 50 边时截断。"""
        nodes = [{"id": f"char:{i}", "type": "Character", "name": f"C{i}"} for i in range(50)]
        edges = [{"from_id": f"a{i}", "to_id": f"b{i}", "type": "related_to"} for i in range(80)]
        result = _graph_summary_for_prompt({"nodes": nodes, "edges": edges})
        assert result["node_count"] == 50
        assert result["edge_count"] == 80
        assert len(result["node_brief"]) == 30  # 截断到 30
        assert len(result["edge_brief"]) == 50  # 截断到 50

    def test_dead_character_marker(self) -> None:
        """dead 角色应标 "(已死)"。"""
        nodes = [
            {"id": "char:苏寒", "type": "Character", "name": "苏寒", "alive": False},
        ]
        result = _graph_summary_for_prompt({"nodes": nodes, "edges": []})
        assert "已死" in result["node_brief"][0]

    def test_foreshadowing_status(self) -> None:
        """Foreshadowing 节点应带 status 标签。"""
        nodes = [
            {
                "id": "fs:bloodline",
                "type": "Foreshadowing",
                "name": "身世之谜",
                "status": "revealed",
            },
        ]
        result = _graph_summary_for_prompt({"nodes": nodes, "edges": []})
        assert "[revealed]" in result["node_brief"][0]

    def test_related_to_edge_with_label(self) -> None:
        """related_to 边带 label 时应在 brief 中显示。"""
        edges = [
            {
                "from_id": "char:林雷",
                "to_id": "char:苏寒",
                "type": "related_to",
                "label": "兄弟",
            },
        ]
        result = _graph_summary_for_prompt({"nodes": [], "edges": edges})
        assert '"兄弟"' in result["edge_brief"][0]
