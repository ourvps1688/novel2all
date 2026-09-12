"""MemoryManager L5 知识图谱集成（V0.22.4）单元测试。

不调真实 LLM —— 用 mock provider 验证 Manager L5 API：
- graph property lazy init（无 tracker / 有 tracker）
- load_graph_for_chapter 三路查询（角色 / active 伏笔 / 最近事件）
- 节点去重（角色子图与伏笔子图有重叠）
- load_for_writing 端到端集成（图谱注入 ctx.graph）
- 空图谱 / 空状态优雅降级
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novel2all.core.memory import (
    MemoryLayer,
    MemoryManager,
    Tracker,
)
from novel2all.core.memory.tracker import ForeshadowingState


class MockLLM:
    """极简 mock LLM（不调真实网络）。"""

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return "{}"

    async def complete_structured(self, prompt: str, *, response_model: Any, **kwargs: Any) -> Any:
        return response_model.model_construct()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """创建临时项目目录。"""
    (tmp_path / "设定").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    return tmp_path


@pytest.fixture
def manager(tmp_project: Path) -> MemoryManager:
    """标准 manager：init tracker + mock LLM。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    tracker.init(project_name="图谱集成测试", total_chapters_target=50)
    return MemoryManager(project_root=tmp_project, llm=MockLLM())


@pytest.fixture
def manager_no_tracker(tmp_project: Path) -> MemoryManager:
    """无 tracker 状态的 manager。"""
    return MemoryManager(project_root=tmp_project, llm=MockLLM())


def _seed_graph(
    manager: MemoryManager,
    nodes: list[dict],
    edges: list[dict],
) -> None:
    """把图谱节点/边写入 tracker state.graph。"""
    state = manager.tracker.read()
    state.graph = {"nodes": nodes, "edges": edges}
    manager.tracker.write(state)


# === Manager.graph property 测试 ===


class TestGraphProperty:
    def test_graph_lazy_init_empty_when_no_tracker(self, manager_no_tracker: MemoryManager) -> None:
        """无 tracker 时 graph 应返回空图谱（0 节点 / 0 边）。"""
        g = manager_no_tracker.graph
        assert g.count() == (0, 0)

    def test_graph_lazy_init_loads_from_state(self, manager: MemoryManager) -> None:
        """tracker state.graph 有数据时，graph property 应正确反序列化。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷", "alive": True},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒", "alive": True},
            ],
            edges=[
                {
                    "from_id": "char:林雷",
                    "to_id": "char:苏寒",
                    "type": "related_to",
                    "label": "兄弟",
                }
            ],
        )
        g = manager.graph
        assert g.has_node("char:林雷")
        assert g.has_node("char:苏寒")
        edges = g.get_neighbors("char:林雷")
        assert len(edges) == 1
        assert edges[0].label == "兄弟"

    def test_graph_singleton_cache(self, manager: MemoryManager) -> None:
        """连续访问 graph property 应返回同一实例（lazy 缓存）。"""
        _seed_graph(
            manager,
            nodes=[{"id": "char:林雷", "type": "Character", "name": "林雷"}],
            edges=[],
        )
        g1 = manager.graph
        g2 = manager.graph
        assert g1 is g2


# === load_graph_for_chapter 测试 ===


class TestLoadGraphForChapter:
    @pytest.mark.asyncio
    async def test_empty_graph_returns_empty_list(self, manager: MemoryManager) -> None:
        """空图谱 → 返回 []。"""
        items = await manager.load_graph_for_chapter(
            chapter=5,
            characters_involved=["林雷"],
            chapter_outline="继续",
        )
        assert items == []

    @pytest.mark.asyncio
    async def test_no_tracker_returns_empty_list(self, manager_no_tracker: MemoryManager) -> None:
        """无 tracker → 返回 []。"""
        items = await manager_no_tracker.load_graph_for_chapter(
            chapter=5,
            characters_involved=["林雷"],
            chapter_outline="继续",
        )
        assert items == []

    @pytest.mark.asyncio
    async def test_character_subgraph_two_hops(self, manager: MemoryManager) -> None:
        """角色子图：林雷 → 苏寒(1跳) → 苍茫镇(2跳)。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷", "alive": True},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒", "alive": True},
                {"id": "loc:苍茫镇", "type": "Location", "name": "苍茫镇", "type_detail": "city"},
            ],
            edges=[
                {
                    "from_id": "char:林雷",
                    "to_id": "char:苏寒",
                    "type": "related_to",
                    "label": "兄弟",
                },
                {"from_id": "char:苏寒", "to_id": "loc:苍茫镇", "type": "located_in"},
            ],
        )
        items = await manager.load_graph_for_chapter(
            chapter=5,
            characters_involved=["林雷"],
            chapter_outline="回苍茫镇",
        )
        assert len(items) >= 1
        all_content = "\n".join(i.content for i in items)
        assert "林雷" in all_content
        assert "苏寒" in all_content
        assert "苍茫镇" in all_content
        assert "兄弟" in all_content  # related_to label

    @pytest.mark.asyncio
    async def test_character_not_in_graph_skipped(self, manager: MemoryManager) -> None:
        """未在图谱中的角色应被静默跳过。"""
        _seed_graph(
            manager,
            nodes=[{"id": "char:林雷", "type": "Character", "name": "林雷"}],
            edges=[],
        )
        items = await manager.load_graph_for_chapter(
            chapter=5,
            characters_involved=["林雷", "不存在的角色"],
            chapter_outline="继续",
        )
        # 只查到林雷，不报错
        assert len(items) == 1
        assert "林雷" in items[0].content

    @pytest.mark.asyncio
    async def test_active_foreshadowing_included(self, manager: MemoryManager) -> None:
        """active 伏笔应被注入 graph context。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {
                    "id": "fs:bloodline",
                    "type": "Foreshadowing",
                    "name": "身世之谜",
                    "id_short": "fs_bloodline_secret",
                    "status": "active",
                },
            ],
            edges=[],
        )
        # 在 tracker state.foreshadowing 也登记 active 伏笔
        state = manager.tracker.read()
        state.foreshadowing["bloodline"] = ForeshadowingState(
            id="bloodline",  # 非 fs: 前缀，验证兼容性
            description="林雷的身世之谜",
            planted_chapter=2,
            status="active",
        )
        manager.tracker.write(state)

        items = await manager.load_graph_for_chapter(
            chapter=10,
            characters_involved=["林雷"],
            chapter_outline="继续",
        )
        all_content = "\n".join(i.content for i in items)
        assert "身世之谜" in all_content
        assert "[active]" in all_content

    @pytest.mark.asyncio
    async def test_revealed_foreshadowing_excluded(self, manager: MemoryManager) -> None:
        """已揭示伏笔不应注入 graph context（避免噪声）。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {
                    "id": "fs:secret",
                    "type": "Foreshadowing",
                    "name": "秘密",
                    "status": "revealed",
                },
            ],
            edges=[],
        )
        state = manager.tracker.read()
        state.foreshadowing["secret"] = ForeshadowingState(
            id="fs:secret",
            description="已揭示的秘密",
            planted_chapter=1,
            status="revealed",
        )
        manager.tracker.write(state)

        items = await manager.load_graph_for_chapter(
            chapter=10,
            characters_involved=["林雷"],
            chapter_outline="继续",
        )
        # 只返回林雷角色子图（不含已揭示伏笔）
        assert len(items) == 1
        assert "秘密" not in items[0].content

    @pytest.mark.asyncio
    async def test_recent_events_included(self, manager: MemoryManager) -> None:
        """最近事件（last_chapter 在 [chapter-5, chapter)）应被注入。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {
                    "id": "event:awakening_ch3",
                    "type": "Event",
                    "name": "林雷觉醒",
                    "in_world_time": "景和三年春",
                    "last_chapter": 3,
                },
            ],
            edges=[
                {"from_id": "char:林雷", "to_id": "event:awakening_ch3", "type": "appears_in"},
            ],
        )
        items = await manager.load_graph_for_chapter(
            chapter=7,  # 当前第 7 章
            characters_involved=["林雷"],
            chapter_outline="继续",
        )
        all_content = "\n".join(i.content for i in items)
        assert "林雷觉醒" in all_content

    @pytest.mark.asyncio
    async def test_old_events_excluded(self, manager: MemoryManager) -> None:
        """超出窗口的旧事件（> 5 章前）不应注入。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {
                    "id": "event:birth_ch1",
                    "type": "Event",
                    "name": "林雷出生",
                    "last_chapter": 1,
                },
            ],
            edges=[],
        )
        items = await manager.load_graph_for_chapter(
            chapter=20,  # 距第 1 章 19 章
            characters_involved=["林雷"],
            chapter_outline="继续",
        )
        # 只查到林雷本人 + 1 个 item（角色子图），不含出生事件
        all_content = "\n".join(i.content for i in items)
        assert "林雷出生" not in all_content

    @pytest.mark.asyncio
    async def test_deduplication_between_subgraphs(self, manager: MemoryManager) -> None:
        """角色子图与伏笔子图重叠时，节点应去重。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒"},
                {
                    "id": "fs:bloodline",
                    "type": "Foreshadowing",
                    "name": "身世之谜",
                    "status": "active",
                },
            ],
            edges=[
                {"from_id": "char:林雷", "to_id": "fs:bloodline", "type": "related_to"},
                {"from_id": "char:苏寒", "to_id": "fs:bloodline", "type": "related_to"},
            ],
        )
        state = manager.tracker.read()
        state.foreshadowing["bloodline"] = ForeshadowingState(
            id="fs:bloodline",
            description="身世之谜",
            planted_chapter=2,
            status="active",
        )
        manager.tracker.write(state)

        items = await manager.load_graph_for_chapter(
            chapter=10,
            characters_involved=["林雷", "苏寒"],
            chapter_outline="继续",
        )
        # 验证：active 伏笔不应被作为独立 item 创建（因为已被角色子图覆盖）
        # 角色子图 item 含 fs:bloodline 节点是合理的（连通性）；独立"伏笔 X 子图"item 才算冗余
        item_sources = [i.source for i in items]
        foreshadowing_items = [s for s in item_sources if "伏笔" in s]
        assert len(foreshadowing_items) == 0, (
            f"fs:bloodline 已被林雷 / 苏寒 子图覆盖，不应再创建独立伏笔 item: {item_sources}"
        )
        # 角色子图应有 2 个（林雷 + 苏寒）
        character_items = [s for s in item_sources if "角色" in s]
        assert len(character_items) == 2, (
            f"应有 2 个角色子图 item，实际 {len(character_items)}: {item_sources}"
        )


# === MemoryItem layer 测试 ===


class TestGraphMemoryItem:
    @pytest.mark.asyncio
    async def test_graph_item_layer_is_graph(self, manager: MemoryManager) -> None:
        """load_graph_for_chapter 返回的 item 应标记 layer=GRAPH。"""
        _seed_graph(
            manager,
            nodes=[{"id": "char:林雷", "type": "Character", "name": "林雷"}],
            edges=[],
        )
        items = await manager.load_graph_for_chapter(
            chapter=5, characters_involved=["林雷"], chapter_outline="继续"
        )
        assert len(items) >= 1
        assert all(item.layer == MemoryLayer.GRAPH for item in items)

    @pytest.mark.asyncio
    async def test_graph_item_relevance_high(self, manager: MemoryManager) -> None:
        """角色子图 item 的 relevance 应 ≥ 0.9。"""
        _seed_graph(
            manager,
            nodes=[{"id": "char:林雷", "type": "Character", "name": "林雷"}],
            edges=[],
        )
        items = await manager.load_graph_for_chapter(
            chapter=5, characters_involved=["林雷"], chapter_outline="继续"
        )
        assert items[0].relevance >= 0.9

    @pytest.mark.asyncio
    async def test_graph_item_token_count_positive(self, manager: MemoryManager) -> None:
        """子图 item 的 token_count 应 > 0。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒"},
            ],
            edges=[
                {
                    "from_id": "char:林雷",
                    "to_id": "char:苏寒",
                    "type": "related_to",
                    "label": "兄弟",
                }
            ],
        )
        items = await manager.load_graph_for_chapter(
            chapter=5, characters_involved=["林雷"], chapter_outline="继续"
        )
        assert items[0].token_count > 0


# === load_for_writing 集成测试 ===


class TestLoadForWritingIntegration:
    @pytest.mark.asyncio
    async def test_load_for_writing_includes_graph(self, manager: MemoryManager) -> None:
        """load_for_writing 应把图谱注入到 ctx.graph。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒"},
            ],
            edges=[
                {
                    "from_id": "char:林雷",
                    "to_id": "char:苏寒",
                    "type": "related_to",
                    "label": "兄弟",
                }
            ],
        )
        ctx = await manager.load_for_writing(
            chapter=10, chapter_outline="继续", characters_involved=["林雷"]
        )
        assert len(ctx.graph) >= 1
        assert all(item.layer == MemoryLayer.GRAPH for item in ctx.graph)

    @pytest.mark.asyncio
    async def test_load_for_writing_empty_graph(self, manager: MemoryManager) -> None:
        """无图谱时 ctx.graph 应为空 list（不报错）。"""
        ctx = await manager.load_for_writing(
            chapter=5, chapter_outline="继续", characters_involved=["林雷"]
        )
        assert ctx.graph == []

    @pytest.mark.asyncio
    async def test_load_for_writing_graph_in_system_sections(self, manager: MemoryManager) -> None:
        """ctx.graph 应能被 to_system_sections 组装为"知识图谱片段"段。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒"},
            ],
            edges=[
                {
                    "from_id": "char:林雷",
                    "to_id": "char:苏寒",
                    "type": "related_to",
                    "label": "兄弟",
                }
            ],
        )
        ctx = await manager.load_for_writing(
            chapter=10, chapter_outline="继续", characters_involved=["林雷"]
        )
        sections = ctx.to_system_sections()
        graph_section = next(s for s in sections if "# 知识图谱片段" in s)
        assert "林雷" in graph_section
        assert "苏寒" in graph_section
        assert "兄弟" in graph_section

    @pytest.mark.asyncio
    async def test_load_for_writing_graph_in_iter_all(self, manager: MemoryManager) -> None:
        """ctx.iter_all() 应包含 graph 层的 item。"""
        _seed_graph(
            manager,
            nodes=[{"id": "char:林雷", "type": "Character", "name": "林雷"}],
            edges=[],
        )
        ctx = await manager.load_for_writing(
            chapter=5, chapter_outline="继续", characters_involved=["林雷"]
        )
        layers = {item.layer for item in ctx.iter_all()}
        assert MemoryLayer.GRAPH in layers

    @pytest.mark.asyncio
    async def test_load_for_writing_total_tokens_includes_graph(
        self, manager: MemoryManager
    ) -> None:
        """ctx.total_tokens 应包含 graph 层的 token。"""
        _seed_graph(
            manager,
            nodes=[
                {"id": "char:林雷", "type": "Character", "name": "林雷"},
                {"id": "char:苏寒", "type": "Character", "name": "苏寒"},
            ],
            edges=[
                {
                    "from_id": "char:林雷",
                    "to_id": "char:苏寒",
                    "type": "related_to",
                    "label": "兄弟",
                }
            ],
        )
        ctx = await manager.load_for_writing(
            chapter=10, chapter_outline="继续", characters_involved=["林雷"]
        )
        graph_tokens = sum(item.token_count for item in ctx.graph)
        assert ctx.total_tokens >= graph_tokens
        assert graph_tokens > 0
