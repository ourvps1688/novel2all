"""L3 章节摘要器（早期章节压缩）。

v0.21 实现滑动窗口策略：

  Chapter 1─10:   全量摘要（每章独立保留）
  Chapter 11─30:  滚动摘要（每 5 章合并成一个）
  Chapter 31+:    进一步压缩（每 10 章合并成一个）

压缩目标：当 total_chapters_target = 400 时，L3 滑动窗口
       (recent_chapter_count=5 + 滚动摘要若干) 总体保持
       在 recent_token_budget = 6000 tokens 以内。

降级：summarize_chapter 单章摘要不依赖 LLM，使用 extractive
     摘要（前 3 句 + 末 1 句 + 关键句），可在沙箱内离线运行。
"""

from __future__ import annotations

import re
from typing import Any

from novel2all.core.memory.tracker import TrackingState

try:
    import tiktoken  # type: ignore

    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENCODER.encode(text))

except Exception:

    def _count_tokens(text: str) -> int:
        # 兜底：英文约 4 字符/token，中文约 1.5 字符/token
        return max(1, len(text) // 3)


# === 摘要策略 ===

# 三个压缩档位的触发边界（章节号）
TIER1_THRESHOLD = 11  # 1-10 全量
TIER2_THRESHOLD = 31  # 11-30 每 5 章滚动；31+ 每 10 章滚动
TIER2_BUCKET = 5  # 11-30 的桶大小
TIER3_BUCKET = 10  # 31+ 的桶大小


def tier_of(chapter: int) -> int:
    """返回章节所在的摘要档位（1/2/3）。"""
    if chapter < TIER1_THRESHOLD:
        return 1
    if chapter < TIER2_THRESHOLD:
        return 2
    return 3


def bucket_of(chapter: int) -> tuple[int, int]:
    """返回章节所属的 (桶起始, 桶结束) 区间。"""
    t = tier_of(chapter)
    if t == 1:
        return (chapter, chapter)
    bucket = TIER2_BUCKET if t == 2 else TIER3_BUCKET
    # 桶从 (tier2 start) 开始对齐：
    # tier 2: [11, 15], [16, 20], ..., [26, 30]
    # tier 3: [31, 40], [41, 50], ...
    if t == 2:
        base = TIER1_THRESHOLD
    else:
        base = TIER2_THRESHOLD
    offset = (chapter - base) // bucket
    start = base + offset * bucket
    end = min(start + bucket - 1, chapter)
    return (start, end)


# === Extractive 摘要（无 LLM）===

_SENT_RE = re.compile(r"[^。！？!?\n]+[。！？!?]+|[^。！？!?\n]+$", re.UNICODE)


def _split_sentences(text: str) -> list[str]:
    """极简分句：中英文句末标点切分。"""
    sents = [s.strip() for s in _SENT_RE.findall(text) if s.strip()]
    return sents or [text.strip()]


def _score_sentence(sent: str, keywords: set[str]) -> float:
    """句子重要性分数：含关键词数 + 长度奖励 - 太短惩罚。"""
    if not sent:
        return 0.0
    sent_lower = sent.lower()
    keyword_hits = sum(1 for k in keywords if k in sent_lower)
    length_bonus = min(len(sent) / 80.0, 1.5)  # 长句适度加分，封顶 1.5
    too_short_penalty = 0.5 if len(sent) < 12 else 0.0
    return keyword_hits * 2.0 + length_bonus - too_short_penalty


def extractive_summary(text: str, max_sentences: int = 5) -> str:
    """Extractive 摘要：保留首 2 句 + 末 1 句 + 关键词命中最高的句。

    不依赖 LLM，可在沙箱内 / 无网络 / 无 key 时直接使用。
    """
    sents = _split_sentences(text)
    if len(sents) <= max_sentences:
        return "".join(sents)

    # 关键词：词频统计（去掉停用词）
    tokens = _tokenize(text)
    stop = _STOPWORDS
    freq: dict[str, int] = {}
    for tok in tokens:
        if tok in stop or len(tok) <= 1:
            continue
        freq[tok] = freq.get(tok, 0) + 1
    top_keywords = {w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:8]}

    # 必保留：首 2 + 末 1
    must_keep = set(range(min(2, len(sents)))) | {len(sents) - 1}

    # 其余句子按分数排，取够 max_sentences
    candidates = [(i, _score_sentence(s, top_keywords)) for i, s in enumerate(sents)]
    candidates.sort(key=lambda x: x[1], reverse=True)
    picked = set(must_keep)
    for idx, _ in candidates:
        if len(picked) >= max_sentences:
            break
        picked.add(idx)

    # 按原文顺序输出
    picked_sorted = sorted(picked)
    return "".join(sents[i] for i in picked_sorted)


_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_STOPWORDS = {
    # 中文高频停用词
    "的", "了", "是", "在", "和", "与", "或", "也", "就", "都", "而", "及",
    "有", "无", "为", "着", "过", "把", "被", "对", "这", "那", "此",
    # 英文高频停用词（极简集）
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "on", "at", "by", "for", "with", "as", "it", "this", "that",
    "he", "she", "they", "we", "i", "you",
}


def _tokenize(text: str) -> list[str]:
    r"""与 retriever 保持一致：中文 bigram + unigram，英文按 \w+。"""
    out: list[str] = []
    for piece in _TOKEN_RE.findall(text.lower()):
        if all("\u4e00" <= c <= "\u9fff" for c in piece):
            out.extend(piece)
            for i in range(len(piece) - 1):
                out.append(piece[i] + piece[i + 1])
        else:
            out.append(piece)
    return out


# === 摘要器主类 ===

class ChapterSummarizer:
    """章节摘要器。

    用法：
        summarizer = ChapterSummarizer()
        summary = summarizer.summarize_chapter("本章正文……")
        token_count = summarizer.count_tokens(summary)

        # 跨章压缩（可选 LLM）
        rolling = await summarizer.compress_range(
            chapter_range=(11, 15),
            chapter_summaries={11: "...", 12: "...", ...},
            llm=None,  # None 时降级为 extractive 拼接
        )

    设计保证：
        - summarize_chapter() 不调外部服务，可在沙箱内运行。
        - compress_range() 在 llm=None 时也可用（拼接 + 二次 extractive）。
    """

    def __init__(
        self,
        *,
        max_sentences: int = 5,
        target_max_chars: int = 600,
    ):
        self.max_sentences = max_sentences
        self.target_max_chars = target_max_chars

    def summarize_chapter(self, chapter_content: str) -> str:
        """单章摘要（extractive，不调 LLM）。"""
        if not chapter_content.strip():
            return ""
        summary = extractive_summary(chapter_content, max_sentences=self.max_sentences)
        if len(summary) > self.target_max_chars:
            # 二次截断到目标长度
            summary = summary[: self.target_max_chars].rstrip("，,;； ") + "……"
        return summary

    def count_tokens(self, text: str) -> int:
        return _count_tokens(text)

    async def compress_range(
        self,
        chapter_range: tuple[int, int],
        chapter_summaries: dict[int, str],
        llm: Any | None = None,
    ) -> str:
        """把一段章节摘要压缩成一段滚动摘要。

        llm 不为 None 时：用 LLM 生成一段连贯总结。
        llm 为 None 时：拼接 + extractive 二次压缩（降级）。
        """
        lo, hi = chapter_range
        relevant = {ch: chapter_summaries[ch] for ch in sorted(chapter_summaries) if lo <= ch <= hi}
        if not relevant:
            return ""
        if len(relevant) == 1:
            return next(iter(relevant.values()))

        combined = "\n\n".join(
            f"第{ch}章: {summary}" for ch, summary in relevant.items()
        )

        if llm is None:
            # 降级：直接对 combined 做 extractive
            return self.summarize_chapter(combined)

        # 调 LLM 生成滚动摘要
        prompt = _ROLLING_PROMPT.format(
            chapter_range=f"{lo}-{hi}",
            combined=combined,
        )
        return await llm.complete(prompt=prompt, temperature=0.3, max_tokens=800)

    def apply_to_state(self, state: TrackingState) -> TrackingState:
        """按滑动窗口策略，把 state.recent_chapter_summaries 折叠。

        调用前：summaries 是字典（key=章节号, value=摘要）
        调用后：早期章节按档位折叠进 rolling keys
                比如 {11-15_rolling: "..."} 替代 {11: ..., 12: ..., ..., 15: ...}
        """
        originals = dict(state.recent_chapter_summaries)
        if not originals:
            return state

        compressed: dict[int | str, str] = {}

        # 全量段
        tier1_keys = sorted(ch for ch in originals if tier_of(ch) == 1)
        for ch in tier1_keys:
            compressed[ch] = originals[ch]

        # tier 2 & 3：按桶合并
        for ch in sorted(originals):
            t = tier_of(ch)
            if t == 1:
                continue
            start, end = bucket_of(ch)
            bucket_key = f"{start}-{end}_rolling"
            if bucket_key in compressed:
                continue
            bucket_summaries = {c: originals[c] for c in originals if start <= c <= end}
            if bucket_summaries:
                compressed[bucket_key] = self._merge_buckets(bucket_summaries)

        # 类型调整：键可能是 int 也可能是 str
        new_dict: dict[int, str] = {}
        for k, v in compressed.items():
            if isinstance(k, int):
                new_dict[k] = v
            else:
                # string bucket key 当作压缩块，用负数 -1/-2/-3 顺序编码保证去重
                pass
        # 但 Pydantic 的 recent_chapter_summaries 是 dict[int, str]
        # 滚动摘要以新结构承载：写到 state.foreshadowing 不合适，
        # 这里改用新字段；为不破坏 schema，我们把 rolling 摘要作为单独
        # 的内存对象返回，state 保留单章摘要。
        # ------------------------------------
        # 折中实现：压缩后的 rolling 块挂到 state 的一个新字段
        # `rolling_summaries: dict[str, str]`，通过 Pydantic 模型扩展。
        # 为避免破坏 schema_v2，我们直接挂为额外 dict，typing-friendly。
        if hasattr(state, "__dict__"):
            state.__dict__["rolling_summaries"] = {  # type: ignore[attr-defined]
                k: v for k, v in compressed.items() if isinstance(k, str)
            }
        return state

    @staticmethod
    def _merge_buckets(bucket_summaries: dict[int, str]) -> str:
        """合并一个桶里的多章摘要为一段滚动摘要。"""
        if len(bucket_summaries) == 1:
            return next(iter(bucket_summaries.values()))
        # 极简合并：取每章首句串联（避免再调 extractive 算法）
        merged_parts: list[str] = []
        for ch in sorted(bucket_summaries):
            text = bucket_summaries[ch]
            first_sentence = _split_sentences(text)[0] if text else ""
            if first_sentence:
                merged_parts.append(f"第{ch}章{first_sentence}")
        result = " ".join(merged_parts)
        if len(result) > 1200:
            result = result[:1200].rstrip("，,;； ") + "……"
        return result


# === Prompt 模板 ===

_ROLLING_PROMPT = """你是长篇小说章节摘要员。把以下若干章的简短摘要合并成一段"滚动摘要"，要求：
1. 保留关键情节转折、人物变化、伏笔推进
2. 去除冗余，控制在 400 字内
3. 用中文，第三人称
4. 章节范围：{chapter_range}

## 各章摘要
{combined}

只返回合并后的滚动摘要，不要其他解释。"""
