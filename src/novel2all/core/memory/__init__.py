"""novel2all 长记忆系统。

解决 LLM 长篇写作中的 context window 限制：
- L1: 核心设定（永远加载）
- L2: 角色状态（按需加载）
- L3: 最近章节摘要（滑动窗口 + 早期压缩）
- L4: 事件检索（向量检索 + 降级）
- L5: 知识图谱（tool call 查询，v0.22+）

v0.21 升级：
- L3：早期章节按档位压缩（1-10 全量、11-30 每5章、31+ 每10章）
- L4：chromadb 语义检索 + TF-IDF + keyword 三层降级

配套机制：
- pre-write 一致性检查（blocking 严重冲突）
- post-write 自动提取 + 更新 tracking + 自动入库事件
- 写中流式校验
"""

from novel2all.core.memory.extractor import ExtractedChapterInfo, Extractor
from novel2all.core.memory.manager import MemoryManager
from novel2all.core.memory.retriever import MemoryRetriever, RetrievedEvent
from novel2all.core.memory.summarizer import (
    ChapterSummarizer,
    bucket_of,
    extractive_summary,
    tier_of,
)
from novel2all.core.memory.tracker import Tracker
from novel2all.core.memory.types import (
    MemoryConfig,
    MemoryContext,
    MemoryItem,
    MemoryLayer,
)
from novel2all.core.memory.verifier import ConsistencyIssue, Verifier

__all__ = [
    "ChapterSummarizer",
    "ConsistencyIssue",
    "ExtractedChapterInfo",
    "Extractor",
    "MemoryConfig",
    "MemoryContext",
    "MemoryItem",
    "MemoryLayer",
    "MemoryManager",
    "MemoryRetriever",
    "RetrievedEvent",
    "Tracker",
    "Verifier",
    "bucket_of",
    "extractive_summary",
    "tier_of",
]
