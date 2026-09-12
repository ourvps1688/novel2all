"""novel2all 长记忆系统。

解决 LLM 长篇写作中的 context window 限制：
- L1: 核心设定（永远加载）
- L2: 角色状态（按需加载）
- L3: 最近章节摘要（滑动窗口）
- L4: 事件检索（向量检索）
- L5: 知识图谱（tool call 查询）

配套机制：
- pre-write 一致性检查（blocking 严重冲突）
- post-write 自动提取 + 更新 tracking
- 写中流式校验
"""

from novel2all.core.memory.extractor import ExtractedChapterInfo, Extractor
from novel2all.core.memory.manager import MemoryManager
from novel2all.core.memory.tracker import Tracker
from novel2all.core.memory.types import (
    MemoryConfig,
    MemoryContext,
    MemoryItem,
    MemoryLayer,
)
from novel2all.core.memory.verifier import ConsistencyIssue, Verifier

__all__ = [
    "ConsistencyIssue",
    "ExtractedChapterInfo",
    "Extractor",
    "MemoryConfig",
    "MemoryContext",
    "MemoryItem",
    "MemoryLayer",
    "MemoryManager",
    "Tracker",
    "Verifier",
]
