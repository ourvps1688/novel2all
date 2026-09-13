"""V0.47 Cache 后端性能基准。

覆盖 4 个 Cache backend × 4 个典型工作负载：
- MemoryLRUBackend：进程内 LRU + TTL
- JSONFileBackend：JSON 文件 + 文件锁
- SQLiteBackend：SQLite + WAL + 连接池
- RedisBackend：分布式（fakeredis in-process mock，标注清楚）

工作负载：
1. read_heavy：80% get + 20% set（热数据访问模式）
2. write_heavy：20% get + 80% set（冷启动 / 写入密集）
3. mixed：50/50（平衡负载）
4. ttl_workload：TTL=1s，频繁刷新（验证 TTL 行为）

测试数据：
- Keys：tuple 风格（model, sys_hash, user_hash, temperature）→ ~40 char encoded
- Values：800 chars（典型 LLM 响应 500-1500 字符）
- Cache size：max_size=1000（足够容纳 10K ops 工作集的前 ~200 unique keys）
- 总操作数：10,000 ops/workload（足够稳定 p95/p99 百分位）

指标：
- 吞吐量 (ops/sec)
- 延迟 p50 / p95 / p99 (ms)
- 命中率 (%)
- 总耗时 (ms)

输出：
- scripts/benchmark_cache_results.md（人类可读 markdown 报告）
- scripts/benchmark_cache_results.json（机器可读原始数据）

设计原则：
- 真实数据（不 mock value 大小）
- 每个 workload 单独跑（warm cache → 清空 → 跑 benchmark）
- 单线程（避免 GIL / SQLite lock 干扰）
- Redis backend 用 fakeredis in-process（生产 Redis 会加网络延迟）
- 失败不中断（捕获异常，记 SKIP）
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# === 配置 ===

NUM_OPS = 10_000  # 每个 workload 的操作数
CACHE_MAX_SIZE = 1000  # cache 上限
VALUE_SIZE_CHARS = 800  # value 大小（模拟典型 LLM 响应）
WORKLOAD_NUM_KEYS = 200  # 工作集大小（远小于 max_size，避免 LRU 频繁淘汰）

# 输出文件
RESULTS_MD = Path(__file__).parent / "benchmark_cache_results.md"
RESULTS_JSON = Path(__file__).parent / "benchmark_cache_results.json"


# === 负载生成器 ===

import random

random.seed(42)  # 固定种子，跨 backend 对齐操作序列

# 预生成 key pool（确保 4 backend 跑完全相同的 key 序列）
KEY_POOL = [
    ("model", f"sys_hash_{i:04d}", f"user_hash_{j:04d}", round(random.random(), 1))
    for i in range(20)  # 20 models
    for j in range(10)  # 10 sys × 10 user = 100? 不对，下面重新设计
]
# 重新设计：200 个 unique keys（= WORKLOAD_NUM_KEYS）
KEY_POOL = [
    (
        f"model_{i // 50}",
        f"sys_hash_{i:04d}",
        f"user_hash_{(i * 7) % 100:04d}",
        round(random.random(), 1),
    )
    for i in range(WORKLOAD_NUM_KEYS)
]
assert len(KEY_POOL) == WORKLOAD_NUM_KEYS
assert len(set(KEY_POOL)) == WORKLOAD_NUM_KEYS  # 全部 unique


# 预生成 value（800 chars）
def make_value(seed: int) -> str:
    """生成 800 char 的伪 LLM 响应内容。"""
    base = "在苍茫的夜色中，林雷独自站在废墟前，凝视着手中那枚染血的玉佩。"
    extra = f"第 {seed} 段：寒风呼啸而过，远方的山脉如同沉睡的巨兽，"
    padding = "x" * (VALUE_SIZE_CHARS - len(base) - len(extra))
    return base + extra + padding


VALUE_FOR_KEY = {key: make_value(i) for i, key in enumerate(KEY_POOL)}
assert all(len(v) >= VALUE_SIZE_CHARS for v in VALUE_FOR_KEY.values())


# 预生成操作序列（4 workload 各一份）
def gen_ops(get_ratio: float) -> list[tuple[str, tuple]]:
    """生成操作序列：('get', key) 或 ('set', key)。

    get_ratio: get 操作的比例（0.0 - 1.0）
    """
    ops = []
    for i in range(NUM_OPS):
        key = random.choice(KEY_POOL)
        if random.random() < get_ratio:
            ops.append(("get", key))
        else:
            ops.append(("set", key))
    return ops


# === Backend factory ===


def make_backends(tmp_dir: Path) -> dict[str, Any]:
    """创建 4 个 backend 实例。

    Returns:
        dict[backend_name, CacheBackend instance]
    """
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
        path=tmp_dir / "cache_bench.json",
        max_size=CACHE_MAX_SIZE,
        ttl_seconds=0,
    )

    # SQLite
    backends["sqlite"] = SQLiteBackend(
        path=tmp_dir / "cache_bench.db",
        max_size=CACHE_MAX_SIZE,
        ttl_seconds=0,
    )

    # Redis (fakeredis in-process mock)
    try:
        from unittest.mock import patch

        import fakeredis

        fake_server = fakeredis.FakeServer()
        with patch(
            "redis.Redis.from_url",
            return_value=fakeredis.FakeRedis(server=fake_server),
        ):
            backends["redis"] = RedisBackend(
                url="redis://fake:6379/0",
                max_size=CACHE_MAX_SIZE,
                ttl_seconds=0,
                namespace="bench",
            )
    except ImportError:
        backends["redis"] = None  # type: ignore[assignment]

    return backends


# === 基准运行器 ===


@dataclass
class BenchResult:
    """单个 backend × workload 的基准结果。"""

    backend: str
    workload: str
    num_ops: int
    elapsed_ms: float
    throughput_ops_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_mean_ms: float
    hit_rate: float
    final_size: int
    note: str = ""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


def run_workload(
    backend: Any, backend_name: str, workload_name: str, ops: list[tuple[str, tuple]]
) -> BenchResult:
    """运行一个 workload，收集延迟和命中统计。"""
    latencies_ms: list[float] = []
    hits = 0
    misses = 0

    # Warmup: 预热 cache（避免冷启动测量偏差）
    for _ in range(min(200, len(ops) // 10)):
        key = random.choice(KEY_POOL)
        backend.set(key, VALUE_FOR_KEY[key])

    # 正式 benchmark
    start = time.perf_counter()
    for op_type, key in ops:
        t0 = time.perf_counter_ns()
        if op_type == "get":
            value = backend.get(key)
            if value is not None:
                hits += 1
            else:
                misses += 1
        else:  # set
            backend.set(key, VALUE_FOR_KEY[key])
        t1 = time.perf_counter_ns()
        latencies_ms.append((t1 - t0) / 1_000_000)  # ns → ms
    elapsed = (time.perf_counter() - start) * 1000  # ms

    # 计算百分位
    latencies_ms.sort()
    n = len(latencies_ms)

    def pct(p: float) -> float:
        idx = min(int(p * n), n - 1)
        return latencies_ms[idx]

    total_lookups = hits + misses
    return BenchResult(
        backend=backend_name,
        workload=workload_name,
        num_ops=len(ops),
        elapsed_ms=round(elapsed, 2),
        throughput_ops_sec=round(len(ops) / (elapsed / 1000), 1),
        latency_p50_ms=round(pct(0.50), 4),
        latency_p95_ms=round(pct(0.95), 4),
        latency_p99_ms=round(pct(0.99), 4),
        latency_mean_ms=round(statistics.mean(latencies_ms), 4),
        hit_rate=round(hits / total_lookups, 4) if total_lookups > 0 else 0.0,
        final_size=backend.size(),
    )


# === Workload 定义 ===

WORKLOADS = [
    ("read_heavy", 0.80, "80% get + 20% set（热数据访问模式）"),
    ("write_heavy", 0.20, "20% get + 80% set（写入密集）"),
    ("mixed", 0.50, "50% get + 50% set（平衡负载）"),
]


def gen_ttl_ops() -> list[tuple[str, tuple]]:
    """TTL workload：设置 TTL=0.3s 的 entries，频繁访问触发过期。

    为简化实现：操作序列固定（set → get × N → set）
    每 5 个 op 一个 cycle，其中 4 个是 get，1 个是 set
    """
    ops: list[tuple[str, tuple]] = []
    for i in range(NUM_OPS // 5):
        key = random.choice(KEY_POOL)
        ops.append(("set", key))
        for _ in range(4):
            ops.append(("get", key))
    return ops


def run_ttl_workload(backend: Any, backend_name: str) -> BenchResult:
    """TTL workload：重新创建带 TTL 的 backend 实例以测试 TTL 行为。"""
    from novel2all.core.cache import (
        JSONFileBackend,
        MemoryLRUBackend,
        RedisBackend,
        SQLiteBackend,
    )

    # 关闭旧 backend
    if hasattr(backend, "close"):
        try:
            backend.close()
        except Exception:
            pass

    # 创建带 TTL=1 的新实例（不同文件路径避免复用）
    import tempfile

    tmp = tempfile.mkdtemp(prefix="bench_ttl_")

    if backend_name == "memory":
        ttl_backend: Any = MemoryLRUBackend(max_size=CACHE_MAX_SIZE, ttl_seconds=1)
    elif backend_name == "json":
        ttl_backend = JSONFileBackend(
            path=Path(tmp) / "cache.json", max_size=CACHE_MAX_SIZE, ttl_seconds=1
        )
    elif backend_name == "sqlite":
        ttl_backend = SQLiteBackend(
            path=Path(tmp) / "cache.db", max_size=CACHE_MAX_SIZE, ttl_seconds=1
        )
    elif backend_name == "redis":
        from unittest.mock import patch

        import fakeredis

        fake_server = fakeredis.FakeServer()
        with patch(
            "redis.Redis.from_url",
            return_value=fakeredis.FakeRedis(server=fake_server),
        ):
            ttl_backend = RedisBackend(
                url="redis://fake_ttl:6379/0",
                max_size=CACHE_MAX_SIZE,
                ttl_seconds=1,
                namespace="bench_ttl",
            )
    else:
        raise ValueError(f"unknown backend: {backend_name}")

    # Pre-fill cache
    for key in KEY_POOL[:50]:
        ttl_backend.set(key, VALUE_FOR_KEY[key])

    # Wait > TTL to ensure all expired
    time.sleep(1.2)

    ops = gen_ttl_ops()
    result = run_workload(ttl_backend, backend_name, "ttl_workload", ops)
    result.note = "TTL=1s, pre-fill 后等待 1.2s, 全部过期后跑 bench"
    if hasattr(ttl_backend, "close"):
        try:
            ttl_backend.close()
        except Exception:
            pass
    return result


# === Markdown 报告生成 ===


def render_markdown(results: list[BenchResult], elapsed_total: float) -> str:
    """生成 markdown 报告。"""
    lines = [
        "# V0.47 Cache 后端性能基准报告",
        "",
        f"**运行时间**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**总耗时**: {elapsed_total:.1f}s",
        f"**每个 workload ops 数**: {NUM_OPS:,}",
        f"**Cache max_size**: {CACHE_MAX_SIZE}",
        f"**Value 大小**: ~{VALUE_SIZE_CHARS} chars",
        f"**工作集 (unique keys)**: {WORKLOAD_NUM_KEYS}",
        "",
        "## 测试环境",
        "",
        f"- Python: {sys.version.split()[0]}",
        f"- Platform: {sys.platform}",
        "",
        "## 重要说明",
        "",
        "- **Redis backend**: 使用 `fakeredis` in-process mock（生产 Redis 会有网络 round-trip 延迟，~0.1-1ms）",
        "- **单线程**: 所有测量为单线程（避免 GIL / SQLite lock 干扰）",
        "- **Warmup**: 每个 workload 前 200 ops 预热 cache",
        "- **真实数据**: Keys = tuple-style (~40 char encoded), Values = ~800 char 模拟 LLM 响应",
        "",
        "## Workload 矩阵",
        "",
        "| Workload | 描述 | get/set 比例 |",
        "|----------|------|--------------|",
        "| read_heavy | 热数据访问模式 | 80% / 20% |",
        "| write_heavy | 写入密集 | 20% / 80% |",
        "| mixed | 平衡负载 | 50% / 50% |",
        "| ttl_workload | TTL=1s, 验证 TTL 行为 | 80% get / 20% set |",
        "",
    ]

    # 按 workload 分组
    by_workload: dict[str, list[BenchResult]] = {}
    for r in results:
        by_workload.setdefault(r.workload, []).append(r)

    for wl_name, wl_results in by_workload.items():
        wl_desc = next((d for n, _, d in WORKLOADS if n == wl_name), "TTL 行为测试")
        lines.append(f"## Workload: `{wl_name}` ({wl_desc})")
        lines.append("")
        lines.append(
            "| Backend | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate | Final Size |"
        )
        lines.append(
            "|---------|-------------------:|---------:|---------:|---------:|----------:|---------:|-----------:|"
        )
        # 排序：按 throughput 降序
        wl_results.sort(key=lambda r: r.throughput_ops_sec, reverse=True)
        for r in wl_results:
            lines.append(
                f"| {r.backend} | {r.throughput_ops_sec:,.0f} | {r.latency_p50_ms:.4f} | "
                f"{r.latency_p95_ms:.4f} | {r.latency_p99_ms:.4f} | {r.latency_mean_ms:.4f} | "
                f"{r.hit_rate:.2%} | {r.final_size} |"
            )
        lines.append("")

    # 综合对比
    lines.append("## 综合对比（read_heavy 性能基准）")
    lines.append("")
    lines.append("> 最常见场景：稳态运行时 cache 命中率高（>80%）")
    lines.append("")
    if "read_heavy" in by_workload:
        lines.append("| Rank | Backend | Throughput | p99 Latency | 备注 |")
        lines.append("|------|---------|-----------:|------------:|------|")
        sorted_rh = sorted(
            by_workload["read_heavy"], key=lambda r: r.throughput_ops_sec, reverse=True
        )
        for i, r in enumerate(sorted_rh, 1):
            note = {
                "memory": "纯内存，最快",
                "json": "JSON 文件 + 文件锁",
                "sqlite": "SQLite + WAL + 连接池",
                "redis": "Redis (fakeredis in-process)",
            }.get(r.backend, "")
            lines.append(
                f"| #{i} | {r.backend} | {r.throughput_ops_sec:,.0f} ops/s | {r.latency_p99_ms:.4f} ms | {note} |"
            )
        lines.append("")

    # 推荐使用场景
    lines.append("## 推荐使用场景")
    lines.append("")
    lines.append("| 场景 | 推荐 Backend | 理由 |")
    lines.append("|------|--------------|------|")
    lines.append("| 单进程 / 小规模 | `memory` | 最快，零依赖 |")
    lines.append("| 单进程 + 持久化 | `sqlite` | ACID + 跨 OS 安全 + 性能可接受 |")
    lines.append("| 跨进程 / 文件共享 | `sqlite` 或 `json` | SQLite 更安全，JSON 更通用 |")
    lines.append("| 跨机器 / 分布式 | `redis` | 唯一支持分布式的 backend |")
    lines.append("| 长期运行 + 大量条目 | `redis` | 内置 LRU + maxmemory 配置 |")
    lines.append("")

    # 原始数据
    lines.append("## 原始数据")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps([r.to_row() for r in results], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


# === 主入口 ===


def main() -> int:
    """运行所有 backend × workload 组合，输出报告。"""
    import tempfile

    print("[V0.47 benchmark] 开始 4 backend × 4 workload 基准测试")
    print(f"  - 每个 workload: {NUM_OPS:,} ops")
    print(f"  - Cache max_size: {CACHE_MAX_SIZE}")
    print(f"  - Value 大小: ~{VALUE_SIZE_CHARS} chars")

    overall_start = time.perf_counter()
    results: list[BenchResult] = []

    with tempfile.TemporaryDirectory(prefix="cache_bench_") as tmp_str:
        tmp_dir = Path(tmp_str)
        backends = make_backends(tmp_dir)

        # 常规 workload
        for wl_name, get_ratio, _ in WORKLOADS:
            print(f"\n[workload] {wl_name} (get_ratio={get_ratio})")
            ops = gen_ops(get_ratio)
            for backend_name, backend in backends.items():
                if backend is None:
                    print(f"  - {backend_name}: SKIPPED (no backend)")
                    continue
                # 清理旧数据
                try:
                    backend.clear()
                except Exception:
                    pass

                print(f"  - {backend_name}: running...", end=" ", flush=True)
                t0 = time.perf_counter()
                try:
                    result = run_workload(backend, backend_name, wl_name, ops)
                    results.append(result)
                    print(
                        f"{result.throughput_ops_sec:,.0f} ops/s "
                        f"(p99={result.latency_p99_ms:.4f} ms, "
                        f"hit={result.hit_rate:.1%}) "
                        f"[{time.perf_counter() - t0:.1f}s]"
                    )
                except Exception as e:
                    print(f"FAILED: {e}")
                    results.append(
                        BenchResult(
                            backend=backend_name,
                            workload=wl_name,
                            num_ops=NUM_OPS,
                            elapsed_ms=0,
                            throughput_ops_sec=0,
                            latency_p50_ms=0,
                            latency_p95_ms=0,
                            latency_p99_ms=0,
                            latency_mean_ms=0,
                            hit_rate=0,
                            final_size=0,
                            note=f"FAILED: {e}",
                        )
                    )

        # TTL workload
        print("\n[workload] ttl_workload (TTL=1s)")
        for backend_name, backend in backends.items():
            if backend is None:
                continue
            print(f"  - {backend_name}: running...", end=" ", flush=True)
            t0 = time.perf_counter()
            try:
                result = run_ttl_workload(backend, backend_name)
                results.append(result)
                print(
                    f"{result.throughput_ops_sec:,.0f} ops/s "
                    f"(p99={result.latency_p99_ms:.4f} ms) "
                    f"[{time.perf_counter() - t0:.1f}s]"
                )
            except Exception as e:
                print(f"FAILED: {e}")

    elapsed_total = time.perf_counter() - overall_start
    print(f"\n[V0.47 benchmark] 总耗时 {elapsed_total:.1f}s")

    # 生成报告
    md = render_markdown(results, elapsed_total)
    RESULTS_MD.write_text(md, encoding="utf-8")
    RESULTS_JSON.write_text(
        json.dumps(
            {
                "metadata": {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "num_ops_per_workload": NUM_OPS,
                    "cache_max_size": CACHE_MAX_SIZE,
                    "value_size_chars": VALUE_SIZE_CHARS,
                    "workload_keys": WORKLOAD_NUM_KEYS,
                    "elapsed_total_seconds": round(elapsed_total, 2),
                    "note": "Redis backend uses fakeredis in-process (not real network)",
                },
                "results": [r.to_row() for r in results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("\n[V0.47 benchmark] 报告已写入:")
    print(f"  - {RESULTS_MD}")
    print(f"  - {RESULTS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
