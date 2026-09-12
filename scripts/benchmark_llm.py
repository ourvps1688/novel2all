#!/usr/bin/env python3
"""novel2all LLM benchmark 脚本（V0.23 决策依据）。

横向对比候选模型在 5 个 TaskType 上的表现：
- 输出质量（主观，markdown 报告）
- 延迟（秒）
- Token 数（input / output）
- 估算成本（CNY）

**绝不修改项目代码**——只读 + 真实调 LLM。

用法：
    # 跑全部（需要 5 个候选模型都能用）
    python scripts/benchmark_llm.py

    # 跑单个 task
    python scripts/benchmark_llm.py --task WRITING

    # 指定模型
    python scripts/benchmark_llm.py --models deepseek/deepseek-v4-pro,deepseek/deepseek-flash

    # dry run（不调真实 API，只检查 setup）
    python scripts/benchmark_llm.py --dry-run

    # 输出 JSON（让 CI 解析）
    python scripts/benchmark_llm.py --json

环境变量：
    DEEPSEEK_API_KEY    DeepSeek 直连（默认必需）
    DASHSCOPE_API_KEY   千问平台（可选）
    MINIMAX_API_KEY     minimax（可选）

输出：
    scripts/benchmark_results.md  - 人类可读报告
    scripts/benchmark_results.json - 机器可读数据

设计原则：
- 不修改 src/novel2all/* 代码
- 不污染 .env 真实 key（只读）
- 失败时记录错误，不中断其他 task
- 复用真实 novel2all fixture（extractor mock 等）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 自动加载 .env
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

# 复用 novel2all 已有模块（不修改它们）
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from novel2all.core.provider_router import TaskType

# === 候选模型清单（基于 docs/llm-providers-truth.md）===

CANDIDATE_MODELS = {
    # DeepSeek 直连（OpenAI 兼容）
    "deepseek/deepseek-v4-pro": {
        "base_url": None,  # 用默认 litellm 路由
        "task_preference": "DeepSeek 旗舰（V0.23 WRITING 默认）",
    },
    "deepseek/deepseek-flash": {
        "base_url": None,
        "task_preference": "DeepSeek 批量（V0.23 其他 task 默认）",
    },
    # minimax（Anthropic 兼容 + 自定义 base_url）
    "anthropic/MiniMax-M3": {
        "base_url": "https://api.minimax.cn/anthropic",
        "task_preference": "minimax 旗舰（中文长篇创作）",
    },
    # 千问平台（OpenAI 兼容 + 自定义 base_url）
    "openai/qwen3.8-max": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "task_preference": "千问旗舰（对照组）",
    },
    "openai/qwen3.8-flash": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "task_preference": "千问性价比",
    },
}

# === 各模型 API key 环境变量名 ===

API_KEY_ENV = {
    "deepseek/deepseek-v4-pro": "DEEPSEEK_API_KEY",
    "deepseek/deepseek-flash": "DEEPSEEK_API_KEY",
    "anthropic/MiniMax-M3": "MINIMAX_API_KEY",
    "openai/qwen3.8-max": "DASHSCOPE_API_KEY",
    "openai/qwen3.8-flash": "DASHSCOPE_API_KEY",
}

# === 价格表（CNY/M tokens，与 docs/llm-providers-truth.md 一致）===

PRICING = {
    "deepseek/deepseek-v4-pro": {
        "input_hit_offpeak": 0.15,
        "input_miss_offpeak": 4.50,
        "output_offpeak": 13.50,
        "input_hit_peak": 0.30,
        "input_miss_peak": 9.00,
        "output_peak": 27.00,
    },
    "deepseek/deepseek-flash": {
        "input_hit_offpeak": 0.02,
        "input_miss_offpeak": 1.00,
        "output_offpeak": 4.00,
        "input_hit_peak": 0.04,
        "input_miss_peak": 2.00,
        "output_peak": 8.00,
    },
    "anthropic/MiniMax-M3": {
        # minimax 无 peak/off-peak 区分（按统一价），原文截自 docs/llm-providers-truth.md §4
        "input_hit_offpeak": 0.84,
        "input_miss_offpeak": 4.2,
        "output_offpeak": 8.4,
        "input_hit_peak": 0.84,
        "input_miss_peak": 4.2,
        "output_peak": 8.4,
    },
    "openai/qwen3.8-max": {
        "input_hit_offpeak": 1.5,
        "input_miss_offpeak": 12.0,
        "output_offpeak": 36.0,
        # 千问无 peak/off-peak 区分（按统一价）
        "input_hit_peak": 1.5,
        "input_miss_peak": 12.0,
        "output_peak": 36.0,
    },
    "openai/qwen3.8-flash": {
        "input_hit_offpeak": 0.1,
        "input_miss_offpeak": 0.8,
        "output_offpeak": 2.7,
        "input_hit_peak": 0.1,
        "input_miss_peak": 0.8,
        "output_peak": 2.7,
    },
}


def is_peak_hour() -> bool:
    """判断当前是否处于 DeepSeek 高峰时段（北京时间）。"""
    try:
        import pytz  # type: ignore[import-not-found]

        tz = pytz.timezone("Asia/Shanghai")
    except ImportError:
        # 退化：用本地时间
        tz = None
    now = datetime.now(tz) if tz else datetime.now()  # noqa: DTZ005
    # ^ 本地时间用于 fallback，timestamp 字段
    if now.weekday() >= 5:
        return False
    hour = now.hour
    return (9 <= hour < 12) or (14 <= hour < 18)


def calc_cost(model: str, input_tokens: int, output_tokens: int, cache_hit: bool = False) -> float:
    """估算单次调用成本（CNY）。"""
    p = PRICING.get(model, {})
    if not p:
        return 0.0
    peak = is_peak_hour() and "deepseek" in model  # 千问无 peak/off-peak 区分
    suffix = "_peak" if peak else "_offpeak"
    input_price = p[f"input_hit{suffix}"] if cache_hit else p[f"input_miss{suffix}"]
    output_price = p[f"output{suffix}"]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


# === 测试用例（5 个 TaskType 各 1 个样本）===

TEST_CASES = {
    TaskType.WRITING: {
        "system": (
            "你是一位玄幻小说作家，文风偏古典白话，擅长描绘江湖恩怨。"
            "当前小说《九霄问道》讲述少年林雷觉醒血脉、复仇血亲的成长故事。"
        ),
        "user": (
            "请写《九霄问道》第1章《苍茫镇觉醒》约 600 字。\n"
            "林雷在苍茫镇集市目睹父亲被黑衣人围攻，觉醒血脉救父。\n"
            "要求：1) 用文风锚点 2) 有动作场面 3) 有伏笔埋设"
        ),
        "min_chars": 400,  # benchmark 不要求完整 2000 字，太贵
    },
    TaskType.CONSISTENCY: {
        "system": "你是小说一致性检查员，评估段落是否与角色设定冲突。",
        "user": (
            "角色设定：林雷，景和三年春生于苍茫镇，父亲林远是炼药师。\n"
            "段落：林雷站在玉京城的城墙上，望着脚下的车水马龙，回想起自己三岁那年..."
            "那年父亲被人诬陷处斩，母亲抱着襁褓中的他连夜逃亡。\n"
            "请检查：1) 地点一致性 2) 角色年龄 3) 父亲生死 4) 整体逻辑"
        ),
        "min_chars": 50,
    },
    TaskType.EXTRACTION: {
        "system": "你是结构化信息提取器，按 JSON schema 输出结果。",
        "user": (
            "请从以下段落提取角色和伏笔信息，输出 JSON：\n\n"
            "段落：林远缓缓睁开眼，对林雷说道：「孩子，你的血脉... 终究还是觉醒了。」"
            "他颤抖的手从怀中取出一枚玉佩，那是林家百年传承的信物。\n"
            "林雷接过玉佩，感到一股暖流涌入体内..."
        ),
        "min_chars": 50,
    },
    TaskType.SUMMARIZATION: {
        "system": "你是小说章节摘要员，输出 200 字以内的摘要。",
        "user": (
            "章节：林雷在苍茫镇集市采药，遇到黑衣人围攻父亲。父亲重伤倒地，"
            "林雷怀中玉佩突然发烫，激发血脉力量，一拳击退黑衣人。但父亲伤势过重，"
            "临终前告知林雷：「去找你师叔玄清真人... 告诉他... 林家还有后人...」\n\n"
            "请输出摘要："
        ),
        "min_chars": 50,
        "max_chars": 300,
    },
    TaskType.COVER: {
        "system": "你是小说封面 prompt 生成器。",
        "user": (
            "为玄幻小说《九霄问道》第1章《苍茫镇觉醒》生成英文 Stable Diffusion prompt。"
            "画面：少年林雷觉醒血脉，玉佩发光，黑衣人被击退，集市火光。\n"
            "要求：写实风格，电影感构图，8K 高清"
        ),
        "min_chars": 50,
    },
}


# === 数据类 ===


@dataclass
class BenchmarkResult:
    task: str
    model: str
    success: bool
    latency_seconds: float = 0.0
    input_tokens_estimated: int = 0  # 估算（无真实 usage 时用 chars/2）
    output_tokens_estimated: int = 0
    output_chars: int = 0
    cost_cny: float = 0.0
    cache_hit: bool = False
    output_preview: str = ""
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())  # noqa: DTZ005


# === Benchmark 主逻辑 ===


async def run_single(
    task: TaskType, model: str, api_key: str, base_url: str | None
) -> BenchmarkResult:
    """跑单个 task + model 组合。"""
    import litellm  # 用于设置 thinking 参数 + 获取真实 usage

    case = TEST_CASES[task]
    start = time.time()

    # 模型特殊配置（各家 thinking 控制）
    extra_body: dict[str, Any] | None = None
    if "deepseek/deepseek" in model:
        # DeepSeek 默认 thinking（特别是 v4-pro）会耗光 token，显式禁用
        extra_body = {"thinking": {"type": "disabled"}}
    elif "qwen" in model.lower():
        # 千问默认 thinking 默认开（实测 qwen3.8-max thinking_tokens 占 98%）
        # V0.23 默认禁用以公平对比
        extra_body = {"enable_thinking": False}
    # minimax 官方推荐思考模式默认开，但 benchmark 关闭以公平对比
    elif "minimax" in model.lower():
        extra_body = {"thinking": {"type": "disabled"}}

    try:
        # 直接调 litellm 以获取真实 usage 数据
        messages: list[dict[str, str]] = []
        if case["system"]:
            messages.append({"role": "system", "content": case["system"]})
        messages.append({"role": "user", "content": case["user"]})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "api_key": api_key,
            "temperature": 0.7 if task == TaskType.WRITING else 0.3,
            "max_tokens": 2048,
        }
        if base_url:
            kwargs["api_base"] = base_url
        if extra_body:
            kwargs["extra_body"] = extra_body

        resp = await litellm.acompletion(**kwargs)
        elapsed = time.time() - start
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        # 千问的 cache 字段名不同
        cache_hit_tokens = (
            getattr(usage, "prompt_cache_hit_tokens", 0)
            or getattr(usage, "cache_read_input_tokens", 0)
            or 0
        )
        cache_hit = cache_hit_tokens > 0 and cache_hit_tokens >= input_tokens * 0.5
        cost = calc_cost(model, input_tokens, output_tokens, cache_hit=cache_hit)

        return BenchmarkResult(
            task=task.value,
            model=model,
            success=True,
            latency_seconds=round(elapsed, 2),
            input_tokens_estimated=input_tokens,
            output_tokens_estimated=output_tokens,
            output_chars=len(content),
            cost_cny=round(cost, 6),
            cache_hit=cache_hit,
            output_preview=content[:200] + ("..." if len(content) > 200 else ""),
        )
    except Exception as e:
        elapsed = time.time() - start
        return BenchmarkResult(
            task=task.value,
            model=model,
            success=False,
            latency_seconds=round(elapsed, 2),
            error=f"{type(e).__name__}: {e}",
        )


async def run_benchmark(
    tasks: list[TaskType],
    models: list[str],
    api_keys: dict[str, str],
) -> list[BenchmarkResult]:
    """跑全部 benchmark 组合。

    每个模型独立配置 base_url + api_key，通过 litellm.acompletion 直调（不走 LLMProvider，
    这样能直接拿真实 usage 数据，且不受 provider_router thinking 控制影响）。
    """
    results = []
    for model in models:
        cfg = CANDIDATE_MODELS[model]
        base_url = cfg.get("base_url")

        # 获取 API key（按 API_KEY_ENV 表）
        env_key_name = API_KEY_ENV.get(model)
        api_key = os.environ.get(env_key_name) if env_key_name else None
        if not api_key:
            print(f"[SKIP] {model}: no API key ({env_key_name})", file=sys.stderr)
            continue

        for task in tasks:
            print(f"[RUN] {task.value} × {model}...", file=sys.stderr)
            result = await run_single(task, model, api_key, base_url)
            results.append(result)
            status = "✓" if result.success else f"✗ ({result.error})"
            print(
                f"  {status} {result.latency_seconds}s, {result.output_chars}字, "
                f"¥{result.cost_cny:.4f}",
                file=sys.stderr,
            )

    return results


def render_markdown(
    results: list[BenchmarkResult], tasks: list[TaskType], models: list[str]
) -> str:
    """生成 markdown 报告。"""
    lines = [
        "# novel2all LLM Benchmark 报告",
        "",
        f"**生成时间**：{datetime.now().isoformat()}",  # noqa: DTZ005
        f"**高峰时段**：{'是（DeepSeek 高峰价）' if is_peak_hour() else '否（DeepSeek 空闲价）'}",
        f"**任务数**：{len(tasks)}，**模型数**：{len(models)}",
        "",
        "## 汇总表",
        "",
        "| Task | Model | 成功 | 延迟(s) | 输出(字) | 输出tok(估) | 成本(¥) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.task} | {r.model} | "
            f"{'✓' if r.success else '✗'} | "
            f"{r.latency_seconds} | "
            f"{r.output_chars} | "
            f"{r.output_tokens_estimated} | "
            f"{r.cost_cny:.4f} |"
        )
    lines.append("")

    # 按 task 分组，看每个 task 上各模型对比
    lines.append("## 按 Task 分组对比")
    for task in tasks:
        lines.append(f"\n### {task.value}")
        lines.append("")
        task_results = [r for r in results if r.task == task.value and r.success]
        if not task_results:
            lines.append("（无成功结果）")
            continue
        lines.append("| Model | 延迟(s) | 字数 | 成本(¥) |")
        lines.append("|---|---|---|---|")
        for r in task_results:
            lines.append(
                f"| {r.model} | {r.latency_seconds} | {r.output_chars} | ¥{r.cost_cny:.4f} |"
            )

    # 按 model 分组，总成本
    lines.append("\n## 按 Model 总成本（本次 benchmark）")
    lines.append("")
    lines.append("| Model | 总成本(¥) | 平均延迟(s) | 成功率 |")
    lines.append("|---|---|---|---|")
    for model in models:
        mr = [r for r in results if r.model == model]
        if not mr:
            continue
        total_cost = sum(r.cost_cny for r in mr)
        avg_lat = sum(r.latency_seconds for r in mr) / len(mr) if mr else 0
        succ_rate = sum(1 for r in mr if r.success) / len(mr) if mr else 0
        lines.append(f"| {model} | ¥{total_cost:.4f} | {avg_lat:.2f} | {succ_rate * 100:.0f}% |")

    # 输出预览（仅 successful 且为写作/摘要 task）
    lines.append("\n## 输出预览（抽样）")
    for r in results:
        if r.success and r.task in ("writing", "summarization") and r.output_preview:
            lines.append(f"\n### {r.task} × {r.model}")
            lines.append("```")
            lines.append(r.output_preview)
            lines.append("```")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="novel2all LLM benchmark")
    parser.add_argument(
        "--task",
        choices=[t.value for t in TaskType],
        help="只跑单个 task",
    )
    parser.add_argument(
        "--models",
        default=",".join(CANDIDATE_MODELS.keys()),
        help="逗号分隔的候选模型列表",
    )
    parser.add_argument("--dry-run", action="store_true", help="只检查 setup，不调 API")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非 markdown")
    args = parser.parse_args()

    tasks = [TaskType(args.task)] if args.task else list(TEST_CASES.keys())
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    # 检查 API key
    api_keys = {
        "deepseek": os.environ.get("DEEPSEEK_API_KEY"),
        "dashscope": os.environ.get("DASHSCOPE_API_KEY"),
        "minimax": os.environ.get("MINIMAX_API_KEY"),
    }
    print(
        "[INFO] API keys: "
        + ", ".join(f"{k}={'OK' if v else 'MISSING'}" for k, v in api_keys.items())
    )

    if args.dry_run:
        print(f"[DRY-RUN] would test {len(tasks)} tasks × {len(models)} models")
        print(f"[DRY-RUN] candidate models: {models}")
        print(f"[DRY-RUN] peak hour: {is_peak_hour()}")
        return

    # 真实跑
    results = asyncio.run(run_benchmark(tasks, models, api_keys))

    # 输出
    if args.json:
        out = [asdict(r) for r in results]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        md = render_markdown(results, tasks, models)
        print(md)
        # 同时写入文件
        out_path = Path(__file__).parent / "benchmark_results.md"
        out_path.write_text(md, encoding="utf-8")
        json_path = Path(__file__).parent / "benchmark_results.json"
        json_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n[SAVED] {out_path}", file=sys.stderr)
        print(f"[SAVED] {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
