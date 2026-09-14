"""V0.52：Cache benchmark CI 版本（性能回归保护）。

设计目标：
- 在 CI 中跑简化的 benchmark（约 30s）
- 对比 baseline（scripts/cache_benchmark_baseline.json）
- throughput 下降 > REGRESSION_THRESHOLD 视为回归，exit 1 失败 CI
- throughput 提升 > 10% 视为显著改进（warning，但通过）

CLI 用法：
    # 跑 benchmark + 对比 baseline（CI 默认模式）
    python scripts/benchmark_cache_ci.py

    # 更新 baseline（性能提升或修复后）
    python scripts/benchmark_cache_ci.py --update-baseline

    # 跳过 redis（CI 环境无 fakeredis 时用）
    python scripts/benchmark_cache_ci.py --skip-redis

    # 自定义阈值（默认 25%）
    python scripts/benchmark_cache_ci.py --regression-threshold 0.30

CI 集成（.github/workflows/ci.yml）：
    - name: Cache benchmark regression check
      run: uv run python scripts/benchmark_cache_ci.py
      失败时 exit 1 → CI fail

数据来源：
- V0.47 完整版（scripts/benchmark_cache.py）：10K ops × 4 workload = ~83s
- V0.52 CI 版（本文件）：2K ops × 3 workload × 4 backend = ~30s（适合 CI）

阈值默认值：
- REGRESSION_THRESHOLD = 0.25（25%）— 超过视为回归，CI 失败
- IMPROVEMENT_THRESHOLD = 0.10（10%）— 超过视为改进，warning 但通过

注意：
- fakeredis 与真 Redis 性能差异 ~30%（fakeredis 更快，因无 socket 开销）
- CI runner 与本地机器差异 ~20%（CI 较慢）
- 综合考虑 25% 阈值能在"真回归"和"环境抖动"之间取得平衡
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# === 配置 ===

NUM_OPS = 2000  # CI 版本 ops 数（比 V0.47 完整版少 5x，约 30s）
CACHE_MAX_SIZE = 1000
VALUE_SIZE_CHARS = 800
WORKLOAD_NUM_KEYS = 200
WARMUP_OPS = 100

# 阈值
# V0.52：CI 与本地 Windows dev 性能差异 ~30%（memory）~55%（sqlite）
# 因此阈值放宽到 50%，真回归（>50%）才会拦截
# 本地开发可用 --regression-threshold 0.25 严格检测
DEFAULT_REGRESSION_THRESHOLD = 0.50  # 50% 下降视为回归
DEFAULT_IMPROVEMENT_THRESHOLD = 0.10  # 10% 提升视为改进

BASELINE_PATH = Path(__file__).parent / "cache_benchmark_baseline.json"

# === 数据准备（与 V0.47 benchmark_cache.py 一致）===

random.seed(42)
KEY_POOL = [
    (
        f"model_{i // 50}",
        f"sys_hash_{i:04d}",
        f"user_hash_{(i * 7) % 100:04d}",
        round(random.random(), 1),
    )
    for i in range(WORKLOAD_NUM_KEYS)
]
assert len(set(KEY_POOL)) == WORKLOAD_NUM_KEYS


def make_value(seed: int) -> str:
    """生成 ~800 char 伪 LLM 响应。"""
    base = "在苍茫的夜色中，林雷独自站在废墟前，凝视着手中那枚染血的玉佩。"
    extra = f"第 {seed} 段：寒风呼啸而过，远方的山脉如同沉睡的巨兽，"
    padding = "x" * (VALUE_SIZE_CHARS - len(base) - len(extra))
    return base + extra + padding


VALUE_FOR_KEY = {key: make_value(i) for i, key in enumerate(KEY_POOL)}


def gen_ops(get_ratio: float) -> list[tuple[str, tuple]]:
    """生成操作序列。"""
    ops = []
    for _ in range(NUM_OPS):
        key = random.choice(KEY_POOL)
        if random.random() < get_ratio:
            ops.append(("get", key))
        else:
            ops.append(("set", key))
    return ops


# === Backend factory（简化版，只跑 3 workload：read/write/mixed）===


def make_backends(tmp_dir: Path, skip_redis: bool = False) -> dict[str, Any]:
    """V0.52：CI 版 backend 工厂（与 V0.47 benchmark 一致）。"""
    from unittest.mock import patch

    import fakeredis

    from novel2all.core.cache import (
        JSONFileBackend,
        MemoryLRUBackend,
        RedisBackend,
        SQLiteBackend,
    )

    backends: dict[str, Any] = {}

    # MemoryLRU
    backends["memory"] = MemoryLRUBackend(max_size=CACHE_MAX_SIZE, ttl_seconds=0)

    # JSONFile
    backends["json"] = JSONFileBackend(
        path=tmp_dir / "cache_bench_ci.json",
        max_size=CACHE_MAX_SIZE,
        ttl_seconds=0,
    )

    # SQLite
    backends["sqlite"] = SQLiteBackend(
        path=tmp_dir / "cache_bench_ci.db",
        max_size=CACHE_MAX_SIZE,
        ttl_seconds=0,
    )

    # Redis (fakeredis)
    if not skip_redis:
        try:
            fake_server = fakeredis.FakeServer()
            with patch(
                "redis.Redis.from_url",
                return_value=fakeredis.FakeRedis(server=fake_server),
            ):
                backends["redis"] = RedisBackend(
                    url="redis://fake:6379/0",
                    max_size=CACHE_MAX_SIZE,
                    ttl_seconds=0,
                    namespace="bench_ci",
                )
        except ImportError:
            print("⚠️  fakeredis 未安装，跳过 redis backend")

    return backends


# === 基准运行器 ===


@dataclass
class CIResult:
    """V0.52：CI 版 benchmark 单结果。"""

    backend: str
    workload: str
    num_ops: int
    elapsed_ms: float
    throughput_ops_sec: float
    p99_ms: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_workload(
    backend: Any,
    backend_name: str,
    workload_name: str,
    ops: list[tuple[str, tuple]],
) -> CIResult:
    """V0.52：CI 版 workload 运行（简化：仅 p99）。"""
    latencies_ms: list[float] = []
    hits = 0
    misses = 0

    # Warmup
    for _ in range(WARMUP_OPS):
        key = random.choice(KEY_POOL)
        backend.set(key, VALUE_FOR_KEY[key])

    # Benchmark
    start = time.perf_counter()
    for op_type, key in ops:
        t0 = time.perf_counter_ns()
        if op_type == "get":
            value = backend.get(key)
            if value is not None:
                hits += 1
            else:
                misses += 1
        else:
            backend.set(key, VALUE_FOR_KEY[key])
        t1 = time.perf_counter_ns()
        latencies_ms.append((t1 - t0) / 1_000_000)
    elapsed = (time.perf_counter() - start) * 1000

    latencies_ms.sort()
    p99_idx = min(int(0.99 * len(latencies_ms)), len(latencies_ms) - 1)

    return CIResult(
        backend=backend_name,
        workload=workload_name,
        num_ops=len(ops),
        elapsed_ms=round(elapsed, 2),
        throughput_ops_sec=round(len(ops) / (elapsed / 1000), 1),
        p99_ms=round(latencies_ms[p99_idx], 4),
    )


# === Baseline 对比与回归检测 ===


@dataclass
class RegressionReport:
    """V0.52：单条 baseline 对比结果。"""

    backend: str
    workload: str
    baseline_throughput: float
    current_throughput: float
    regression_pct: float  # 负值表示变慢
    is_regression: bool
    is_improvement: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_to_baseline(
    current_results: list[CIResult],
    baseline: dict[str, Any],
    regression_threshold: float,
    improvement_threshold: float,
) -> list[RegressionReport]:
    """V0.52：对比当前结果与 baseline，检测回归。"""
    baseline_map = {(r["backend"], r["workload"]): r for r in baseline["results"]}

    reports: list[RegressionReport] = []
    for cur in current_results:
        key = (cur.backend, cur.workload)
        if key not in baseline_map:
            continue  # baseline 中没有该组合（skip）

        base = baseline_map[key]
        baseline_tput = base["throughput_ops_sec"]
        current_tput = cur.throughput_ops_sec

        # regression_pct: 负值表示变慢
        regression_pct = (current_tput - baseline_tput) / baseline_tput

        # 回归：变慢超过阈值
        is_regression = regression_pct < -regression_threshold
        # 改进：变快超过阈值
        is_improvement = regression_pct > improvement_threshold

        reports.append(
            RegressionReport(
                backend=cur.backend,
                workload=cur.workload,
                baseline_throughput=baseline_tput,
                current_throughput=current_tput,
                regression_pct=round(regression_pct, 4),
                is_regression=is_regression,
                is_improvement=is_improvement,
            )
        )

    return reports


def format_report(reports: list[RegressionReport]) -> str:
    """V0.52：格式化回归检测报告（人类可读）。"""
    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("V0.52 Cache Benchmark CI - 回归检测报告")
    lines.append("=" * 80)
    lines.append("")
    lines.append(
        f"{'Backend':<10} {'Workload':<15} {'Baseline':>12} {'Current':>12} {'Change':>10} {'Status':>10}"
    )
    lines.append("-" * 80)

    for r in reports:
        change_pct = f"{r.regression_pct * 100:+.1f}%"
        if r.is_regression:
            status = "❌ REGRESSION"
            icon = "❌"
        elif r.is_improvement:
            status = "✅ IMPROVED"
            icon = "✅"
        else:
            status = "✓ OK"
            icon = "✓"
        lines.append(
            f"{r.backend:<10} {r.workload:<15} "
            f"{r.baseline_throughput:>10,.0f}/s {r.current_throughput:>10,.0f}/s "
            f"{change_pct:>10} {icon} {status}"
        )
    lines.append("-" * 80)

    regressions = [r for r in reports if r.is_regression]
    improvements = [r for r in reports if r.is_improvement]

    lines.append("")
    lines.append(f"总计：{len(reports)} 个测试，{len(regressions)} 回归，{len(improvements)} 改进")

    if regressions:
        lines.append("")
        lines.append("⚠️  回归详情：")
        for r in regressions:
            lines.append(
                f"  - {r.backend} / {r.workload}: "
                f"{r.baseline_throughput:,.0f} → {r.current_throughput:,.0f} ops/s "
                f"({r.regression_pct * 100:.1f}%)"
            )
    if improvements:
        lines.append("")
        lines.append("🎉 改进详情：")
        for r in improvements:
            lines.append(
                f"  - {r.backend} / {r.workload}: "
                f"{r.baseline_throughput:,.0f} → {r.current_throughput:,.0f} ops/s "
                f"(+{r.regression_pct * 100:.1f}%)"
            )

    return "\n".join(lines)


# === 主入口 ===


def main() -> int:
    parser = argparse.ArgumentParser(description="V0.52 Cache benchmark CI regression check")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="用当前结果更新 baseline（用于性能提升后）",
    )
    parser.add_argument(
        "--skip-redis",
        action="store_true",
        help="跳过 redis backend（CI 环境无 fakeredis 时用）",
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=DEFAULT_REGRESSION_THRESHOLD,
        help=f"回归阈值（默认 {DEFAULT_REGRESSION_THRESHOLD:.0%}）",
    )
    parser.add_argument(
        "--improvement-threshold",
        type=float,
        default=DEFAULT_IMPROVEMENT_THRESHOLD,
        help=f"改进阈值（默认 {DEFAULT_IMPROVEMENT_THRESHOLD:.0%}）",
    )
    args = parser.parse_args()

    import tempfile

    print("[V0.52 cache-bench-ci] 启动 CI 版 benchmark")
    print(f"  ops/workload: {NUM_OPS:,}（CI 加速版）")
    print(f"  baseline: {BASELINE_PATH}")
    print(f"  regression threshold: {args.regression_threshold:.0%}")
    print(f"  improvement threshold: {args.improvement_threshold:.0%}")

    overall_start = time.perf_counter()
    current_results: list[CIResult] = []

    workloads = [
        ("read_heavy", 0.80),
        ("write_heavy", 0.20),
        ("mixed", 0.50),
    ]

    # V0.52：每个 backend 用独立的 tmp 目录 + 在每个 workload 后销毁/重建
    # 解决 SQLite WAL 文件残留 + json 文件锁在 Windows 上的问题
    for wl_name, get_ratio in workloads:
        ops = gen_ops(get_ratio)
        with tempfile.TemporaryDirectory(prefix=f"cache_bench_ci_{wl_name}_") as tmp_str:
            tmp_dir = Path(tmp_str)
            backends = make_backends(tmp_dir, skip_redis=args.skip_redis)

            for backend_name, backend in backends.items():
                try:
                    backend.clear()
                except Exception:
                    pass

                print(f"  [{wl_name}] {backend_name} ...", end=" ", flush=True)
                t0 = time.perf_counter()
                try:
                    result = run_workload(backend, backend_name, wl_name, ops)
                    result.note = (
                        f"ops={NUM_OPS}, value_size={VALUE_SIZE_CHARS}, keys={WORKLOAD_NUM_KEYS}"
                    )
                    current_results.append(result)
                    print(
                        f"{result.throughput_ops_sec:,.0f} ops/s "
                        f"(p99={result.p99_ms:.4f}ms) "
                        f"[{time.perf_counter() - t0:.1f}s]"
                    )
                except Exception as e:
                    print(f"FAILED: {e}")
                    current_results.append(
                        CIResult(
                            backend=backend_name,
                            workload=wl_name,
                            num_ops=NUM_OPS,
                            elapsed_ms=0,
                            throughput_ops_sec=0,
                            p99_ms=0,
                            note=f"FAILED: {e}",
                        )
                    )

                # 清理：先 close 释放连接池/file lock
                try:
                    if hasattr(backend, "close"):
                        backend.close()
                except Exception:
                    pass
            # tmp_dir 在 with 退出时自动清理（含 sqlite/redis/json 临时文件）

    elapsed_total = time.perf_counter() - overall_start
    print(f"\n[V0.52 cache-bench-ci] 总耗时 {elapsed_total:.1f}s")

    # === 处理 --update-baseline ===
    if args.update_baseline:
        baseline_data = {
            "metadata": {
                "updated_at": datetime.now(UTC).isoformat(),
                "version": "V0.52",
                "platform": "auto-updated by CI",
                "note": "Auto-updated by benchmark_cache_ci.py --update-baseline",
            },
            "results": [r.to_dict() for r in current_results],
        }
        BASELINE_PATH.write_text(
            json.dumps(baseline_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"✅ Baseline 已更新：{BASELINE_PATH}")
        print(f"   共 {len(current_results)} 条记录")
        return 0

    # === 对比 baseline 检测回归 ===
    if not BASELINE_PATH.exists():
        print(f"⚠️  Baseline 不存在: {BASELINE_PATH}")
        print("   首次运行请先用 --update-baseline 创建 baseline")
        return 1

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    reports = compare_to_baseline(
        current_results=current_results,
        baseline=baseline,
        regression_threshold=args.regression_threshold,
        improvement_threshold=args.improvement_threshold,
    )

    print(format_report(reports))

    # 保存当前结果
    results_path = BASELINE_PATH.parent / "cache_benchmark_ci_results.json"
    results_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "num_ops": NUM_OPS,
                    "regression_threshold": args.regression_threshold,
                    "elapsed_total_seconds": round(elapsed_total, 2),
                },
                "results": [r.to_dict() for r in current_results],
                "comparison": [r.to_dict() for r in reports],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n[V0.52 cache-bench-ci] 详细结果：{results_path}")

    # 决定退出码
    regressions = [r for r in reports if r.is_regression]
    if regressions:
        print(
            f"\n❌ CI FAILED：检测到 {len(regressions)} 个回归（> {args.regression_threshold:.0%}）"
        )
        return 1

    print("\n✅ CI PASSED：无回归")
    return 0


if __name__ == "__main__":
    sys.exit(main())
