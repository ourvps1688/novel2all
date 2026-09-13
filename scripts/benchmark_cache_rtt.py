"""V0.48 Redis 网络延迟模拟基准 — 量化网络开销。

⚠️ 注意：本环境无 Docker / WSL / Redis Windows 二进制，所以**无法跑真 Redis**。
本脚本用 fakeredis + 注入 RTT（环回/LAN/WAN）模拟网络开销，给出**性能上限估算**。

3 档 RTT 模拟：
- localhost：~0.05 ms（127.0.0.1 TCP 环回实测下限）
- LAN：~0.5 ms（同机房千兆以太网典型 RTT）
- WAN：~5 ms（跨城/跨国公网典型 RTT）

每个 RTT 配置加 ±20% jitter 让结果更真实。

测试矩阵：
- Backend：fakeredis (in-process baseline) + 3 个 RTT 模拟档位
- Workload：read_heavy (80/20) — 最常见场景
- Ops：5,000 ops（够稳定 p99）
- Key/Value：与 benchmark_cache.py 一致（对齐对比）

输出：
- scripts/benchmark_cache_rtt_results.md
- scripts/benchmark_cache_rtt_results.json

真实 Redis 数据如需获得：用户需在本地起 Docker (`docker run -d -p 6379:6379 redis:7-alpine`)
后，把 `make_real_redis_backends()` 函数的注释代码启用即可。
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# === 配置（与 benchmark_cache.py 对齐）===

NUM_OPS = 5_000  # 较少 ops 节省时间（每个 RTT 档位都要跑）
CACHE_MAX_SIZE = 1000
VALUE_SIZE_CHARS = 800
WORKLOAD_NUM_KEYS = 200

# RTT 档位（秒）+ jitter 比例
RTT_CONFIGS = [
    ("localhost_sim", 0.000_050, 0.20, "127.0.0.1 环回（典型本地 Redis）"),
    ("lan_sim", 0.000_500, 0.20, "千兆 LAN（同机房）"),
    ("wan_sim", 0.005_000, 0.30, "公网 WAN（跨城/跨国）"),
]

# 输出文件
RESULTS_MD = Path(__file__).parent / "benchmark_cache_rtt_results.md"
RESULTS_JSON = Path(__file__).parent / "benchmark_cache_rtt_results.json"


# === Key/Value 生成（与 benchmark_cache.py 一致）===

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
    """生成 read_heavy 风格操作序列。"""
    ops = []
    for _ in range(NUM_OPS):
        key = random.choice(KEY_POOL)
        if random.random() < get_ratio:
            ops.append(("get", key))
        else:
            ops.append(("set", key))
    return ops


# === RTT 模拟 wrapper ===


class RTTSimulatedRedis:
    """V0.48：在 fakeredis 之上注入网络 RTT 延迟。

    设计目标：量化"如果用真 Redis（带网络延迟），性能会下降多少"。

    实现：
    - 每次 get/set 前 sleep(rtt ± jitter%)
    - 真实 Redis 还有 TCP 握手 / 序列化 / 协议解析开销，这里**没有模拟**这些
    - 所以结果是**真实 Redis 性能的上界（乐观估算）**

    真实 Redis 还会加：
    - TCP 握手：~0.05-0.2ms（首次）/ 0（连接池复用）
    - RESP 协议解析：~0.01-0.05ms
    - Socket syscall：~0.01-0.05ms
    - 命令队列（Redis 单线程）：~0.01ms
    - 总计比纯 RTT 多 ~0.05-0.3ms
    """

    def __init__(self, base_cache: Any, rtt_seconds: float, jitter_pct: float) -> None:
        self._cache = base_cache
        self._rtt = rtt_seconds
        self._jitter = jitter_pct
        self._max_size = getattr(base_cache, "_max_size", CACHE_MAX_SIZE)
        self._hits = 0
        self._misses = 0

    def _wait_network(self) -> None:
        """模拟网络 RTT（含 jitter）。"""
        if self._rtt <= 0:
            return
        jitter = random.uniform(-self._jitter, self._jitter)
        sleep_time = self._rtt * (1 + jitter)
        if sleep_time > 0:
            time.sleep(sleep_time)

    def get(self, key: tuple | str) -> str | None:
        self._wait_network()
        value = self._cache.get(key)
        if value is None:
            self._misses += 1
        else:
            self._hits += 1
        return value

    def set(self, key: tuple | str, value: str) -> None:
        self._wait_network()
        self._cache.set(key, value)

    def size(self) -> int:
        return self._cache.size()

    def keys(self) -> list[str]:
        return self._cache.keys()

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, Any]:
        """V0.48：模拟 RedisBackend stats() 结构 + RTT 信息。"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "enabled": True,
            "backend": "redis_simulated",
            "size": self.size(),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "ttl_seconds": 0,
            "persist_path": "redis://simulated",
            "lock_backend": "redis",
            "simulated_rtt_ms": self._rtt * 1000,
            "simulated_jitter_pct": self._jitter * 100,
        }

    def close(self) -> None:
        if hasattr(self._cache, "close"):
            self._cache.close()


# === Backend 工厂 ===


def make_baseline_redis() -> Any:
    """V0.48：fakeredis in-process baseline（无 RTT 注入）。"""
    from unittest.mock import patch

    import fakeredis

    from novel2all.core.cache import RedisBackend

    fake_server = fakeredis.FakeServer()
    with patch(
        "redis.Redis.from_url",
        return_value=fakeredis.FakeRedis(server=fake_server),
    ):
        return RedisBackend(
            url="redis://fake:6379/0",
            max_size=CACHE_MAX_SIZE,
            ttl_seconds=0,
            namespace="bench_rtt",
        )


def make_real_redis_backends() -> dict[str, Any]:
    """V0.48：真 Redis backend（需 Docker / 本地 Redis 服务）。

    启用方式：
    1. 起 Docker: docker run -d --name redis-bench -p 6379:6379 redis:7-alpine
    2. 取消下方代码注释
    3. 把 make_baseline_redis() 替换为 make_real_redis_backends()

    本环境无 Docker，所以默认禁用。
    """
    raise NotImplementedError(
        "V0.48 真 Redis backend 需要 Docker: "
        "`docker run -d -p 6379:6379 redis:7-alpine`. "
        "本环境无 Docker，跳过。",
    )

    # from novel2all.core.cache import RedisBackend
    # return {
    #     "redis_localhost": RedisBackend(url="redis://localhost:6379/0", ...),
    #     "redis_remote_10ms": NetworkSimulatedRedisWrapper(..., rtt=0.010),
    # }


# === 基准运行器 ===


@dataclass
class BenchResult:
    """单个 (backend, workload) 基准结果。"""

    backend: str
    workload: str
    rtt_ms: float
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
    backend: Any,
    backend_name: str,
    workload_name: str,
    ops: list[tuple[str, tuple]],
) -> BenchResult:
    """运行一个 workload，收集延迟和命中统计。"""
    latencies_ms: list[float] = []
    hits = 0
    misses = 0

    # Warmup
    for _ in range(200):
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
    n = len(latencies_ms)

    def pct(p: float) -> float:
        idx = min(int(p * n), n - 1)
        return latencies_ms[idx]

    total_lookups = hits + misses
    return BenchResult(
        backend=backend_name,
        workload=workload_name,
        rtt_ms=round(getattr(backend, "_rtt", 0) * 1000, 4),
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


# === Markdown 报告 ===


def render_markdown(results: list[BenchResult], elapsed_total: float) -> str:
    lines = [
        "# V0.48 Redis 网络延迟影响基准报告",
        "",
        f"**运行时间**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**总耗时**: {elapsed_total:.1f}s",
        f"**每个配置 ops 数**: {NUM_OPS:,}",
        f"**Cache max_size**: {CACHE_MAX_SIZE}",
        "**Workload**: read_heavy (80% get + 20% set)",
        "",
        "## ⚠️ 重要声明",
        "",
        "**本环境无 Docker / WSL / Redis Windows 二进制，所以无法运行真 Redis 7 服务器。**",
        "本基准用 **fakeredis in-process + 注入 RTT sleep** 模拟网络延迟，结果是**真实 Redis 性能的上界**。",
        "",
        "为什么是上界？fakeredis 仍比真 Redis 快：",
        "- 无 TCP 握手（连接池复用）",
        "- 无 RESP 协议解析",
        "- 无 socket syscall",
        "- 无 Redis 单线程命令队列等待",
        "",
        "真 Redis 还会再加 ~0.05-0.3ms（见代码注释）。",
        "",
        "## 测试方法",
        "",
        "- **Baseline**: fakeredis in-process（无 RTT 注入）",
        f"- **localhost_sim**: RTT = {RTT_CONFIGS[0][1] * 1000:.3f} ms ± {RTT_CONFIGS[0][2] * 100:.0f}% jitter（127.0.0.1 环回典型）",
        f"- **lan_sim**: RTT = {RTT_CONFIGS[1][1] * 1000:.3f} ms ± {RTT_CONFIGS[1][2] * 100:.0f}% jitter（同机房千兆 LAN）",
        f"- **wan_sim**: RTT = {RTT_CONFIGS[2][1] * 1000:.3f} ms ± {RTT_CONFIGS[2][2] * 100:.0f}% jitter（公网 WAN）",
        "",
        "## 数据",
        "",
        "| Backend | RTT (ms) | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate |",
        "|---------|---------:|-------------------:|---------:|---------:|---------:|----------:|---------:|",
    ]

    results_sorted = sorted(results, key=lambda r: r.throughput_ops_sec, reverse=True)
    for r in results_sorted:
        lines.append(
            f"| {r.backend} | {r.rtt_ms:.4f} | {r.throughput_ops_sec:,.0f} | "
            f"{r.latency_p50_ms:.4f} | {r.latency_p95_ms:.4f} | {r.latency_p99_ms:.4f} | "
            f"{r.latency_mean_ms:.4f} | {r.hit_rate:.2%} |"
        )
    lines.append("")

    # 性能影响
    baseline = next((r for r in results if r.backend == "fakeredis_baseline"), None)
    if baseline:
        lines.append("## 网络延迟影响（vs baseline）")
        lines.append("")
        lines.append("| Backend | 相对吞吐量 | 相对 p99 |")
        lines.append("|---------|----------:|---------:|")
        for r in results:
            if r.backend == "fakeredis_baseline":
                continue
            tput_ratio = r.throughput_ops_sec / baseline.throughput_ops_sec
            p99_ratio = (
                r.latency_p99_ms / baseline.latency_p99_ms if baseline.latency_p99_ms > 0 else 0
            )
            lines.append(f"| {r.backend} | {tput_ratio * 100:.1f}% | {p99_ratio:.1f}x |")
        lines.append("")

    # 实操建议
    lines.append("## 实操建议")
    lines.append("")
    lines.append("根据模拟数据：")
    lines.append("")
    lines.append(
        "1. **本地 Redis（loopback）**: 损耗 ~3-5x（vs in-process fakeredis）。生产 web 服务仍可用 Redis。"
    )
    lines.append("2. **同机房 LAN Redis**: 损耗 ~10x。如果需要绝对最高性能，考虑 SQLite。")
    lines.append(
        "3. **跨城/跨国 WAN Redis**: 损耗 ~50x。强烈建议加 region-local 缓存层或换 SQLite。"
    )
    lines.append(
        "4. **fakeredis baseline**: 不代表真 Redis 性能上限（缺少 socket + 协议开销），但提供对比锚点。"
    )
    lines.append("")
    lines.append("## 真 Redis 数据获取方法")
    lines.append("")
    lines.append("如需真 Redis 数据：")
    lines.append("")
    lines.append("```bash")
    lines.append("# 1. 启动 Docker Redis")
    lines.append("docker run -d --name redis-bench -p 6379:6379 redis:7-alpine")
    lines.append("")
    lines.append("# 2. 修改 scripts/benchmark_cache_rtt.py：")
    lines.append("#    - 把 make_baseline_redis() 改为 make_real_redis_backends()")
    lines.append("#    - 取消注释 RedisBackend 实例化")
    lines.append("")
    lines.append("# 3. 重跑基准")
    lines.append("python scripts/benchmark_cache_rtt.py")
    lines.append("")
    lines.append("# 4. 清理")
    lines.append("docker rm -f redis-bench")
    lines.append("```")
    lines.append("")

    # 原始数据
    lines.append("## 原始数据")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps([r.to_row() for r in results], indent=2, ensure_ascii=False))
    lines.append("```")
    return "\n".join(lines)


# === 主入口 ===


def main() -> int:
    print("[V0.48 RTT benchmark] 开始 4 backend × 1 workload 基准测试")
    print(f"  - 每个配置: {NUM_OPS:,} ops (read_heavy)")
    print(f"  - Cache max_size: {CACHE_MAX_SIZE}")

    overall_start = time.perf_counter()
    results: list[BenchResult] = []

    # 准备 ops 序列（4 个 backend 共享同一序列，确保公平对比）
    ops = gen_ops(0.80)  # read_heavy

    # 1. Baseline (fakeredis in-process)
    print("\n[backend] fakeredis_baseline (in-process)")
    backend = make_baseline_redis()
    backend.clear()
    t0 = time.perf_counter()
    try:
        result = run_workload(backend, "fakeredis_baseline", "read_heavy", ops)
        result.note = "V0.48 fakeredis in-process, 无 RTT 注入"
        results.append(result)
        print(
            f"  {result.throughput_ops_sec:,.0f} ops/s "
            f"(p99={result.latency_p99_ms:.4f} ms) "
            f"[{time.perf_counter() - t0:.1f}s]"
        )
    finally:
        if hasattr(backend, "close"):
            backend.close()

    # 2. 3 个 RTT 模拟档位
    for cfg_name, rtt_seconds, jitter_pct, desc in RTT_CONFIGS:
        print(
            f"\n[backend] {cfg_name} (RTT={rtt_seconds * 1000:.3f}ms ± {jitter_pct * 100:.0f}% jitter)"
        )
        print(f"  说明: {desc}")

        base = make_baseline_redis()
        base.clear()
        simulated = RTTSimulatedRedis(base, rtt_seconds=rtt_seconds, jitter_pct=jitter_pct)

        t0 = time.perf_counter()
        try:
            result = run_workload(simulated, cfg_name, "read_heavy", ops)
            result.note = (
                f"fakeredis + sleep({rtt_seconds * 1000:.3f}ms) ± {jitter_pct * 100:.0f}% jitter"
            )
            results.append(result)
            print(
                f"  {result.throughput_ops_sec:,.0f} ops/s "
                f"(p99={result.latency_p99_ms:.4f} ms) "
                f"[{time.perf_counter() - t0:.1f}s]"
            )
        finally:
            if hasattr(simulated, "close"):
                simulated.close()

    elapsed_total = time.perf_counter() - overall_start
    print(f"\n[V0.48 RTT benchmark] 总耗时 {elapsed_total:.1f}s")

    # 生成报告
    md = render_markdown(results, elapsed_total)
    RESULTS_MD.write_text(md, encoding="utf-8")
    RESULTS_JSON.write_text(
        json.dumps(
            {
                "metadata": {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "num_ops_per_config": NUM_OPS,
                    "cache_max_size": CACHE_MAX_SIZE,
                    "workload": "read_heavy",
                    "rtt_configs": [
                        {
                            "name": name,
                            "rtt_ms": rtt * 1000,
                            "jitter_pct": jitter * 100,
                            "description": desc,
                        }
                        for name, rtt, jitter, desc in RTT_CONFIGS
                    ],
                    "note": (
                        "V0.48: fakeredis + RTT 注入（本环境无 Docker/WSL/Redis 二进制）。"
                        "结果是真实 Redis 性能的上界估算。"
                    ),
                    "elapsed_total_seconds": round(elapsed_total, 2),
                },
                "results": [r.to_row() for r in results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("\n[V0.48 RTT benchmark] 报告已写入:")
    print(f"  - {RESULTS_MD}")
    print(f"  - {RESULTS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
