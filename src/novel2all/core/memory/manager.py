"""MemoryManager：长记忆系统的统一入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from novel2all.core.memory.extractor import Extractor
from novel2all.core.memory.retriever import MemoryRetriever
from novel2all.core.memory.summarizer import ChapterSummarizer
from novel2all.core.memory.tracker import (
    CharacterState,
    Tracker,
    TrackingState,
)
from novel2all.core.memory.types import (
    MemoryConfig,
    MemoryContext,
    MemoryItem,
    MemoryLayer,
)
from novel2all.core.memory.verifier import ConsistencyIssue, Verifier


class MemoryManager(BaseModel):
    """长记忆系统统一入口。

    关键 API：
    - load_for_writing()：写作前组装 memory context
    - update_after_writing()：写完后自动更新 tracking
    - pre_write_check()：写前一致性检查
    - post_write_check()：写后质量检查

    v0.21 接入：
    - retriever：L4 事件检索（chromadb → TF-IDF → keyword 三层降级）
    - summarizer：早期章节压缩（1-10 全量、11-30 每5章滚动、31+ 每10章滚动）
    """

    project_root: Path
    config: MemoryConfig = MemoryConfig()
    llm: Any  # LLMProvider（避免循环依赖）

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def tracker(self) -> Tracker:
        return Tracker(self.project_root / "_tracking-state.json")

    @property
    def extractor(self) -> Extractor:
        return Extractor(self.llm)  # type: ignore[arg-type]

    @property
    def verifier(self) -> Verifier:
        return Verifier(self.llm)  # type: ignore[arg-type]

    @property
    def retriever(self) -> MemoryRetriever:
        # Lazy init，单例模式：项目级复用 .chroma/ 目录
        if not hasattr(self, "_retriever_cache"):
            self._retriever_cache = MemoryRetriever(  # type: ignore[attr-defined]
                self.project_root / ".chroma"
            )
        return self._retriever_cache  # type: ignore[attr-defined]

    @property
    def summarizer(self) -> ChapterSummarizer:
        return ChapterSummarizer()

    # === L1: 核心设定 ===

    async def load_core(self) -> list[MemoryItem]:
        """加载核心设定（永远加载）。"""
        items: list[MemoryItem] = []
        # 文风锚点
        style_file = self.project_root / "设定" / "文风.md"
        if style_file.exists():
            items.append(
                MemoryItem(
                    content=style_file.read_text(encoding="utf-8"),
                    source=str(style_file),
                    layer=MemoryLayer.CORE,
                    token_count=len(style_file.read_text(encoding="utf-8")) // 4,
                )
            )
        # 世界观核心
        worldview_dir = self.project_root / "设定" / "世界观"
        if worldview_dir.exists():
            for f in worldview_dir.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                items.append(
                    MemoryItem(
                        content=content,
                        source=str(f),
                        layer=MemoryLayer.CORE,
                        token_count=len(content) // 4,
                    )
                )
        return items

    # === L2: 角色状态 ===

    async def load_character_states(self, characters: list[str]) -> list[MemoryItem]:
        """加载指定角色的当前状态。"""
        if not self.tracker.exists():
            return []

        state = self.tracker.read()
        items: list[MemoryItem] = []
        for name in characters:
            char = state.characters.get(name)
            if char:
                items.append(
                    MemoryItem(
                        content=self._format_character(char),
                        source=f"_tracking-state.json#characters.{name}",
                        layer=MemoryLayer.CHARACTER,
                        token_count=100,
                        relevance=1.0,
                    )
                )
        return items

    # === L3: 最近章节 ===

    async def load_recent_chapters(self, current_chapter: int) -> list[MemoryItem]:
        """加载最近 N 章摘要。

        v0.21 升级：按档位压缩
          - 第 1-10 章：全量
          - 第 11-30 章：每 5 章合并成一段滚动摘要
          - 第 31+ 章：每 10 章合并成一段滚动摘要

        始终额外保留最近 recent_chapter_count 章的全量摘要（无论档位）。
        """
        if not self.tracker.exists():
            return []

        state = self.tracker.read()
        sorted_chapters = sorted(state.recent_chapter_summaries.keys(), reverse=True)
        # 最近 N 章（不压缩）作为"近期窗口"
        recent_uncompressed = [ch for ch in sorted_chapters if ch < current_chapter][
            : self.config.recent_chapter_count
        ]

        # 早期压缩：从剩余章节里按档位折叠
        older_chapters = [
            ch for ch in sorted_chapters if ch < current_chapter and ch not in recent_uncompressed
        ]

        items: list[MemoryItem] = []

        # 滚动摘要（按桶取一段代表）
        rolling_keys_added: set[tuple[int, int]] = set()
        from novel2all.core.memory.summarizer import bucket_of

        for ch in older_chapters:
            start, end = bucket_of(ch)
            if (start, end) in rolling_keys_added:
                continue
            rolling_keys_added.add((start, end))
            # 收集桶内所有摘要，拼接为一段
            bucket_summaries = [
                state.recent_chapter_summaries[c]
                for c in sorted(state.recent_chapter_summaries.keys())
                if start <= c <= end <= current_chapter
            ]
            if not bucket_summaries:
                continue
            rolling_text = f"## 第{start}-{end}章（滚动）\n" + " | ".join(bucket_summaries)
            items.append(
                MemoryItem(
                    content=rolling_text,
                    source=f"_tracking-state.json#rolling.{start}-{end}",
                    layer=MemoryLayer.RECENT,
                    token_count=len(rolling_text) // 4,
                    relevance=0.7,  # 滚动摘要权重低于近章
                )
            )

        # 近期窗口（按时间顺序输出）
        for ch in sorted(recent_uncompressed):
            summary = state.recent_chapter_summaries[ch]
            items.append(
                MemoryItem(
                    content=f"## 第{ch}章\n{summary}",
                    source=f"_tracking-state.json#recent_chapter_summaries.{ch}",
                    layer=MemoryLayer.RECENT,
                    token_count=len(summary) // 4,
                    relevance=1.0,
                )
            )
        return items

    # === L4: 事件检索（向量检索） ===

    async def search_relevant_events(
        self,
        query: str,
        top_k: int | None = None,
        chapter_range: tuple[int, int] | None = None,
    ) -> list[MemoryItem]:
        """检索相关历史事件（v0.21 接入向量检索 + 三层降级）。

        优先用 chromadb 语义检索；不可用时自动降级 TF-IDF → keyword。
        """
        k = top_k if top_k is not None else self.config.event_top_k
        return self.retriever.query(
            query,
            top_k=k,
            chapter_range=chapter_range,
        )

    # === 统一组装 ===

    async def load_for_writing(
        self,
        chapter: int,
        chapter_outline: str,
        characters_involved: list[str],
    ) -> MemoryContext:
        """写作前组装完整 memory context。"""
        core = await self.load_core()
        character = await self.load_character_states(characters_involved)
        recent = await self.load_recent_chapters(chapter)
        events = await self.search_relevant_events(chapter_outline)

        return MemoryContext(
            core=core,
            character=character,
            recent=recent,
            events=events,
        )

    # === 写后更新 ===

    async def update_after_writing(
        self,
        chapter: int,
        content: str,
    ) -> tuple[TrackingState, list[ConsistencyIssue]]:
        """写完一章后自动更新 tracking + 检查一致性。

        Returns: (updated_state, post_write_issues)

        v0.21 新增：把提取出的事件自动入库到 retriever（L4），
        供后续章节检索用。
        """
        if not self.tracker.exists():
            raise FileNotFoundError("Tracking state not initialized. Run `novel2all setup` first.")

        state = self.tracker.read()

        # 1. 自动提取关键信息
        extracted = await self.extractor.extract(
            chapter=chapter,
            content=content,
            previous_state=state,
        )

        # 2. 应用到 state
        state = self.extractor.apply_to_state(state, extracted)

        # 3. 写回
        self.tracker.write(state)

        # 4. 自动入库新事件到 retriever（L4）—— v0.21
        if self.config.auto_embed_after_write:
            self._index_chapter_events(chapter, content, state)

        # 5. 写后一致性检查
        issues = await self.verifier.post_write_check(state, content)

        return state, issues

    def _index_chapter_events(
        self,
        chapter: int,
        content: str,
        state: TrackingState,
    ) -> int:
        """把本章关键事件入库到 retriever。返回入库条数。"""
        events: list[dict[str, Any]] = []

        # 时间线条目
        for event in state.timeline:
            if event.chapter != chapter:
                continue
            events.append(
                {
                    "chapter": chapter,
                    "event_type": "timeline",
                    "text": f"[{event.in_world_time}] {event.location}: {event.summary}",
                    "metadata": {"characters": event.characters},
                }
            )

        # 角色变化（用本章 last_updated_chapter == chapter 的角色）
        for name, char in state.characters.items():
            if char.last_updated_chapter != chapter:
                continue
            parts = [f"角色 {name}"]
            if char.location:
                parts.append(f"位置 {char.location}")
            if char.emotional_state:
                parts.append(f"情绪 {char.emotional_state}")
            if char.motivation:
                parts.append(f"动机 {char.motivation}")
            events.append(
                {
                    "chapter": chapter,
                    "event_type": "character_change",
                    "text": "，".join(parts),
                    "metadata": {"character": name},
                }
            )

        # 伏笔（本章新埋伏笔或推进）
        for fs in state.foreshadowing.values():
            if fs.planted_chapter != chapter and fs.notes is None:
                continue
            if fs.planted_chapter == chapter or (fs.notes and f"ch{chapter}" in fs.notes):
                events.append(
                    {
                        "chapter": chapter,
                        "event_type": "foreshadowing",
                        "text": f"伏笔 {fs.id}: {fs.description} (status={fs.status})",
                        "metadata": {"foreshadowing_id": fs.id, "status": fs.status},
                    }
                )

        if events:
            self.retriever.add_events(events)
        return len(events)

    # === 写前检查 ===

    async def pre_write_check(
        self,
        chapter: int,
        outline: str,
    ) -> list[ConsistencyIssue]:
        """写前一致性检查（blocking 严重冲突）。"""
        if not self.tracker.exists():
            return []

        state = self.tracker.read()
        return await self.verifier.pre_write_check(state, outline)

    # === 辅助 ===

    @staticmethod
    def _format_character(char: CharacterState) -> str:
        parts = [f"# {char.name}"]
        if char.location:
            parts.append(f"位置：{char.location}")
        if char.emotional_state:
            parts.append(f"情绪：{char.emotional_state}")
        if char.motivation:
            parts.append(f"动机：{char.motivation}")
        if char.knowledge:
            parts.append("已知：")
            for k in char.knowledge:
                parts.append(f"- {k}")
        return "\n".join(parts)
