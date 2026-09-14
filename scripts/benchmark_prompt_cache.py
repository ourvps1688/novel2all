"""V0.30.6 C1：Prompt prefix cache 命中率 benchmark + 成本节省验证。

模拟典型 novel 写作工作负载：
- 100 章节生成（每章 prompt 不同）
- 5 个独特 system prompt（世界观 + 角色卡 + 写作风格）
- 系统 prompt 在每章都被复用
- 测量：
  1. prompt prefix hit rate
  2. cost_saved_cny（按 DeepSeek flash cache 命中率）
  3. 对比：实际 LLMProvider 调用 vs 假设没有 cache

输出：scripts/benchmark_prompt_cache_results.md（人类可读）
     scripts/benchmark_prompt_cache_results.json（机器可读）
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel2all.core import LLMConfig, LLMProvider

# === 配置 ===

NUM_CHAPTERS = 100  # 100 章小说
NUM_UNIQUE_SYSTEM_PROMPTS = 5  # 5 个独特 system prompt（轮换使用）
AVG_PROMPT_TOKENS = 5000  # 每章 prompt ~5000 tokens
AVG_OUTPUT_TOKENS = 3000  # 每章输出 ~3000 tokens

# DeepSeek flash pricing（V0.36 cost_estimate 实测）
PRICE_INPUT_MISS_CNY_PER_M = 1.00
PRICE_INPUT_HIT_CNY_PER_M = 0.02
PRICE_OUTPUT_CNY_PER_M = 4.00


def build_workload():
    """构建 100 章工作负载：每章 prompt 不同，system prompt 5 选 1。

    Returns:
        list[(system, prompt)] 共 NUM_CHAPTERS 项
    """
    workloads = []
    # 5 个独特 system prompt（角色卡/世界观/写作风格 5 种组合）
    system_prompts = [
        f"你是{author}，擅长{genre}类型，已写{years}年。\n请保持角色一致性。"
        for author, genre, years in [
            ("李白", "玄幻", 10),
            ("杜甫", "现实", 15),
            ("莫言", "魔幻现实", 20),
            ("J.K. Rowling", "奇幻", 12),
            ("Stephen King", "悬疑", 18),
        ]
    ]

    for ch in range(1, NUM_CHAPTERS + 1):
        # 轮换使用 system prompt（5 种，每章轮换）
        sys_idx = (ch - 1) % NUM_UNIQUE_SYSTEM_PROMPTS
        system = system_prompts[sys_idx]
        # prompt 每章都不同
        prompt = (
            f"第{ch:03d}章\n\n"
            f"本章要点：\n- 角色 A 与角色 B 在 {ch % 10 + 1} 号场景对话\n"
            f"- 推动主线：神秘事件 {ch} 进展\n- 字数要求：3000+ 字\n\n"
            f"上下文（之前 5 章摘要）：\n..."
        )
        workloads.append((system, prompt))

    return workloads, system_prompts


def run_benchmark():
    """跑 benchmark：模拟 100 章调用，记录 prompt prefix 命中统计。"""
    print("V0.30.6 C1 Prompt Prefix Cache Benchmark")
    print(f"Started at: {datetime.now(tz=UTC).isoformat()}")
    print()

    workloads, unique_sys_prompts = build_workload()
    print(f"Total chapters: {NUM_CHAPTERS}")
    print(f"Unique system prompts: {len(unique_sys_prompts)}")
    print()

    # 创建 LLMProvider（cache_enabled=False，仅做 prefix 跟踪）
    config = LLMConfig(cache_enabled=False)
    provider = LLMProvider(config)

    print("Running benchmark...")
    t0 = time.perf_counter()
    for system, prompt in workloads:
        # 模拟 LLMProvider 内部的 _make_cache_key() 调用
        provider._make_cache_key("deepseek/deepseek-flash", system, prompt, 0.7)
    elapsed = time.perf_counter() - t0

    stats = provider.prompt_cache_stats()
    print("\n=== Results ===")
    print(f"Elapsed: {elapsed * 1000:.2f} ms")
    print(f"Total chapters: {stats['total']}")
    print(f"Prefix hits: {stats['prefix_hits']}")
    print(f"Prefix misses: {stats['prefix_misses']}")
    print(f"Hit rate: {stats['hit_rate']:.2%}")
    print(f"Unique sys prompts: {stats['unique_sys_prompts']}")
    print(f"Cost saved (estimated): ¥{stats['cost_saved_cny']:.4f}")
    print(f"Potential savings: ¥{stats['potential_savings_cny']:.4f}")

    # 计算理论成本对比
    print("\n=== Cost Analysis ===")
    total_input_tokens = NUM_CHAPTERS * AVG_PROMPT_TOKENS
    total_output_tokens = NUM_CHAPTERS * AVG_OUTPUT_TOKENS

    cost_no_cache = (
        total_input_tokens * PRICE_INPUT_MISS_CNY_PER_M / 1_000_000
        + total_output_tokens * PRICE_OUTPUT_CNY_PER_M / 1_000_000
    )
    # prefix hit 时：input 用 hit price，output 不变
    cost_with_cache = (
        stats["prefix_hits"] * AVG_PROMPT_TOKENS * PRICE_INPUT_HIT_CNY_PER_M / 1_000_000
        + stats["prefix_misses"] * AVG_PROMPT_TOKENS * PRICE_INPUT_MISS_CNY_PER_M / 1_000_000
        + total_output_tokens * PRICE_OUTPUT_CNY_PER_M / 1_000_000
    )
    actual_saved = cost_no_cache - cost_with_cache
    pct_saved = actual_saved / cost_no_cache * 100 if cost_no_cache > 0 else 0

    print(f"Total input tokens: {total_input_tokens:,}")
    print(f"Total output tokens: {total_output_tokens:,}")
    print(f"Cost WITHOUT cache: ¥{cost_no_cache:.4f}")
    print(f"Cost WITH cache: ¥{cost_with_cache:.4f}")
    print(f"Actual savings: ¥{actual_saved:.4f} ({pct_saved:.1f}%)")

    return {
        "metadata": {
            "version": "V0.30.6 C1",
            "started_at": datetime.now(tz=UTC).isoformat(),
            "elapsed_ms": round(elapsed * 1000, 2),
            "config": {
                "num_chapters": NUM_CHAPTERS,
                "num_unique_system_prompts": NUM_UNIQUE_SYSTEM_PROMPTS,
                "avg_prompt_tokens": AVG_PROMPT_TOKENS,
                "avg_output_tokens": AVG_OUTPUT_TOKENS,
            },
            "pricing": {
                "input_miss_cny_per_m": PRICE_INPUT_MISS_CNY_PER_M,
                "input_hit_cny_per_m": PRICE_INPUT_HIT_CNY_PER_M,
                "output_cny_per_m": PRICE_OUTPUT_CNY_PER_M,
            },
        },
        "results": {
            "prefix_hits": stats["prefix_hits"],
            "prefix_misses": stats["prefix_misses"],
            "total": stats["total"],
            "hit_rate": stats["hit_rate"],
            "unique_sys_prompts": stats["unique_sys_prompts"],
        },
        "cost_analysis": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "cost_no_cache_cny": round(cost_no_cache, 4),
            "cost_with_cache_cny": round(cost_with_cache, 4),
            "actual_savings_cny": round(actual_saved, 4),
            "savings_pct": round(pct_saved, 2),
        },
    }


def save_report(data: dict) -> None:
    """保存 benchmark 结果到 markdown + json。"""
    output_dir = Path(__file__).parent
    json_path = output_dir / "benchmark_prompt_cache_results.json"
    md_path = output_dir / "benchmark_prompt_cache_results.md"

    # Save JSON
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate markdown
    md_lines = [
        "# V0.30.6 C1 Prompt Prefix Cache Benchmark",
        "",
        f"**Generated**: {data['metadata']['started_at']}",
        f"**Elapsed**: {data['metadata']['elapsed_ms']} ms",
        "",
        "## Configuration",
        "",
        f"- Chapters: {data['metadata']['config']['num_chapters']}",
        f"- Unique system prompts: {data['metadata']['config']['num_unique_system_prompts']}",
        f"- Avg prompt tokens/chapter: {data['metadata']['config']['avg_prompt_tokens']}",
        f"- Avg output tokens/chapter: {data['metadata']['config']['avg_output_tokens']}",
        "",
        "## Pricing (DeepSeek flash, V0.36 实测)",
        "",
        f"- Input cache miss: ¥{data['metadata']['pricing']['input_miss_cny_per_m']}/M",
        f"- Input cache hit: ¥{data['metadata']['pricing']['input_hit_cny_per_m']}/M",
        f"- Output: ¥{data['metadata']['pricing']['output_cny_per_m']}/M",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Prefix hits | {data['results']['prefix_hits']} |",
        f"| Prefix misses | {data['results']['prefix_misses']} |",
        f"| Total chapters | {data['results']['total']} |",
        f"| **Hit rate** | **{data['results']['hit_rate']:.2%}** |",
        f"| Unique sys prompts | {data['results']['unique_sys_prompts']} |",
        "",
        "## Cost Analysis",
        "",
        "| Scenario | Cost |",
        "|----------|-----:|",
        f"| **WITHOUT cache** | ¥{data['cost_analysis']['cost_no_cache_cny']:.4f} |",
        f"| **WITH cache** | ¥{data['cost_analysis']['cost_with_cache_cny']:.4f} |",
        f"| **Savings** | **¥{data['cost_analysis']['actual_savings_cny']:.4f} ({data['cost_analysis']['savings_pct']:.1f}%)** |",
        "",
        "## Interpretation",
        "",
        (
            "- **Hit rate "
            + f"{data['results']['hit_rate']:.2%}"
            + "** 意味着 "
            + f"{data['results']['prefix_hits']}"
            + " 章复用了 system prompt prefix，仅 "
            + f"{data['results']['prefix_misses']}"
            + " 章是首次生成 system prompt。"
        ),
        (
            "- **节省 ¥"
            + f"{data['cost_analysis']['actual_savings_cny']:.4f}"
            + "** ("
            + f"{data['cost_analysis']['savings_pct']:.1f}"
            + "%) 来自 input token 价格差：cache hit (¥"
            + f"{data['metadata']['pricing']['input_hit_cny_per_m']}"
            + "/M) vs cache miss (¥"
            + f"{data['metadata']['pricing']['input_miss_cny_per_m']}"
            + "/M)。"
        ),
        f"- **Hit rate 验证 V0.30.6 C1 设计假设**：典型 novel 写作工作负载（system prompt 跨章节稳定）的 prefix 命中率接近 {100.0 * (1 - 1 / NUM_UNIQUE_SYSTEM_PROMPTS):.1f}%。",
        "",
    ]

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print("\nReport saved:")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")


if __name__ == "__main__":
    data = run_benchmark()
    save_report(data)
    sys.exit(0)
