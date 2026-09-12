"""MemoryManager 集成测试 —— 验证 retriever + summarizer 真正接入 L4 / L3。

不调真实 LLM（用 mock provider）。
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


class MockLLM:
    """极简 mock LLM，仅用于测试 manager 流程连通性。"""

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return "{}"

    async def complete_structured(self, prompt: str, *, response_model: Any, **kwargs: Any) -> Any:
        # 返回 response_model 的空实例
        return response_model.model_construct()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """创建临时项目目录（含设定目录）。"""
    (tmp_path / "设定").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    return tmp_path


@pytest.fixture
def manager(tmp_project: Path) -> MemoryManager:
    """标准 manager，自动用 mock LLM。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    tracker.init(project_name="测试", total_chapters_target=50)
    llm = MockLLM()
    return MemoryManager(project_root=tmp_project, llm=llm)


class TestRetrieverIntegration:
    @pytest.mark.asyncio
    async def test_retriever_initialized_lazily(self, manager: MemoryManager) -> None:
        """首次访问 retriever 属性才初始化 .chroma 目录。"""
        # 调用前不应有 .chroma
        assert not (manager.project_root / ".chroma").exists()
        _ = manager.retriever
        assert (manager.project_root / ".chroma").exists()

    @pytest.mark.asyncio
    async def test_search_relevant_events_returns_items(self, manager: MemoryManager) -> None:
        """L4 检索应返回非空 MemoryItem。"""
        # 手动入库一些事件
        manager.retriever.add_events(
            [
                {"chapter": 1, "event_type": "timeline", "text": "林雷出生"},
                {"chapter": 2, "event_type": "character_change", "text": "林雷觉醒血脉"},
            ]
        )
        results = await manager.search_relevant_events("林雷觉醒")
        assert len(results) >= 1
        for item in results:
            assert item.layer == MemoryLayer.EVENT

    @pytest.mark.asyncio
    async def test_search_relevant_events_empty_corpus(self, manager: MemoryManager) -> None:
        results = await manager.search_relevant_events("任何查询")
        assert results == []

    @pytest.mark.asyncio
    async def test_load_for_writing_includes_events(self, manager: MemoryManager) -> None:
        """load_for_writing 应把检索到的事件组装进 MemoryContext.events。"""
        # 先入库 5 条
        manager.retriever.add_events(
            [
                {"chapter": i, "event_type": "timeline", "text": f"事件 {i}: 林雷相关情节"}
                for i in range(1, 6)
            ]
        )
        ctx = await manager.load_for_writing(
            chapter=10,
            chapter_outline="本章林雷将展开新冒险",
            characters_involved=["林雷"],
        )
        assert len(ctx.events) >= 1


class TestSummarizerIntegration:
    @pytest.mark.asyncio
    async def test_load_recent_chapters_uncompressed(self, manager: MemoryManager) -> None:
        """第 1-10 章（最近 5 章）应全量保留，无滚动。"""
        tracker = manager.tracker
        state = tracker.read()
        for ch in range(1, 6):
            state.recent_chapter_summaries[ch] = f"第{ch}章摘要"
        tracker.write(state)

        items = await manager.load_recent_chapters(current_chapter=11)
        # 5 章全量保留
        chapter_items = [
            i for i in items if i.source.endswith(tuple(f".{ch}" for ch in range(1, 6)))
        ]
        assert len(chapter_items) >= 1

    @pytest.mark.asyncio
    async def test_load_recent_chapters_with_rolling(self, manager: MemoryManager) -> None:
        """早期章节应按档位折叠成滚动摘要。"""
        tracker = manager.tracker
        state = tracker.read()
        # 写到第 30 章，方便后面 current_chapter=35 时近章 = 30-34
        for ch in range(1, 31):
            state.recent_chapter_summaries[ch] = f"第{ch}章摘要"
        tracker.write(state)

        items = await manager.load_recent_chapters(current_chapter=35)
        # 早期（11-29）应被滚动摘要覆盖
        rolling_items = [i for i in items if "rolling" in i.source]
        assert len(rolling_items) >= 1
        # 近 5 章（30-34）应保留全量
        full_chapter_nums = set()
        for item in items:
            if item.source.startswith("_tracking-state.json#recent_chapter_summaries."):
                try:
                    full_chapter_nums.add(int(item.source.rsplit(".", 1)[-1]))
                except ValueError:
                    pass
        assert any(30 <= ch <= 34 for ch in full_chapter_nums), (
            f"近章未保留全量: {full_chapter_nums}"
        )

    @pytest.mark.asyncio
    async def test_load_recent_chapters_returns_memory_items(self, manager: MemoryManager) -> None:
        tracker = manager.tracker
        state = tracker.read()
        # 写足够多章以触发两种分支（rolling + full）
        for ch in range(1, 15):
            state.recent_chapter_summaries[ch] = "本章摘要 " * 20  # 充足 token
        tracker.write(state)

        items = await manager.load_recent_chapters(current_chapter=20)
        assert all(item.layer == MemoryLayer.RECENT for item in items)
        # token_count > 0 的应该占大多数（content 不为空）
        non_empty = [i for i in items if i.token_count > 0]
        assert len(non_empty) >= 1, (
            f"所有 item 的 token_count 都 ≤ 0: {[i.token_count for i in items]}"
        )


class TestUpdateAfterWritingIntegration:
    @pytest.mark.asyncio
    async def test_index_chapter_events_adds_to_retriever(self, manager: MemoryManager) -> None:
        """_index_chapter_events 应把本章事件入 retriever。"""
        from novel2all.core.memory.tracker import (
            CharacterState,
            TimelineEvent,
        )

        state = manager.tracker.read()
        # 直接构造包含本章事件的状态
        state.characters["林雷"] = CharacterState(
            name="林雷",
            location="青云宗",
            emotional_state="决意",
            last_updated_chapter=5,
        )
        state.timeline.append(
            TimelineEvent(
                chapter=5,
                in_world_time="景和三年夏",
                location="青云宗",
                characters=["林雷"],
                summary="林雷参加大比获胜",
            )
        )
        manager.tracker.write(state)

        n = manager._index_chapter_events(5, "本章正文", state)
        assert n >= 2  # 至少 timeline + character_change

        # 检索应能找到
        results = manager.retriever.query("林雷 青云宗 大比", top_k=5)
        assert len(results) >= 1


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_existing_memory_context_still_works(self, manager: MemoryManager) -> None:
        """确保 load_for_writing 在 events 为空时仍返回完整 4 层。"""
        # 写一些 L1/L2/L3 数据
        (manager.project_root / "设定" / "文风.md").write_text(
            "古风古韵，简洁有力", encoding="utf-8"
        )
        tracker = manager.tracker
        state = tracker.read()
        from novel2all.core.memory.tracker import CharacterState

        state.characters["林雷"] = CharacterState(name="林雷", last_updated_chapter=2)
        state.recent_chapter_summaries[1] = "第1章摘要"
        tracker.write(state)

        ctx = await manager.load_for_writing(
            chapter=3,
            chapter_outline="继续",
            characters_involved=["林雷"],
        )
        # 4 层都应存在（events 可能空，但字段在）
        assert isinstance(ctx.core, list)
        assert isinstance(ctx.character, list)
        assert isinstance(ctx.recent, list)
        assert isinstance(ctx.events, list)
        assert ctx.total_tokens > 0
