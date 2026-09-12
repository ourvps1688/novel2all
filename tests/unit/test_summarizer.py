"""ChapterSummarizer 单元测试。

测试目标：
- 档位划分（tier_of / bucket_of）
- 单章 extractive 摘要（不调 LLM、可在沙箱内跑）
- 跨章压缩（无 LLM 降级路径）
- token 计数
- 摘要后 token 数明显下降（满足"≥50%"的工程目标）
"""

from __future__ import annotations

import pytest

from novel2all.core.memory.summarizer import (
    TIER1_THRESHOLD,
    TIER2_THRESHOLD,
    ChapterSummarizer,
    bucket_of,
    extractive_summary,
    tier_of,
)

# === 档位划分 ===


class TestTier:
    def test_tier1_chapters(self) -> None:
        assert tier_of(1) == 1
        assert tier_of(5) == 1
        assert tier_of(10) == 1

    def test_tier2_chapters(self) -> None:
        assert tier_of(11) == 2
        assert tier_of(20) == 2
        assert tier_of(30) == 2

    def test_tier3_chapters(self) -> None:
        assert tier_of(31) == 3
        assert tier_of(50) == 3
        assert tier_of(400) == 3

    def test_tier_boundary(self) -> None:
        assert tier_of(TIER1_THRESHOLD - 1) == 1
        assert tier_of(TIER1_THRESHOLD) == 2
        assert tier_of(TIER2_THRESHOLD - 1) == 2
        assert tier_of(TIER2_THRESHOLD) == 3


class TestBucket:
    def test_tier1_single_chapter_bucket(self) -> None:
        assert bucket_of(1) == (1, 1)
        assert bucket_of(10) == (10, 10)

    def test_tier2_5_chapter_buckets(self) -> None:
        assert bucket_of(11) == (11, 11)  # 桶首
        assert bucket_of(15) == (11, 15)
        assert bucket_of(16) == (16, 16)  # 桶首
        assert bucket_of(20) == (16, 20)
        assert bucket_of(30) == (26, 30)

    def test_tier3_10_chapter_buckets(self) -> None:
        assert bucket_of(31) == (31, 31)  # 桶首
        assert bucket_of(40) == (31, 40)
        assert bucket_of(41) == (41, 41)  # 桶首
        assert bucket_of(100) == (91, 100)


# === Extractive 摘要 ===

SAMPLE_CHAPTER = """景和三年春，苍茫镇外的桃花开得正盛。林雷出生在一个普通的农户家中，父亲是镇上的铁匠，母亲早逝。
自幼林雷便展现出异于常人的聪慧，三岁能识千字，五岁便能背诵家传功法。村中老人皆言此子将来必成大器。
然而命运多舛，林雷六岁那年，村子遭逢大旱。父亲带着他背井离乡，一路上风餐露宿，艰难度日。
十二岁时，林雷流浪至青云宗山脚下，被外出采药的长老发现其资质惊人，遂收入门下。在青云宗，林雷如饥似渴地修炼，
日夜不辍。三年时间，便从外门弟子晋升为内门精英。宗内大比之日，林雷一剑破开九重天象，震惊全宗。
此后林雷声名远播，引来各方势力关注。一日，神秘老者来访，赠予林雷一枚古朴玉佩，言道：此物关乎你身世之谜，切记珍藏。
林雷接过玉佩，只觉一股温热从掌心传来，仿佛有什么力量在体内苏醒。他心中暗暗发誓，定要查明真相，不负老者厚望。
是夜，林雷闭关修炼，试图感应玉佩中的奥秘。月光透过窗棂洒落，他盘膝而坐，心如止水。
忽然，一道金光从玉佩中激射而出，直冲林雷眉心。他猛然睁眼，只见眼前浮现出一幅古老的画卷——那是上古神族的辉煌历史。
原来，林雷竟是上古神族后裔，体内流淌着神族血脉。这血脉沉睡了千年，今朝终于觉醒。"""


class TestExtractiveSummary:
    def test_short_text_returns_full(self) -> None:
        text = "第一句。第二句。第三句。"
        result = extractive_summary(text, max_sentences=5)
        assert "第一句" in result
        assert "第二句" in result
        assert "第三句" in result

    def test_long_text_extracts_key_sentences(self) -> None:
        result = extractive_summary(SAMPLE_CHAPTER, max_sentences=4)
        # 首句应保留
        assert "林雷出生" in result
        # 末句应保留
        assert "觉醒" in result
        # 总长应远小于原文
        assert len(result) < len(SAMPLE_CHAPTER)

    def test_keyword_sentence_picked(self) -> None:
        """高频关键词所在句子应被优先保留。"""
        # 文本里"玉佩"出现多次，让 max_sentences 足够大以容纳
        text = "无关首句。" * 5 + "玉佩的秘密在于血脉。" + "无关末句。" * 5
        result = extractive_summary(text, max_sentences=5)
        assert "玉佩" in result

    def test_empty_input(self) -> None:
        assert extractive_summary("") == ""

    def test_single_sentence(self) -> None:
        result = extractive_summary("孤句。")
        assert "孤句" in result


# === Summarizer 主体 ===


class TestChapterSummarizer:
    @pytest.fixture
    def summarizer(self) -> ChapterSummarizer:
        return ChapterSummarizer()

    def test_summarize_chapter_returns_string(self, summarizer: ChapterSummarizer) -> None:
        result = summarizer.summarize_chapter(SAMPLE_CHAPTER)
        assert isinstance(result, str)
        assert len(result) > 0
        assert len(result) < len(SAMPLE_CHAPTER)

    def test_summarize_chapter_empty(self, summarizer: ChapterSummarizer) -> None:
        assert summarizer.summarize_chapter("") == ""
        assert summarizer.summarize_chapter("   \n  ") == ""

    def test_summarize_chapter_truncates_long_output(self, summarizer: ChapterSummarizer) -> None:
        # 强制超长
        long_text = "。".join([f"第{i}句话包含一些内容" for i in range(100)])
        result = summarizer.summarize_chapter(long_text)
        assert len(result) <= summarizer.target_max_chars + 5  # 允许省略号

    def test_count_tokens(self, summarizer: ChapterSummarizer) -> None:
        assert summarizer.count_tokens("hello") >= 1
        assert summarizer.count_tokens("你好世界") >= 1

    @pytest.mark.asyncio
    async def test_compress_range_no_llm_fallback(self, summarizer: ChapterSummarizer) -> None:
        """llm=None 时压缩不应报错。"""
        summaries = {
            11: "林雷觉醒血脉。",
            12: "林雷结识苏寒。",
            13: "苏寒背叛。",
            14: "追逐战斗。",
            15: "林雷胜利。",
        }
        result = await summarizer.compress_range((11, 15), summaries, llm=None)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_compress_range_single_chapter(self, summarizer: ChapterSummarizer) -> None:
        result = await summarizer.compress_range((5, 5), {5: "单章"}, llm=None)
        assert result == "单章"

    @pytest.mark.asyncio
    async def test_compress_range_empty(self, summarizer: ChapterSummarizer) -> None:
        result = await summarizer.compress_range((1, 5), {}, llm=None)
        assert result == ""

    def test_token_reduction_meets_target(self, summarizer: ChapterSummarizer) -> None:
        """摘要后 token 数相比原文应下降 ≥ 50%（V0.21 工程目标）。"""
        original_tokens = summarizer.count_tokens(SAMPLE_CHAPTER)
        summary = summarizer.summarize_chapter(SAMPLE_CHAPTER)
        summary_tokens = summarizer.count_tokens(summary)
        reduction = 1 - (summary_tokens / original_tokens)
        assert reduction >= 0.5, (
            f"摘要压缩率 {reduction:.1%} 未达 50% 目标 "
            f"({summary_tokens} / {original_tokens} tokens)"
        )
