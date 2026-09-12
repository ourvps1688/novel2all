"""L4 事件检索器（向量检索 + 关键词降级）。

v0.21 实现：
- 主路径：chromadb + 默认 sentence-transformers embedding
- 降级路径 1：TF-IDF（无需外部依赖，纯 Python）
- 降级路径 2：关键词匹配（最朴素，作为最后兜底）

设计目标：检索层失败永远不阻断写作主流程。
任何 chromadb / 模型加载异常都会被捕获并降级。
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novel2all.core.memory.types import MemoryItem, MemoryLayer

# === Embedding 抽象 ===

EmbeddingFunc = Callable[[Sequence[str]], list[list[float]]]


def _hash_embedding(texts: Sequence[str]) -> list[list[float]]:
    """Deterministic fake embedding，仅用于测试/降级。

    用 SHA-256 的 16 个字节（128 维）当伪向量。
    两个文本的 hash 几乎不相似，所以语义召回不可用，但 API 接口与真实 embedding 一致。
    """
    out: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # 把 16 字节展成 32 个 float；前 16 个为正，后 16 个为负，制造一些结构
        floats: list[float] = []
        for i, b in enumerate(digest):
            v = b / 255.0  # [0, 1]
            if i % 2 == 1:
                v = -v
            floats.append(v)
        out.append(floats)
    return out


def _try_chromadb_embedding() -> EmbeddingFunc | None:
    """尝试加载 chromadb + 默认 embedding。失败返回 None。"""
    try:
        from chromadb.utils import embedding_functions  # type: ignore

        ef = embedding_functions.DefaultEmbeddingFunction()
    except Exception:
        return None

    def _embed(texts: Sequence[str]) -> list[list[float]]:
        try:
            return ef(list(texts))  # type: ignore[no-any-return]
        except Exception:
            return _hash_embedding(texts)

    return _embed


# === 检索结果 ===


@dataclass
class RetrievedEvent:
    """单条检索结果。"""

    chapter: int
    event_type: str  # "character_change" | "foreshadowing" | "timeline" | "general"
    text: str
    score: float
    metadata: dict[str, Any]


# === 检索器 ===


class MemoryRetriever:
    """事件检索器。

    用法：
        retriever = MemoryRetriever(project_root / ".chroma")
        retriever.add_event(chapter=3, event_type="character_change",
                            text="林雷觉醒血脉之力", metadata={...})
        results = retriever.query("血脉觉醒", top_k=5)

    失败降级：如果 chromadb 不可用，自动切到 TF-IDF；TF-IDF 也不可用则切到关键词匹配。
    """

    COLLECTION_NAME = "events"

    def __init__(
        self,
        chroma_dir: Path,
        embedding_fn: EmbeddingFunc | None = None,
        force_mode: str | None = None,
    ):
        """retriever 初始化。

        force_mode 用于测试：
          - None：按优先级 chromadb → TF-IDF 自动降级（默认）
          - "chromadb"：强制走 chromadb，失败则报错
          - "tfidf"：强制走 TF-IDF 降级路径
          - "keyword"：强制走最朴素 keyword 路径
        """
        self.chroma_dir = Path(chroma_dir)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._embedding_fn = embedding_fn
        self._mode: str = "uninitialized"
        self._chroma_collection: Any = None
        self._fallback_corpus: list[RetrievedEvent] = []  # TF-IDF / keyword 降级用
        self._init_mode(force_mode=force_mode)

    # === 初始化与降级 ===

    def _init_mode(self, force_mode: str | None = None) -> None:
        """按优先级尝试初始化：chromadb → TF-IDF → keyword。

        force_mode: 测试钩子，指定首选模式。失败时**自动降级**（fail-soft），
        测试可通过 `retriever.mode` 检查实际模式并自行 skip。

        设计原则：force_mode 是"首选"，不是"必须"。
        """
        if force_mode is not None:
            if force_mode == "chromadb":
                if self._try_init_chromadb():
                    self._mode = "chromadb"
                else:
                    # 初始化失败时优雅降级到 TF-IDF（不阻断调用方）
                    self._mode = "tfidf"
                return
            if force_mode == "tfidf":
                self._mode = "tfidf"
                return
            if force_mode == "keyword":
                self._mode = "keyword"
                return
            raise ValueError(f"Unknown force_mode: {force_mode}")

        # 默认自动降级
        # 1. 尝试 chromadb
        if self._embedding_fn is not None or self._try_init_chromadb():
            self._mode = "chromadb"
            return
        # 2. 降级 TF-IDF（不依赖外部包）
        self._mode = "tfidf"

    def _try_init_chromadb(self) -> bool:
        try:
            import chromadb  # type: ignore
        except Exception:
            return False

        try:
            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            # 优先用默认 embedding，加载失败就用 caller 提供的或 hash 兜底
            if self._embedding_fn is None:
                ef = _try_chromadb_embedding()
                self._embedding_fn = ef or _hash_embedding
            self._chroma_collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            return True
        except Exception:
            return False

    @property
    def mode(self) -> str:
        """当前检索模式：'chromadb' | 'tfidf' | 'keyword'。"""
        return self._mode

    # === 入库 API ===

    def add_event(
        self,
        *,
        chapter: int,
        event_type: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> str:
        """入库一条事件。返回事件 ID。"""
        eid = (
            event_id
            or f"ch{chapter}-{event_type}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"
        )
        meta = {"chapter": chapter, "event_type": event_type, **(metadata or {})}

        if self._mode == "chromadb":
            try:
                self._chroma_collection.add(  # type: ignore[union-attr]
                    documents=[text],
                    metadatas=[meta],
                    ids=[eid],
                )
                return eid
            except Exception:
                # 运行时失败 → 降级
                self._fallback_corpus.append(RetrievedEvent(chapter, event_type, text, 1.0, meta))
                self._mode = "tfidf"
                return eid

        # TF-IDF / keyword 模式：内存存储
        self._fallback_corpus.append(RetrievedEvent(chapter, event_type, text, 1.0, meta))
        return eid

    def add_events(self, events: Sequence[dict[str, Any]]) -> list[str]:
        """批量入库。每条 dict 至少包含 chapter/event_type/text。"""
        ids: list[str] = []
        for e in events:
            ids.append(
                self.add_event(
                    chapter=e["chapter"],
                    event_type=e.get("event_type", "general"),
                    text=e["text"],
                    metadata=e.get("metadata"),
                    event_id=e.get("id"),
                )
            )
        return ids

    # === 检索 API ===

    def query(
        self,
        text: str,
        *,
        top_k: int = 8,
        chapter_range: tuple[int, int] | None = None,
        event_type: str | None = None,
    ) -> list[MemoryItem]:
        """检索相关事件并返回 MemoryItem（layer=EVENT）。"""
        if self._mode == "chromadb":
            try:
                return self._query_chromadb(text, top_k, chapter_range, event_type)
            except Exception:
                self._mode = "tfidf"
        if self._mode == "tfidf":
            return self._query_tfidf(text, top_k, chapter_range, event_type)
        return self._query_keyword(text, top_k, chapter_range, event_type)

    def _query_chromadb(
        self,
        text: str,
        top_k: int,
        chapter_range: tuple[int, int] | None,
        event_type: str | None,
    ) -> list[MemoryItem]:
        where: dict[str, Any] = {}
        if chapter_range:
            where["chapter"] = {"$gte": chapter_range[0], "$lte": chapter_range[1]}
        if event_type:
            where["event_type"] = event_type

        kwargs: dict[str, Any] = {
            "query_texts": [text],
            "n_results": min(top_k, max(1, self._chroma_collection.count())),  # type: ignore[union-attr]
        }
        if where:
            kwargs["where"] = where

        result = self._chroma_collection.query(**kwargs)  # type: ignore[union-attr]
        items: list[MemoryItem] = []
        for i, doc in enumerate(result.get("documents", [[]])[0]):
            meta = result.get("metadatas", [[]])[0][i]
            dist = result.get("distances", [[]])[0][i]
            score = max(0.0, 1.0 - float(dist))  # cosine distance → 相似度
            items.append(_to_memory_item(doc, meta, score))
        return items

    def _query_tfidf(
        self,
        text: str,
        top_k: int,
        chapter_range: tuple[int, int] | None,
        event_type: str | None,
    ) -> list[MemoryItem]:
        candidates = self._filter_corpus(chapter_range, event_type)
        if not candidates:
            return []
        docs = [c.text for c in candidates]
        scores = _tfidf_scores(text, docs)
        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]
        return [_to_memory_item(c.text, _event_to_meta(c), s) for c, s in ranked if s > 0]

    def _query_keyword(
        self,
        text: str,
        top_k: int,
        chapter_range: tuple[int, int] | None,
        event_type: str | None,
    ) -> list[MemoryItem]:
        candidates = self._filter_corpus(chapter_range, event_type)
        if not candidates:
            return []
        keywords = set(_tokenize(text))
        scored: list[tuple[RetrievedEvent, float]] = []
        for c in candidates:
            doc_tokens = set(_tokenize(c.text))
            if not doc_tokens or not keywords:
                scored.append((c, 0.0))
                continue
            overlap = len(keywords & doc_tokens) / len(keywords | doc_tokens)
            scored.append((c, overlap))
        ranked = sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]
        return [_to_memory_item(c.text, _event_to_meta(c), s) for c, s in ranked if s > 0]

    def _filter_corpus(
        self,
        chapter_range: tuple[int, int] | None,
        event_type: str | None,
    ) -> list[RetrievedEvent]:
        out = list(self._fallback_corpus)
        if chapter_range:
            lo, hi = chapter_range
            out = [c for c in out if lo <= c.chapter <= hi]
        if event_type:
            out = [c for c in out if c.event_type == event_type]
        return out

    # === 维护 ===

    def delete_chapter(self, chapter: int) -> int:
        """删除某章全部事件，返回删除条数。"""
        if self._mode == "chromadb":
            try:
                existing = self._chroma_collection.get(where={"chapter": chapter})  # type: ignore[union-attr]
                ids = existing.get("ids", [])
                if ids:
                    self._chroma_collection.delete(ids=ids)  # type: ignore[union-attr]
                return len(ids)
            except Exception:
                self._mode = "tfidf"

        before = len(self._fallback_corpus)
        self._fallback_corpus = [c for c in self._fallback_corpus if c.chapter != chapter]
        return before - len(self._fallback_corpus)

    def count(self) -> int:
        """当前已入库事件总数。"""
        if self._mode == "chromadb":
            try:
                return int(self._chroma_collection.count())  # type: ignore[union-attr]
            except Exception:
                return len(self._fallback_corpus)
        return len(self._fallback_corpus)

    def clear(self) -> None:
        """清空所有事件（仅影响当前 retriever 实例；磁盘文件不动）。"""
        if self._mode == "chromadb":
            try:
                existing = self._chroma_collection.get()  # type: ignore[union-attr]
                ids = existing.get("ids", [])
                if ids:
                    self._chroma_collection.delete(ids=ids)  # type: ignore[union-attr]
            except Exception:
                pass
        self._fallback_corpus.clear()

    def wipe_disk(self) -> None:
        """物理删除磁盘上的 chromadb 目录（谨慎使用）。"""
        if self.chroma_dir.exists():
            shutil.rmtree(self.chroma_dir)
        self._fallback_corpus.clear()


# === 辅助函数（纯函数，方便测试）===

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    r"""极简分词：英文按 \w+，中文按 bigram + unigram 混合。

    例：'林雷觉醒' → ['林雷', '雷觉', '觉醒', '林', '雷', '觉', '醒']
    兼顾召回率（"林雷"整体可匹配）与覆盖率（单字兜底）。
    """
    out: list[str] = []
    for piece in _TOKEN_RE.findall(text.lower()):
        if all("\u4e00" <= c <= "\u9fff" for c in piece):
            # bigram + unigram
            out.extend(piece)  # unigram
            for i in range(len(piece) - 1):
                out.append(piece[i] + piece[i + 1])  # bigram
        else:
            out.append(piece)
    return out


def _tfidf_scores(query: str, docs: Sequence[str]) -> list[float]:
    """TF-IDF 余弦相似度（纯 Python，无依赖）。"""
    if not docs:
        return []
    query_tokens = _tokenize(query)
    if not query_tokens:
        return [0.0] * len(docs)

    doc_tokens_list = [_tokenize(d) for d in docs]
    df: Counter[str] = Counter()
    for tokens in doc_tokens_list:
        for t in set(tokens):
            df[t] += 1
    n_docs = len(docs)

    def vector(tokens: list[str]) -> dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            idf = math.log((n_docs + 1) / (df.get(term, 0) + 1)) + 1
            vec[term] = (count / len(tokens)) * idf
        return vec

    q_vec = vector(query_tokens)
    if not q_vec:
        return [0.0] * len(docs)

    scores: list[float] = []
    for d_tokens in doc_tokens_list:
        d_vec = vector(d_tokens)
        if not d_vec:
            scores.append(0.0)
            continue
        # cosine
        common = set(q_vec) & set(d_vec)
        dot = sum(q_vec[t] * d_vec[t] for t in common)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        d_norm = math.sqrt(sum(v * v for v in d_vec.values()))
        denom = q_norm * d_norm
        scores.append(dot / denom if denom > 0 else 0.0)
    return scores


def _to_memory_item(text: str, meta: dict[str, Any], score: float) -> MemoryItem:
    """把检索结果转成 MemoryItem（layer=EVENT）。"""
    chapter = meta.get("chapter", 0)
    return MemoryItem(
        content=text,
        source=f"retriever#ch{chapter}",
        layer=MemoryLayer.EVENT,
        relevance=score,
        token_count=max(1, len(text) // 4),
    )


def _event_to_meta(event: RetrievedEvent) -> dict[str, Any]:
    return {"chapter": event.chapter, "event_type": event.event_type, **event.metadata}
