"""Memory 单元测试。"""

from __future__ import annotations

from novel2all.core.memory import MemoryContext, MemoryItem, MemoryLayer


def test_memory_iter_all() -> None:
    """测试 MemoryContext.iter_all。"""
    ctx = MemoryContext(
        core=[MemoryItem(content="核心", source="a.md", layer=MemoryLayer.CORE, token_count=10)],
        character=[
            MemoryItem(content="角色", source="b.md", layer=MemoryLayer.CHARACTER, token_count=20)
        ],
        recent=[
            MemoryItem(content="最近", source="c.md", layer=MemoryLayer.RECENT, token_count=30)
        ],
        events=[MemoryItem(content="事件", source="d.md", layer=MemoryLayer.EVENT, token_count=40)],
    )
    all_items = list(ctx.iter_all())
    assert len(all_items) == 4
    assert sum(i.token_count for i in all_items) == 100


def test_memory_total_tokens() -> None:
    """测试 token 计数。"""
    ctx = MemoryContext(
        core=[MemoryItem(content="x", source="a", layer=MemoryLayer.CORE, token_count=100)],
        character=[
            MemoryItem(content="y", source="b", layer=MemoryLayer.CHARACTER, token_count=200)
        ],
    )
    assert ctx.total_tokens == 300


def test_memory_to_system_sections() -> None:
    """测试组装成 system sections。"""
    ctx = MemoryContext(
        core=[MemoryItem(content="设定", source="a.md", layer=MemoryLayer.CORE)],
        character=[MemoryItem(content="角色", source="b.md", layer=MemoryLayer.CHARACTER)],
        recent=[MemoryItem(content="最近", source="c.md", layer=MemoryLayer.RECENT)],
        events=[MemoryItem(content="事件", source="d.md", layer=MemoryLayer.EVENT)],
        graph=[MemoryItem(content="图谱", source="e.md", layer=MemoryLayer.GRAPH)],
    )
    sections = ctx.to_system_sections()
    assert len(sections) == 5
    assert "# 核心设定" in sections[0]
    assert "# 角色状态" in sections[1]
    assert "# 最近章节" in sections[2]
    assert "# 相关历史事件" in sections[3]
    assert "# 知识图谱片段" in sections[4]


def test_memory_config_defaults() -> None:
    """测试 MemoryConfig 默认值。"""
    from novel2all.core.memory import MemoryConfig

    cfg = MemoryConfig()
    assert cfg.core_token_budget == 3000
    assert cfg.character_token_budget == 4000
    assert cfg.recent_chapter_count == 5
    assert cfg.recent_token_budget == 6000
    assert cfg.event_top_k == 8
    assert cfg.event_token_budget == 5000
    assert cfg.auto_extract_after_write is True
    assert cfg.auto_embed_after_write is True
    assert cfg.pre_write_check_blocking is True
