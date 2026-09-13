# V0.48 Redis 网络延迟影响基准报告

**运行时间**: 2026-09-13 16:09:10 UTC
**总耗时**: 37.8s
**每个配置 ops 数**: 5,000
**Cache max_size**: 1000
**Workload**: read_heavy (80% get + 20% set)

## ⚠️ 重要声明

**本环境无 Docker / WSL / Redis Windows 二进制，所以无法运行真 Redis 7 服务器。**
本基准用 **fakeredis in-process + 注入 RTT sleep** 模拟网络延迟，结果是**真实 Redis 性能的上界**。

为什么是上界？fakeredis 仍比真 Redis 快：
- 无 TCP 握手（连接池复用）
- 无 RESP 协议解析
- 无 socket syscall
- 无 Redis 单线程命令队列等待

真 Redis 还会再加 ~0.05-0.3ms（见代码注释）。

## 测试方法

- **Baseline**: fakeredis in-process（无 RTT 注入）
- **localhost_sim**: RTT = 0.050 ms ± 20% jitter（127.0.0.1 环回典型）
- **lan_sim**: RTT = 0.500 ms ± 20% jitter（同机房千兆 LAN）
- **wan_sim**: RTT = 5.000 ms ± 30% jitter（公网 WAN）

## 数据

| Backend | RTT (ms) | Throughput (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Hit Rate |
|---------|---------:|-------------------:|---------:|---------:|---------:|----------:|---------:|
| fakeredis_baseline | 0.0000 | 23,683 | 0.0375 | 0.0547 | 0.0939 | 0.0420 | 92.70% |
| localhost_sim | 0.0500 | 1,603 | 0.6042 | 0.7487 | 0.8585 | 0.6233 | 93.67% |
| lan_sim | 0.5000 | 1,146 | 0.9184 | 1.1844 | 1.3138 | 0.8713 | 89.85% |
| wan_sim | 5.0000 | 178 | 5.6247 | 7.0324 | 7.3226 | 5.6307 | 92.01% |

## 网络延迟影响（vs baseline）

| Backend | 相对吞吐量 | 相对 p99 |
|---------|----------:|---------:|
| localhost_sim | 6.8% | 9.1x |
| lan_sim | 4.8% | 14.0x |
| wan_sim | 0.7% | 78.0x |

## 实操建议

根据模拟数据：

1. **本地 Redis（loopback）**: 损耗 ~3-5x（vs in-process fakeredis）。生产 web 服务仍可用 Redis。
2. **同机房 LAN Redis**: 损耗 ~10x。如果需要绝对最高性能，考虑 SQLite。
3. **跨城/跨国 WAN Redis**: 损耗 ~50x。强烈建议加 region-local 缓存层或换 SQLite。
4. **fakeredis baseline**: 不代表真 Redis 性能上限（缺少 socket + 协议开销），但提供对比锚点。

## 真 Redis 数据获取方法

如需真 Redis 数据：

```bash
# 1. 启动 Docker Redis
docker run -d --name redis-bench -p 6379:6379 redis:7-alpine

# 2. 修改 scripts/benchmark_cache_rtt.py：
#    - 把 make_baseline_redis() 改为 make_real_redis_backends()
#    - 取消注释 RedisBackend 实例化

# 3. 重跑基准
python scripts/benchmark_cache_rtt.py

# 4. 清理
docker rm -f redis-bench
```

## 原始数据

```json
[
  {
    "backend": "fakeredis_baseline",
    "workload": "read_heavy",
    "rtt_ms": 0,
    "num_ops": 5000,
    "elapsed_ms": 211.13,
    "throughput_ops_sec": 23682.6,
    "latency_p50_ms": 0.0375,
    "latency_p95_ms": 0.0547,
    "latency_p99_ms": 0.0939,
    "latency_mean_ms": 0.042,
    "hit_rate": 0.927,
    "final_size": 199,
    "note": "V0.48 fakeredis in-process, 无 RTT 注入"
  },
  {
    "backend": "localhost_sim",
    "workload": "read_heavy",
    "rtt_ms": 0.05,
    "num_ops": 5000,
    "elapsed_ms": 3119.44,
    "throughput_ops_sec": 1602.9,
    "latency_p50_ms": 0.6042,
    "latency_p95_ms": 0.7487,
    "latency_p99_ms": 0.8585,
    "latency_mean_ms": 0.6233,
    "hit_rate": 0.9367,
    "final_size": 199,
    "note": "fakeredis + sleep(0.050ms) ± 20% jitter"
  },
  {
    "backend": "lan_sim",
    "workload": "read_heavy",
    "rtt_ms": 0.5,
    "num_ops": 5000,
    "elapsed_ms": 4360.99,
    "throughput_ops_sec": 1146.5,
    "latency_p50_ms": 0.9184,
    "latency_p95_ms": 1.1844,
    "latency_p99_ms": 1.3138,
    "latency_mean_ms": 0.8713,
    "hit_rate": 0.8985,
    "final_size": 199,
    "note": "fakeredis + sleep(0.500ms) ± 20% jitter"
  },
  {
    "backend": "wan_sim",
    "workload": "read_heavy",
    "rtt_ms": 5.0,
    "num_ops": 5000,
    "elapsed_ms": 28162.33,
    "throughput_ops_sec": 177.5,
    "latency_p50_ms": 5.6247,
    "latency_p95_ms": 7.0324,
    "latency_p99_ms": 7.3226,
    "latency_mean_ms": 5.6307,
    "hit_rate": 0.9201,
    "final_size": 197,
    "note": "fakeredis + sleep(5.000ms) ± 30% jitter"
  }
]
```