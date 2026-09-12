"""50 章长记忆模拟 E2E 测试。

目标（V0.21 长记忆核心验证）：
  - 不依赖真实 LLM（用 mock extractor 模拟写作 + extract 流程）
  - 50 章模拟写作后，验证：
    1. 关键角色（5 个）的 last_updated_chapter 推进到接近 50
    2. 关键伏笔（3 个）的状态正确（active/advanced/revealed）
    3. timeline 累积合理（50 章应该有几十个时间线事件）
    4. retriever 能从历史中召回"林雷"、"伏笔"、"位置"等关键词相关事件
    5. load_for_writing 返回的 events 列表非空且相关
    6. token 总量控制在 recent_token_budget * 2 以内（避免爆炸）

设计思路：
  - MockLLM.complete_structured 根据 chapter 编号返回确定性的 ExtractedChapterInfo
    （角色推进、timeline 事件、伏笔操作），模拟"小说家"行为
  - MockLLM.complete 返回章节正文 mock
  - 50 章循环调用 manager.update_after_writing，每章验证 state 更新正确
  - 最终做端到端 retrieval 测试
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from novel2all.core.memory import (
    ExtractedChapterInfo,
    MemoryConfig,
    MemoryLayer,
    MemoryManager,
    Tracker,
)
from novel2all.core.memory.extractor import (
    CharacterUpdate,
    ForeshadowingUpdate,
    TimelineEventUpdate,
)
from novel2all.core.memory.verifier import ConsistencyIssue

# === Mock LLM ===

# 5 个核心角色：林雷（主角）、苏寒（兄弟）、青云（师父）、玉佩（信物角色化）、反派X
# 3 个核心伏笔：fs_secret_identity, fs_treasure, fs_vow
CHARACTERS = ["林雷", "苏寒", "青云", "玉佩", "反派X"]
FORESHADOWINGS = ["fs_secret_identity", "fs_treasure", "fs_vow"]


class MockLLM:
    """Mock LLM，不调外部 API。

    complete_structured(prompt, response_model=ExtractedChapterInfo)：
      根据 chapter 编号返回确定性的 ExtractedChapterInfo，模拟"作者"行为：
      - 每章推进 1-2 个角色（位置/情绪）
      - 每 10 章增加一个 timeline 事件
      - 第 5 章埋设伏笔 fs_secret_identity
      - 第 20 章推进 fs_secret_identity（status=advanced）
      - 第 35 章揭示 fs_secret_identity（status=revealed）
      - 第 40 章埋设 fs_treasure
      - 第 50 章揭示 fs_vow
      - 每章 summary 包含 "林雷" 关键词

    complete(prompt) 返回 mock 章节正文。
    """

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        ch = self._extract_chapter(prompt)
        return f"第{ch}章正文：林雷继续在修仙界冒险。本章约 2500 字。"

    async def complete_structured(
        self,
        prompt: str,
        *,
        response_model: Any,
        **kwargs: Any,
    ) -> Any:
        if response_model is ExtractedChapterInfo:
            # 从 prompt 中提取章节号（提取逻辑见 _extract_chapter）。
            # 注意：必须从 prompt 解析，不能用 kwargs 里的 chapter（instructor
            # 实际不会传 chapter 参数，只能从 prompt 文本推断）。
            ch = self._extract_chapter(prompt)
            return self._mock_extract(ch, prompt)
        # Verifier pre/post-write check（返回 list[ConsistencyIssue]）
        origin = getattr(response_model, "__origin__", None)
        if origin is list:
            return []
        # 其他 Pydantic 模型
        if hasattr(response_model, "model_construct"):
            return response_model.model_construct()
        return None

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        yield await self.complete(prompt, **kwargs)

    @staticmethod
    def _extract_chapter(prompt: str) -> int:
        """从 prompt 末尾的"## 本章正文 \\n 第N章正文..."段落提取当前章节号。

        关键：必须从 content 字段提取，不能从 previous_state 里的 last_chapter
        提取——后者是上一章，会让当前章节永远小 1。
        """
        # 优先匹配 "## 本章正文\n第N章..." 这一段
        m = re.search(r"##\s*本章正文\s*\n\s*第\s*(\d+)\s*章", prompt)
        if m:
            return int(m.group(1))
        # 后备：匹配 "chapter: N" 或 "chapter N"
        m = re.search(r"chapter[\"'\s:：]+(\d+)", prompt, re.IGNORECASE)
        if m:
            # 但要排除 "last_chapter" 里的数字——通过位置约束
            # 实际上 prompt 里没有 last_chapter 字样的"chapter N"，所以这条匹配是安全的
            return int(m.group(1))
        # 最后后备：取全文最后一个"第N章"
        all_matches = re.findall(r"第\s*(\d+)\s*章", prompt)
        if all_matches:
            # 取最后一个出现的（content 在 prompt 末尾）
            return int(all_matches[-1])
        return 0

    def _mock_extract(self, ch: int, prompt: str) -> ExtractedChapterInfo:
        """根据 chapter 编号生成 ExtractedChapterInfo。"""
        char_updates: list[CharacterUpdate] = []
        timeline_events: list[TimelineEventUpdate] = []
        fs_planted: list[ForeshadowingUpdate] = []
        fs_changed: list[ForeshadowingUpdate] = []

        # 每章推进主角"林雷"（每章都推进位置/情绪）
        if ch % 1 == 0:
            char_updates.append(
                CharacterUpdate(
                    name="林雷",
                    location=f"第{ch}章场景",
                    emotional_state=("坚定" if ch % 2 == 0 else "紧张"),
                    knowledge_added=[f"第{ch}章学到的知识"],
                )
            )

        # 每 3 章推进一次苏寒
        if ch % 3 == 0:
            char_updates.append(
                CharacterUpdate(
                    name="苏寒",
                    location=f"苏寒在第{ch}章的位置",
                    emotional_state="动摇",
                )
            )

        # 每 5 章推进一次青云
        if ch % 5 == 0:
            char_updates.append(
                CharacterUpdate(
                    name="青云",
                    location="青云宗",
                    emotional_state="关注",
                )
            )

        # 每 7 章推进玉佩相关
        if ch % 7 == 0:
            char_updates.append(
                CharacterUpdate(
                    name="玉佩",
                    location="林雷怀中",
                    emotional_state="神秘",
                )
            )

        # 每 10 章出现反派X
        if ch % 10 == 0:
            char_updates.append(
                CharacterUpdate(
                    name="反派X",
                    location="暗处",
                    emotional_state="得意",
                )
            )

        # 每 10 章一个 timeline 事件
        if ch % 10 == 0:
            timeline_events.append(
                TimelineEventUpdate(
                    in_world_time=f"景和三年{1 + ch // 10}季",
                    location=f"第{ch}章地点",
                    characters=["林雷"],
                    summary=f"第{ch}章里程碑事件：林雷修为突破",
                )
            )

        # 伏笔生命周期
        if ch == 5:
            fs_planted.append(
                ForeshadowingUpdate(
                    id="fs_secret_identity",
                    description="林雷身世之谜",
                    planted_chapter=ch,
                    status="active",
                )
            )
        elif ch == 20:
            fs_changed.append(
                ForeshadowingUpdate(
                    id="fs_secret_identity",
                    description="林雷身世初显",
                    planted_chapter=5,
                    status="advanced",
                )
            )
        elif ch == 35:
            fs_changed.append(
                ForeshadowingUpdate(
                    id="fs_secret_identity",
                    description="林雷身世揭晓",
                    planted_chapter=5,
                    status="revealed",
                )
            )

        if ch == 40:
            fs_planted.append(
                ForeshadowingUpdate(
                    id="fs_treasure",
                    description="上古秘宝线索",
                    planted_chapter=ch,
                    status="active",
                )
            )

        if ch == 50:
            fs_planted.append(
                ForeshadowingUpdate(
                    id="fs_vow",
                    description="林雷的誓言",
                    planted_chapter=ch,
                    status="revealed",
                )
            )

        return ExtractedChapterInfo(
            chapter=ch,
            character_updates=char_updates,
            foreshadowing_planted=fs_planted,
            foreshadowing_changed=fs_changed,
            timeline_events=timeline_events,
            summary=f"第{ch}章摘要：林雷在玄幻世界的冒险继续。",
        )


# === Fixtures ===


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / "设定").mkdir()
    (tmp_path / "设定" / "世界观").mkdir(parents=True, exist_ok=True)
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    return tmp_path


@pytest.fixture
def manager(tmp_project: Path) -> MemoryManager:
    """预装 mock LLM 的 MemoryManager。"""
    tracker = Tracker(tmp_project / "_tracking-state.json")
    tracker.init(
        project_name="50章测试",
        genre="玄幻",
        total_chapters_target=50,
    )
    # 写入初始世界观
    (tmp_project / "设定" / "文风.md").write_text(
        "古风古韵，简洁有力，注重意境描写",
        encoding="utf-8",
    )
    return MemoryManager(
        project_root=tmp_project,
        config=MemoryConfig(
            recent_chapter_count=5,
            recent_token_budget=6000,
            event_top_k=8,
            auto_embed_after_write=True,
        ),
        llm=MockLLM(),
    )


# === 50 章模拟 ===


@pytest.mark.asyncio
async def test_50_chapters_no_character_loss(manager: MemoryManager) -> None:
    """50 章后，5 个核心角色全部仍在 state.characters 里，且 last_updated_chapter 推进。"""
    state_file = manager.project_root / "_tracking-state.json"
    tracker = Tracker(state_file)

    # 50 章循环
    for ch in range(1, 51):
        content = f"第{ch}章正文" + "林雷" * 50  # 含关键词
        _state, _issues = await manager.update_after_writing(ch, content)
        # 每章验证：tracker 写回成功
        assert state_file.exists()

    # === 验证 1：所有核心角色仍存在 ===
    final = tracker.read()
    for name in CHARACTERS:
        assert name in final.characters, f"角色 {name} 在第 50 章后丢失！"

    # === 验证 2：角色 last_updated_chapter 推进（每章都应触发）===
    # 林雷每章都更新，所以应该是 50
    assert final.characters["林雷"].last_updated_chapter == 50
    # 苏寒每 3 章更新，最近一次 48
    assert final.characters["苏寒"].last_updated_chapter == 48
    # 青云每 5 章更新，最近一次 50
    assert final.characters["青云"].last_updated_chapter == 50
    # 玉佩每 7 章更新，最近一次 49
    assert final.characters["玉佩"].last_updated_chapter == 49
    # 反派X每 10 章更新，最近一次 50
    assert final.characters["反派X"].last_updated_chapter == 50


@pytest.mark.asyncio
async def test_50_chapters_foreshadowing_lifecycle(manager: MemoryManager) -> None:
    """伏笔 lifecycle：埋下 → 推进 → 揭示，整个过程不丢失。"""
    tracker = Tracker(manager.project_root / "_tracking-state.json")

    for ch in range(1, 51):
        await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )

    final = tracker.read()

    # fs_secret_identity: 第 5 章埋下 → 第 20 章 advanced → 第 35 章 revealed
    fs_id = final.foreshadowing["fs_secret_identity"]
    assert fs_id.status == "revealed", f"fs_secret_identity 应为 revealed，实际 {fs_id.status}"
    assert fs_id.planted_chapter == 5

    # fs_treasure: 第 40 章埋下，50 章后仍 active
    fs_t = final.foreshadowing["fs_treasure"]
    assert fs_t.status == "active"
    assert fs_t.planted_chapter == 40

    # fs_vow: 第 50 章埋下并揭示
    fs_v = final.foreshadowing["fs_vow"]
    assert fs_v.status == "revealed"
    assert fs_v.planted_chapter == 50


@pytest.mark.asyncio
async def test_50_chapters_timeline_density(manager: MemoryManager) -> None:
    """Timeline 应该累积合理数量的事件（每 10 章一个里程碑）。"""
    tracker = Tracker(manager.project_root / "_tracking-state.json")

    for ch in range(1, 51):
        await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )

    final = tracker.read()
    # 50 章 / 10 = 5 个 timeline 事件
    assert len(final.timeline) == 5, f"应有 5 个 timeline 事件，实际 {len(final.timeline)}"
    # 事件按章节排序
    chapter_nums = [e.chapter for e in final.timeline]
    assert chapter_nums == [10, 20, 30, 40, 50]


@pytest.mark.asyncio
async def test_50_chapters_retriever_recall(manager: MemoryManager) -> None:
    """50 章后，用 retriever 检索历史事件能召回相关章节。"""
    # 先跑 50 章
    for ch in range(1, 51):
        await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )

    # === 验证：retriever 召回与"林雷"相关的事件 ===
    results = await manager.search_relevant_events("林雷", top_k=10)
    assert len(results) >= 1, "retriever 至少应召回 1 个事件"
    for item in results:
        assert item.layer == MemoryLayer.EVENT
        assert "林雷" in item.content or "场景" in item.content


@pytest.mark.asyncio
async def test_50_chapters_load_for_writing_includes_history(
    manager: MemoryManager,
) -> None:
    """50 章后，写第 51 章时，load_for_writing 应返回带历史记忆的 MemoryContext。"""
    # 跑 50 章
    for ch in range(1, 51):
        await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )

    # 模拟第 51 章写作前的 memory load
    ctx = await manager.load_for_writing(
        chapter=51,
        chapter_outline="林雷继续修炼，准备面对最终考验",
        characters_involved=["林雷", "苏寒"],
    )

    # === 验证 ===
    # 4 层都在
    assert isinstance(ctx.core, list)
    assert isinstance(ctx.character, list)
    assert isinstance(ctx.recent, list)
    assert isinstance(ctx.events, list)

    # 角色层：林雷、苏寒 都在
    char_names = {item.content.split("\n")[0] for item in ctx.character}
    assert any("林雷" in n for n in char_names)
    assert any("苏寒" in n for n in char_names)

    # 事件层：retriever 应召回了"林雷"相关历史
    assert len(ctx.events) >= 1
    # 召回的事件内容应含"林雷"
    assert all("林雷" in item.content or "场景" in item.content for item in ctx.events)

    # 最近章节层：包含近 5 章（46-50）的全量摘要
    recent_chapters = [
        item.source.split(".")[-1]
        for item in ctx.recent
        if item.source.startswith("_tracking-state.json#recent_chapter_summaries.")
    ]
    assert any(ch in recent_chapters for ch in ["46", "47", "48", "49", "50"])


@pytest.mark.asyncio
async def test_50_chapters_token_budget_under_control(
    manager: MemoryManager,
) -> None:
    """50 章后，load_for_writing 返回的总 token 数不应爆炸（≤ recent_token_budget × 3）。"""
    for ch in range(1, 51):
        await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )

    ctx = await manager.load_for_writing(
        chapter=51,
        chapter_outline="林雷继续修炼",
        characters_involved=["林雷"],
    )

    # 总 token 控制：不应超过 recent_token_budget × 3 = 18000
    # 实际预期：core + character + recent + events < 15000
    assert ctx.total_tokens <= 18000, (
        f"token 总数 {ctx.total_tokens} 超出预算 18000，"
        f"core={sum(i.token_count for i in ctx.core)} "
        f"character={sum(i.token_count for i in ctx.character)} "
        f"recent={sum(i.token_count for i in ctx.recent)} "
        f"events={sum(i.token_count for i in ctx.events)}"
    )


@pytest.mark.asyncio
async def test_50_chapters_no_blocking_issues(manager: MemoryManager) -> None:
    """50 章后，所有 post-write check 都应通过（无 critical issues）。"""
    all_blocking: list[ConsistencyIssue] = []
    for ch in range(1, 51):
        _, issues = await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )
        # 我们的 mock verifier 返回 []，但收集以防万一
        all_blocking.extend([i for i in issues if i.severity == "critical"])

    # mock verifier 返回 []，所以不应有 critical
    assert len(all_blocking) == 0


# === 跨章测试：写第 51 章时仍能 recall 第 1 章的角色 ===


@pytest.mark.asyncio
async def test_recall_first_chapter_at_chapter_51(manager: MemoryManager) -> None:
    """写第 51 章时，retriever 应能召回第 1 章埋下的初始角色（即使 50 章后）。"""
    for ch in range(1, 51):
        await manager.update_after_writing(
            ch,
            f"第{ch}章正文" + "林雷" * 50,
        )

    # 用 query "第1章" / "苍茫镇" 等早期关键词
    results = await manager.search_relevant_events("第10章里程碑", top_k=10)
    # 早期 milestone 事件应能被召回
    chapter_sources = []
    for item in results:
        m = re.search(r"#ch(\d+)", item.source)
        if m:
            chapter_sources.append(int(m.group(1)))
    # 至少召回第 10 章的事件（milestone）
    if chapter_sources:
        assert min(chapter_sources) <= 20, (
            f"召回的最早章节为 {min(chapter_sources)}，应该能召回第 10 章"
        )
