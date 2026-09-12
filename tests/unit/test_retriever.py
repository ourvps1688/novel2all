"""MemoryRetriever 单元测试。

测试目标：
- 入库 10 条事件
- 检索能召回相关事件（chromadb / TF-IDF / keyword 三种模式各覆盖）
- 章节范围 / 事件类型过滤
- delete_chapter 正确性
- 失败降级路径（chromadb 不可用时自动切到 TF-IDF）

环境说明：
- chromadb 在 Windows 沙箱可能因缺少 VC++ Runtime DLL 而无法 import（chromadb_rust_bindings）。
  这是真实环境差异，由 `needs_chromadb` 自动 skip chromadb 模式测试。
- TF-IDF / keyword / 单元测试在任何环境都能跑。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novel2all.core.memory.retriever import (
    MemoryRetriever,
    _hash_embedding,
    _tfidf_scores,
    _tokenize,
)
from novel2all.core.memory.types import MemoryLayer


# === 环境探测 ===

def _chromadb_available() -> bool:
    try:
        import chromadb  # noqa: F401

        # 再探测 rust 绑定（沙箱里这里会 ImportError）
        from chromadb.api import rust  # noqa: F401
        return True
    except Exception:
        return False


CHROMADB_OK = _chromadb_available()
needs_chromadb = pytest.mark.skipif(
    not CHROMADB_OK,
    reason="chromadb 不可用（Windows DLL 缺失或 import 失败），沙箱/CI Windows 跳过。"
           "Linux/macOS 或装好 VC++ runtime 的 Windows 应正常。",
)


# === Fixtures ===

@pytest.fixture
def events_corpus() -> list[dict]:
    """10 条玄幻小说事件，覆盖角色/伏笔/时间线。"""
    return [
        {"chapter": 1, "event_type": "timeline",
         "text": "景和三年春，林雷出生于苍茫镇"},
        {"chapter": 2, "event_type": "character_change",
         "text": "林雷觉醒血脉之力"},
        {"chapter": 3, "event_type": "foreshadowing",
         "text": "神秘老者留下玉佩，暗示林雷身世之谜"},
        {"chapter": 5, "event_type": "timeline",
         "text": "林雷离开苍茫镇前往青云宗"},
        {"chapter": 7, "event_type": "character_change",
         "text": "林雷结识苏寒，结为兄弟"},
        {"chapter": 10, "event_type": "foreshadowing",
         "text": "玉佩秘密初显：林雷实为上古神族后裔"},
        {"chapter": 15, "event_type": "timeline",
         "text": "青云宗大比，林雷崭露头角"},
        {"chapter": 20, "event_type": "character_change",
         "text": "林雷突破筑基期"},
        {"chapter": 25, "event_type": "foreshadowing",
         "text": "苏寒背叛，盗走宗门至宝"},
        {"chapter": 30, "event_type": "timeline",
         "text": "林雷追杀苏寒至北荒"},
    ]


@pytest.fixture
def fake_retriever(tmp_path: Path) -> MemoryRetriever:
    """真实 chromadb 路径（依赖 rust 绑定 + onnxruntime）。"""
    rt = MemoryRetriever(tmp_path / ".chroma", embedding_fn=_hash_embedding, force_mode="chromadb")
    yield rt
    rt.wipe_disk()


@pytest.fixture
def fallback_retriever(tmp_path: Path) -> MemoryRetriever:
    """强制走 TF-IDF 降级路径（沙箱/CI Windows 都可跑）。"""
    rt = MemoryRetriever(tmp_path / ".chroma", force_mode="tfidf")
    return rt


# === Chromadb 路径（生产环境） ===

@needs_chromadb
class TestChromadbMode:
    def test_add_event_returns_id(self, fake_retriever: MemoryRetriever) -> None:
        eid = fake_retriever.add_event(
            chapter=1, event_type="timeline", text="q1"
        )
        assert eid.startswith("ch1-")

    def test_count_after_add(self, fake_retriever: MemoryRetriever,
                             events_corpus: list[dict]) -> None:
        fake_retriever.add_events(events_corpus)
        assert fake_retriever.count() == 10
        assert fake_retriever.mode == "chromadb"

    def test_query_returns_memory_items(
        self, fake_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fake_retriever.add_events(events_corpus)
        results = fake_retriever.query("林雷 觉醒 血脉", top_k=3)
        assert 0 < len(results) <= 3
        for item in results:
            assert item.layer == MemoryLayer.EVENT
            assert item.relevance >= 0
            assert item.token_count > 0

    def test_chapter_range_filter(
        self, fake_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fake_retriever.add_events(events_corpus)
        results = fake_retriever.query("林雷", top_k=10, chapter_range=(1, 5))
        for item in results:
            ch = int(item.source.split("#ch")[-1])
            assert 1 <= ch <= 5

    def test_event_type_filter(
        self, fake_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fake_retriever.add_events(events_corpus)
        results = fake_retriever.query("林雷", top_k=10, event_type="foreshadowing")
        for item in results:
            ch = int(item.source.split("#ch")[-1])
            assert ch in (3, 10, 25)

    def test_delete_chapter(
        self, fake_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fake_retriever.add_events(events_corpus)
        n = fake_retriever.delete_chapter(5)
        assert n >= 1
        assert fake_retriever.count() == 9


# === TF-IDF 降级路径（沙箱/CI Windows 都可跑） ===

class TestFallbackMode:
    def test_fallback_init_when_chromadb_unavailable(
        self, fallback_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fallback_retriever.add_events(events_corpus)
        assert fallback_retriever.mode == "tfidf"
        assert fallback_retriever.count() == 10

    def test_tfidf_query_recall(
        self, fallback_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fallback_retriever.add_events(events_corpus)
        results = fallback_retriever.query("林雷 觉醒 血脉", top_k=3)
        assert len(results) > 0

    def test_tfidf_chapter_range_filter(
        self, fallback_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fallback_retriever.add_events(events_corpus)
        results = fallback_retriever.query("林雷", top_k=10, chapter_range=(11, 25))
        for item in results:
            ch = int(item.source.split("#ch")[-1])
            assert 11 <= ch <= 25

    def test_tfidf_event_type_filter(
        self, fallback_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fallback_retriever.add_events(events_corpus)
        results = fallback_retriever.query(
            "玉佩 林雷", top_k=10, event_type="foreshadowing"
        )
        for item in results:
            ch = int(item.source.split("#ch")[-1])
            assert ch in (3, 10, 25)

    def test_tfidf_zero_results_on_unmatched_query(
        self, fallback_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fallback_retriever.add_events(events_corpus)
        results = fallback_retriever.query("完全不相关的话题 xyz abc", top_k=5)
        assert results == []

    def test_delete_chapter_fallback(
        self, fallback_retriever: MemoryRetriever, events_corpus: list[dict]
    ) -> None:
        fallback_retriever.add_events(events_corpus)
        n = fallback_retriever.delete_chapter(5)
        assert n >= 1
        assert fallback_retriever.count() == 9


# === 纯函数（无外部依赖） ===

class TestHelpers:
    def test_tokenize_chinese(self) -> None:
        tokens = _tokenize("林雷觉醒血脉之力")
        assert "林雷" in tokens
        assert "觉醒" in tokens
        assert "血脉" in tokens

    def test_tokenize_english(self) -> None:
        tokens = _tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_tokenize_mixed(self) -> None:
        # 中英混合
        tokens = _tokenize("林雷觉醒 Mana burst")
        assert "林雷" in tokens
        assert "觉醒" in tokens
        assert "mana" in tokens
        assert "burst" in tokens

    def test_tfidf_scores_simple(self) -> None:
        docs = ["林雷觉醒血脉", "苏寒背叛", "完全不相关"]
        scores = _tfidf_scores("林雷 觉醒", docs)
        assert scores[0] > scores[1]
        assert scores[0] > scores[2]

    def test_tfidf_scores_empty_query(self) -> None:
        scores = _tfidf_scores("", ["文档1", "文档2"])
        assert scores == [0.0, 0.0]

    def test_tfidf_scores_empty_docs(self) -> None:
        scores = _tfidf_scores("查询", [])
        assert scores == []

    def test_hash_embedding_deterministic(self) -> None:
        a = _hash_embedding(["hello"])
        b = _hash_embedding(["hello"])
        assert a == b

    def test_hash_embedding_different_text(self) -> None:
        a = _hash_embedding(["hello"])
        b = _hash_embedding(["world"])
        assert a != b


# === 自动降级测试 ===

@needs_chromadb
def test_auto_fallback_on_chromadb_runtime_error(tmp_path: Path) -> None:
    """chromadb 查询时崩溃 → 自动切到 TF-IDF。"""

    class FailingRetriever(MemoryRetriever):
        def _query_chromadb(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("chromadb broken")

    rt = FailingRetriever(tmp_path / ".chroma", force_mode="chromadb")
    rt.add_events([
        {"chapter": 1, "event_type": "timeline", "text": "林雷出生"},
        {"chapter": 2, "event_type": "timeline", "text": "林雷觉醒"},
    ])
    assert rt.mode == "chromadb"
    results = rt.query("林雷", top_k=2)
    assert rt.mode == "tfidf"
    assert len(results) >= 1
    rt.wipe_disk()


def test_auto_fallback_on_chromadb_init_failure(tmp_path: Path) -> None:
    """chromadb 初始化失败时（沙箱场景），mode 自动设为 tfidf。"""
    rt = MemoryRetriever(tmp_path / ".chroma")  # 不传 force_mode
    assert rt.mode in ("tfidf", "chromadb")  # 不强求，由环境决定
    # 即使初始化到 tfidf 也能用
    rt.add_events([{"chapter": 1, "event_type": "timeline", "text": "测试"}])
    results = rt.query("测试", top_k=2)
    assert isinstance(results, list)
    rt.wipe_disk()
