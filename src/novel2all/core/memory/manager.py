"""MemoryManager：长记忆系统的统一入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from novel2all.core.memory.extractor import Extractor
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
        """加载最近 N 章摘要。"""
        if not self.tracker.exists():
            return []

        state = self.tracker.read()
        sorted_chapters = sorted(state.recent_chapter_summaries.keys(), reverse=True)
        recent = [ch for ch in sorted_chapters if ch < current_chapter][
            : self.config.recent_chapter_count
        ]

        items: list[MemoryItem] = []
        for ch in sorted(recent):  # 按时间顺序
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

    # === L4: 事件检索（向量检索，v0.21+ 实现） ===

    async def search_relevant_events(
        self, query: str, top_k: int | None = None
    ) -> list[MemoryItem]:
        """检索相关历史事件。

        v0.20 用最简单的 keyword 检索占位。
        v0.21 接入 chromadb 向量检索。
        """
        # TODO v0.21 接入向量数据库
        # 现在返回空，依赖 L3 滑动窗口 + L5 图谱
        return []

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

        # 4. 写后一致性检查
        issues = await self.verifier.post_write_check(state, content)

        return state, issues

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
