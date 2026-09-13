# V0.47 Cache 后端性能基准报告

**运行时间**: 2026-09-13 15:46:53 UTC
**总耗时**: 83.2s
**每个 workload ops 数**: 10,000
**Cache max_size**: 1000
**Value 大小**: ~800 chars
**工作集 (unique keys)**: 200

## 测试环境

- Python: 3.12.14
- Platform: win32

## 重要说明

- **Redis backend**: 使用 `fakeredis` in-process mock（生产 Redis 会有网络 round-trip 延迟，~0.1-1ms）
- **单线程**: 所有测量为单线程（避免 GIL / SQLite lock 干扰）
- **Warmup**: 每个 workload 前 200 ops 预热 cache
- **真实数据**: Keys = tuple-style (~40 char encoded), Values = ~800 char 模拟 LLM 响应

## Workload 矩阵

| Workload | 描述 | get/set 比例 |
|----------|------|--------------|
| read_heavy | 热数据访问模式 | 80% / 20% |
| write_heavy | 写入密集 | 20% / 80% |
| mixed | 平衡负载 | 50% / 50% |
| ttl_workload | TTL=1s, 验证 TTL 行为 | 80% get / 20% set |

## Workload: `read_heavy` (80% get + 20% set（热数据访问模式）)

| Backend | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate | Final Size |
|---------|-------------------:|---------:|---------:|---------:|----------:|---------:|-----------:|
| memory | 1,184,680 | 0.0007 | 0.0008 | 0.0010 | 0.0007 | 96.87% | 200 |
| sqlite | 53,339 | 0.0148 | 0.0178 | 0.0320 | 0.0186 | 94.77% | 200 |
| redis | 23,758 | 0.0374 | 0.0534 | 0.0945 | 0.0419 | 96.62% | 200 |
| json | 1,211 | 0.0096 | 4.3238 | 4.7898 | 0.8255 | 96.15% | 200 |

## Workload: `write_heavy` (20% get + 80% set（写入密集）)

| Backend | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate | Final Size |
|---------|-------------------:|---------:|---------:|---------:|----------:|---------:|-----------:|
| memory | 1,258,384 | 0.0007 | 0.0008 | 0.0008 | 0.0007 | 99.06% | 200 |
| sqlite | 54,205 | 0.0143 | 0.0172 | 0.0348 | 0.0183 | 99.16% | 200 |
| redis | 19,782 | 0.0501 | 0.0570 | 0.1146 | 0.0503 | 99.21% | 200 |
| json | 295 | 4.0880 | 4.7769 | 5.0836 | 3.3937 | 99.31% | 200 |

## Workload: `mixed` (50% get + 50% set（平衡负载）)

| Backend | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate | Final Size |
|---------|-------------------:|---------:|---------:|---------:|----------:|---------:|-----------:|
| memory | 1,271,149 | 0.0007 | 0.0008 | 0.0008 | 0.0007 | 98.65% | 200 |
| sqlite | 53,783 | 0.0145 | 0.0176 | 0.0382 | 0.0184 | 98.59% | 200 |
| redis | 21,123 | 0.0496 | 0.0569 | 0.1149 | 0.0471 | 98.75% | 200 |
| json | 471 | 0.0516 | 4.6935 | 5.0029 | 2.1220 | 98.51% | 200 |

## Workload: `ttl_workload` (TTL 行为测试)

| Backend | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate | Final Size |
|---------|-------------------:|---------:|---------:|---------:|----------:|---------:|-----------:|
| memory | 919,616 | 0.0007 | 0.0019 | 0.0022 | 0.0010 | 100.00% | 200 |
| sqlite | 62,306 | 0.0115 | 0.0164 | 0.0303 | 0.0159 | 100.00% | 200 |
| redis | 22,487 | 0.0381 | 0.0633 | 0.1055 | 0.0442 | 100.00% | 200 |
| json | 1,138 | 0.0103 | 4.5090 | 4.9777 | 0.8781 | 100.00% | 200 |

## 综合对比（read_heavy 性能基准）

> 最常见场景：稳态运行时 cache 命中率高（>80%）

| Rank | Backend | Throughput | p99 Latency | 备注 |
|------|---------|-----------:|------------:|------|
| #1 | memory | 1,184,680 ops/s | 0.0010 ms | 纯内存，最快 |
| #2 | sqlite | 53,339 ops/s | 0.0320 ms | SQLite + WAL + 连接池 |
| #3 | redis | 23,758 ops/s | 0.0945 ms | Redis (fakeredis in-process) |
| #4 | json | 1,211 ops/s | 4.7898 ms | JSON 文件 + 文件锁 |

## 推荐使用场景

| 场景 | 推荐 Backend | 理由 |
|------|--------------|------|
| 单进程 / 小规模 | `memory` | 最快，零依赖 |
| 单进程 + 持久化 | `sqlite` | ACID + 跨 OS 安全 + 性能可接受 |
| 跨进程 / 文件共享 | `sqlite` 或 `json` | SQLite 更安全，JSON 更通用 |
| 跨机器 / 分布式 | `redis` | 唯一支持分布式的 backend |
| 长期运行 + 大量条目 | `redis` | 内置 LRU + maxmemory 配置 |

## 原始数据

```json
[
  {
    "backend": "memory",
    "workload": "read_heavy",
    "num_ops": 10000,
    "elapsed_ms": 8.44,
    "throughput_ops_sec": 1184679.7,
    "latency_p50_ms": 0.0007,
    "latency_p95_ms": 0.0008,
    "latency_p99_ms": 0.001,
    "latency_mean_ms": 0.0007,
    "hit_rate": 0.9687,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "json",
    "workload": "read_heavy",
    "num_ops": 10000,
    "elapsed_ms": 8259.11,
    "throughput_ops_sec": 1210.8,
    "latency_p50_ms": 0.0096,
    "latency_p95_ms": 4.3238,
    "latency_p99_ms": 4.7898,
    "latency_mean_ms": 0.8255,
    "hit_rate": 0.9615,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "sqlite",
    "workload": "read_heavy",
    "num_ops": 10000,
    "elapsed_ms": 187.48,
    "throughput_ops_sec": 53339.1,
    "latency_p50_ms": 0.0148,
    "latency_p95_ms": 0.0178,
    "latency_p99_ms": 0.032,
    "latency_mean_ms": 0.0186,
    "hit_rate": 0.9477,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "redis",
    "workload": "read_heavy",
    "num_ops": 10000,
    "elapsed_ms": 420.91,
    "throughput_ops_sec": 23758.0,
    "latency_p50_ms": 0.0374,
    "latency_p95_ms": 0.0534,
    "latency_p99_ms": 0.0945,
    "latency_mean_ms": 0.0419,
    "hit_rate": 0.9662,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "memory",
    "workload": "write_heavy",
    "num_ops": 10000,
    "elapsed_ms": 7.95,
    "throughput_ops_sec": 1258384.0,
    "latency_p50_ms": 0.0007,
    "latency_p95_ms": 0.0008,
    "latency_p99_ms": 0.0008,
    "latency_mean_ms": 0.0007,
    "hit_rate": 0.9906,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "json",
    "workload": "write_heavy",
    "num_ops": 10000,
    "elapsed_ms": 33947.19,
    "throughput_ops_sec": 294.6,
    "latency_p50_ms": 4.088,
    "latency_p95_ms": 4.7769,
    "latency_p99_ms": 5.0836,
    "latency_mean_ms": 3.3937,
    "hit_rate": 0.9931,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "sqlite",
    "workload": "write_heavy",
    "num_ops": 10000,
    "elapsed_ms": 184.48,
    "throughput_ops_sec": 54205.4,
    "latency_p50_ms": 0.0143,
    "latency_p95_ms": 0.0172,
    "latency_p99_ms": 0.0348,
    "latency_mean_ms": 0.0183,
    "hit_rate": 0.9916,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "redis",
    "workload": "write_heavy",
    "num_ops": 10000,
    "elapsed_ms": 505.52,
    "throughput_ops_sec": 19781.7,
    "latency_p50_ms": 0.0501,
    "latency_p95_ms": 0.057,
    "latency_p99_ms": 0.1146,
    "latency_mean_ms": 0.0503,
    "hit_rate": 0.9921,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "memory",
    "workload": "mixed",
    "num_ops": 10000,
    "elapsed_ms": 7.87,
    "throughput_ops_sec": 1271148.7,
    "latency_p50_ms": 0.0007,
    "latency_p95_ms": 0.0008,
    "latency_p99_ms": 0.0008,
    "latency_mean_ms": 0.0007,
    "hit_rate": 0.9865,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "json",
    "workload": "mixed",
    "num_ops": 10000,
    "elapsed_ms": 21227.22,
    "throughput_ops_sec": 471.1,
    "latency_p50_ms": 0.0516,
    "latency_p95_ms": 4.6935,
    "latency_p99_ms": 5.0029,
    "latency_mean_ms": 2.122,
    "hit_rate": 0.9851,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "sqlite",
    "workload": "mixed",
    "num_ops": 10000,
    "elapsed_ms": 185.93,
    "throughput_ops_sec": 53782.8,
    "latency_p50_ms": 0.0145,
    "latency_p95_ms": 0.0176,
    "latency_p99_ms": 0.0382,
    "latency_mean_ms": 0.0184,
    "hit_rate": 0.9859,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "redis",
    "workload": "mixed",
    "num_ops": 10000,
    "elapsed_ms": 473.41,
    "throughput_ops_sec": 21123.4,
    "latency_p50_ms": 0.0496,
    "latency_p95_ms": 0.0569,
    "latency_p99_ms": 0.1149,
    "latency_mean_ms": 0.0471,
    "hit_rate": 0.9875,
    "final_size": 200,
    "note": ""
  },
  {
    "backend": "memory",
    "workload": "ttl_workload",
    "num_ops": 10000,
    "elapsed_ms": 10.87,
    "throughput_ops_sec": 919616.3,
    "latency_p50_ms": 0.0007,
    "latency_p95_ms": 0.0019,
    "latency_p99_ms": 0.0022,
    "latency_mean_ms": 0.001,
    "hit_rate": 1.0,
    "final_size": 200,
    "note": "TTL=1s, pre-fill 后等待 1.2s, 全部过期后跑 bench"
  },
  {
    "backend": "json",
    "workload": "ttl_workload",
    "num_ops": 10000,
    "elapsed_ms": 8785.12,
    "throughput_ops_sec": 1138.3,
    "latency_p50_ms": 0.0103,
    "latency_p95_ms": 4.509,
    "latency_p99_ms": 4.9777,
    "latency_mean_ms": 0.8781,
    "hit_rate": 1.0,
    "final_size": 200,
    "note": "TTL=1s, pre-fill 后等待 1.2s, 全部过期后跑 bench"
  },
  {
    "backend": "sqlite",
    "workload": "ttl_workload",
    "num_ops": 10000,
    "elapsed_ms": 160.5,
    "throughput_ops_sec": 62305.6,
    "latency_p50_ms": 0.0115,
    "latency_p95_ms": 0.0164,
    "latency_p99_ms": 0.0303,
    "latency_mean_ms": 0.0159,
    "hit_rate": 1.0,
    "final_size": 200,
    "note": "TTL=1s, pre-fill 后等待 1.2s, 全部过期后跑 bench"
  },
  {
    "backend": "redis",
    "workload": "ttl_workload",
    "num_ops": 10000,
    "elapsed_ms": 444.7,
    "throughput_ops_sec": 22486.9,
    "latency_p50_ms": 0.0381,
    "latency_p95_ms": 0.0633,
    "latency_p99_ms": 0.1055,
    "latency_mean_ms": 0.0442,
    "hit_rate": 1.0,
    "final_size": 200,
    "note": "TTL=1s, pre-fill 后等待 1.2s, 全部过期后跑 bench"
  }
]
```
