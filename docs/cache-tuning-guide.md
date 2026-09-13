# novel2all Cache 调优与生产部署指南

> **版本范围**：V0.33 → V0.48（Cache 工程化全线）
> **数据来源**：`scripts/benchmark_cache.py` (V0.47) + `scripts/benchmark_cache_rtt.py` (V0.48)
> **目标**：把 benchmark 实测数据转为可操作的生产部署 checklist

---

## 1. TL;DR — 30 秒决策表

| 你的场景 | 推荐 Backend | 典型 TTL | 推荐 max_size |
|----------|--------------|---------:|--------------:|
| 本地开发 / 单次运行 | `memory` | 0（不过期） | 256 |
| 单进程 + 持久化 | `sqlite` | 86400（24h） | 1024 |
| 多进程本地 + 文件共享 | `sqlite` | 86400 | 1024-4096 |
| 同机房多 Web 实例 | `redis` (loopback) | 3600（1h） | 4096 + Redis maxmemory |
| 跨城/多 region | `redis` + region-local | 1800（30min） | 8192 + LRU policy |
| ⚠️ 跨城/跨国 Redis 直连 | **不要**（损耗 130x） | - | - |

**不在表里的场景** → 看第 2 节决策树。

---

## 2. Backend 选择决策树

```
你的部署形态？
├─ 单进程（CLI / 脚本）
│   ├─ 需要重启后保留？ → No → memory
│   │                      Yes → sqlite
│   └─ 跨 OS 共享文件？ → sqlite（已跨 OS 验证）
│
├─ 多进程（同机）
│   ├─ 进程数 < 5 → sqlite（WAL 模式支持读并发）
│   └─ 进程数 ≥ 5 → redis（loopback，单线程串行化更稳）
│
├─ 多机器（同 region / 同机房）
│   └─ redis（唯一支持分布式）
│
└─ 多 region / 跨城 / 跨国
    ├─ Redis 直连？→ ❌ 不推荐（见 §5 网络损耗）
    └─ Redis + region-local SQLite 双层？→ ✅ 推荐
```

### 2.1 Benchmark 实测数据（V0.47 read_heavy 80/20）

| Backend | Throughput | p99 延迟 | 相对 memory | 推荐场景 |
|---------|-----------:|---------:|------------:|----------|
| `memory` | 1.27M ops/s | 0.0008 ms | **100%** | 单进程 / 开发 |
| `sqlite` | 54K ops/s | 0.0334 ms | **4.2%** | 单进程+持久化 / 多进程本地 |
| `redis` (fakeredis) | 23K ops/s | 0.0945 ms | **1.8%** | 分布式（同机房 loopback） |
| `json` | 1.2K ops/s | 4.8268 ms | **0.09%** | 兼容性场景（不推荐生产） |

> **结论**：**SQLite 是 sweet spot** — 性能比 Redis 快 2x + 比 JSON 快 45x + 内置 ACID + 跨 OS 兼容。仅在需要跨机器时才用 Redis。

### 2.2 各 backend 适用/不适用矩阵

| Backend | 单进程 | 多进程本地 | 多机器 | 持久化 | 跨 OS | 分布式 |
|---------|:------:|:----------:|:------:|:------:|:------:|:------:|
| `memory` | ✅ | ❌ | ❌ | ❌ | - | ❌ |
| `json` | ✅ | ⚠️ (有锁) | ⚠️ (NFS 慢) | ✅ | ⚠️ | ❌ |
| `sqlite` | ✅ | ✅ | ⚠️ (NFS 慢) | ✅ | ✅ | ❌ |
| `redis` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 3. TTL 配置（cache_ttl_seconds）

### 3.1 决策原则

- **TTL = 0**（永不过期）：适合**内容稳定**的场景（小说骨架、角色设定）
- **TTL > 0**：适合**内容会变**的场景（实时事件、模型版本切换、prompt 迭代）

### 3.2 推荐 TTL 表

| 内容类型 | 推荐 TTL | 理由 |
|----------|---------:|------|
| 角色卡 / 世界观 | 0（永不过期） | 频繁复用 + 几乎不变 |
| 章节细纲 | 86400（24h） | 短期复用，迭代期可能重写 |
| 完整章节正文 | 604800（7天） | 重写概率低 |
| LLM 输出调试 | 3600（1h） | prompt 频繁调整，避免用旧结果 |
| 第三方 API 响应 | 依 API 缓存策略 | 如：天气数据 600s（10min） |

### 3.3 TTL 行为数据（V0.47 ttl_workload 实测）

4 个 backend 在 TTL=1s 下的表现：

| Backend | Throughput | p99 (ms) | TTL 检查开销 |
|---------|-----------:|---------:|-------------:|
| `memory` | 812K ops/s | 0.0023 | 应用层 O(1) |
| `sqlite` | 64K ops/s | 0.0284 | SQL `expires_at < ?` 检查 |
| `redis` (in-process) | 22K ops/s | 0.1052 | **Redis 原生 EXPIRE**（零应用层开销） |
| `json` | 1.1K ops/s | 4.9249 | 应用层检查 + 重读整个 JSON |

> **关键**：Redis 的 TTL 是 **服务端原生 EXPIRE**，性能不受 TTL 设置影响。其他 backend 是**应用层检查**，TTL > 0 会有轻微开销。

### 3.4 TTL 边界陷阱

⚠️ **不要设 TTL 太短**：
- TTL < 60s：cache 命中率急剧下降（benchmark 显示 hit_rate 从 96% 掉到 < 50%）
- 每次 miss 都要重调 LLM → 反而更慢 + 更贵
- **经验法则**：TTL × cache_hit_rate ≥ 期望复用周期

---

## 4. max_size 配置（cache_max_size）

### 4.1 内存占用估算

| Value 大小 | 200 keys | 1024 keys | 4096 keys |
|-----------:|---------:|----------:|----------:|
| 200 chars (小) | 40 KB | 200 KB | 800 KB |
| 800 chars (典型) | 160 KB | 800 KB | 3.2 MB |
| 2000 chars (大) | 400 KB | 2 MB | 8 MB |

**推导**：每个 entry 大约 = `value_size + 100 bytes overhead`（key 编码 + 元数据）

### 4.2 max_size 推荐值

| 场景 | 推荐 max_size | 内存上限 |
|------|--------------:|---------:|
| CLI / 一次性脚本 | 256（默认） | ~200 KB |
| 开发 / 调试 | 512 | ~400 KB |
| 单用户 web 服务 | 1024 | ~800 KB |
| 多用户 web 服务 | 4096 | ~3 MB |
| 大规模爬虫 / 批处理 | 16384 | ~13 MB |
| Redis + maxmemory | 由 Redis 配置决定 | 由 Redis 控制 |

### 4.3 max_size 与 LRU 淘汰

- **max_size 太小**：频繁 LRU 淘汰 → 命中率低
- **max_size 太大**：内存占用高 + 全表扫描慢
- **经验法则**：max_size = 2-5x 实际 unique keys 数

如何估算 unique keys？
- 看 `cache_stats()` 的 `size` 字段（稳态运行后）
- size 接近 max_size → 调大；size 远小于 max_size → 调小

---

## 5. 网络延迟影响（Redis 部署关键）

### 5.1 V0.48 RTT 实测（fakeredis + 注入 RTT 模拟）

| 部署位置 | RTT | Throughput | 损耗（vs in-process） |
|----------|----:|-----------:|---------------------:|
| in-process (基准) | 0 ms | 23.7K ops/s | 100% |
| localhost 环回 | 0.05 ms | 1.6K ops/s | **15x** |
| LAN（同机房） | 0.5 ms | 1.1K ops/s | **21x** |
| WAN（跨城） | 5 ms | 178 ops/s | **133x** |

> **结论**：**WAN Redis 几乎不可用**（178 ops/s 远低于 SQLite 的 54K ops/s）。

### 5.2 Redis 部署建议

| 部署位置 | 是否推荐 | 理由 |
|----------|:--------:|------|
| 同机 loopback | ✅ | RTT 0.05ms，损耗可接受 |
| 同机房 LAN | ✅ | RTT 0.5ms，需权衡 |
| 跨城 / 跨国 | ❌ | 损耗 130x，必须加 region-local cache |

### 5.3 多 region 部署模式

```
[User in Region A]  →  [App A]  →  [Local Cache (SQLite)]  ⇄  [Redis A]
                                                              ↕ async replication
[User in Region B]  →  [App B]  →  [Local Cache (SQLite)]  ⇄  [Redis B]
```

**两层缓存**：
- L1（应用层 SQLite）：< 1ms，进程本地
- L2（Redis）：跨进程 / 跨实例共享
- **不要**让 L2 是跨城 Redis → 加 region-local 兜底

---

## 6. 迁移路径（升级现有部署）

### 6.1 从 memory → sqlite（最常见）

```bash
# 1. 启动时切换 backend
export LLM_CACHE_BACKEND=sqlite
export LLM_CACHE_PERSIST_PATH=/var/cache/novel2all/cache.db
export LLM_CACHE_ENABLED=true

# 2. 旧 memory cache 数据自动丢弃（不持久）
# 3. 新 sqlite cache 自动创建

# 4. 可选：用迁移工具批量导入历史数据（V0.43）
novel2all cache-migrate --src memory --dst sqlite
```

### 6.2 从 sqlite → redis（多实例场景）

```bash
# 1. 起 Redis 服务
docker run -d -p 6379:6379 redis:7-alpine

# 2. 切换 backend（配置）
export LLM_CACHE_BACKEND=redis
export LLM_CACHE_REDIS_URL=redis://localhost:6379/0
export LLM_CACHE_REDIS_NAMESPACE=novel2all_prod

# 3. 一次性迁移历史数据
novel2all cache-migrate --src sqlite --src-path /var/cache/novel2all/cache.db \
                       --dst redis --dst-path redis://localhost:6379/0

# 4. 重启所有应用实例（pickup 新 config）
```

### 6.3 跨 backend 平滑迁移（V0.43 保证）

- ✅ 不丢数据
- ✅ TTL 过期条目自动跳过
- ✅ 进度回调（CLI 进度条）
- ✅ 错误累积（单条失败不中断）

---

## 7. 监控 Checklist

部署后必看指标（`/api/cache/stats` 端点）：

### 7.1 健康指标

| 指标 | 健康值 | 异常排查 |
|------|-------|----------|
| `enabled` | true | false = cache 被关掉了 |
| `size` | 应 < max_size | 满 = 频繁 LRU 淘汰，命中率会下降 |
| `hits` + `misses` | 单调递增 | 一直 0 = cache 未启用 |
| `hit_rate` | > 80% | < 50% = cache 收益低，考虑关掉 |

### 7.2 性能指标

| 指标 | 健康值 | 异常排查 |
|------|-------|----------|
| `backend` | 符合预期 backend | 切换失败 = config 没生效 |
| `lock_backend` | `sqlite` / `redis` / `fcntl` / `msvcrt` | `none` + 多进程 = 锁缺失 |
| `conn_pool_size` (SQLite) | < 100 | 持续增长 = 连接泄漏 |
| `used_memory_bytes` (Redis) | < Redis maxmemory | 超 = Redis 开始驱逐 |

### 7.3 告警阈值建议

```yaml
# Prometheus 告警示例（伪代码）
- alert: CacheHitRateLow
  expr: cache_hit_rate < 0.5
  for: 10m
  annotations: "Cache 收益低，考虑关闭或调整 TTL"

- alert: CacheMissSpike
  expr: rate(cache_misses[5m]) > rate(cache_hits[5m])
  for: 5m
  annotations: "Cache miss 突增，检查 TTL / max_size"

- alert: RedisMemoryHigh
  expr: redis_used_memory / redis_max_memory > 0.9
  for: 5m
  annotations: "Redis 即将触发 maxmemory 驱逐"
```

---

## 8. 常见陷阱（来自 V0.33-V0.45 实战教训）

### ⚠️ 陷阱 1：JSON backend 在 write_heavy 场景性能塌方

**症状**：cache 写入密集时吞吐从 1.2K ops/s 掉到 291 ops/s
**根因**：JSONFile 每次 set 都 fsync + 文件锁 + 全文件重写
**解决**：换 sqlite 或加 TTL 减少写频率

### ⚠️ 陷阱 2：JSON backend 跨 OS 不互斥

**症状**：Linux 写的 cache 文件，在 Windows 上读不到刚写入的数据
**根因**：POSIX flock vs Windows msvcrt 锁机制不互通
**解决**：同 OS 部署 JSON，或换 sqlite（内置跨 OS 锁）

### ⚠️ 陷阱 3：Redis 多应用 namespace 冲突

**症状**：多个应用共享 Redis 时，cache key 互相覆盖
**解决**：每个应用设独立 `cache_redis_namespace`（如 `novel2all_prod` / `novel2all_dev`）

### ⚠️ 陷阱 4：max_size 设太小导致命中率低

**症状**：cache stats 显示 size 一直 = max_size，hit_rate < 30%
**根因**：unique keys 远超 max_size，频繁 LRU 淘汰
**解决**：用真实工作集大小 × 2-5 作为新 max_size

### ⚠️ 陷阱 5：TTL 设太短导致"假 hit"

**症状**：cache 显示 hit 但实际内容已过期（业务逻辑仍按"新鲜"处理）
**解决**：TTL ≥ 业务能容忍的最大陈旧时间（一般 1h-7day）

### ⚠️ 陷阱 6：fakeredis mock 跑测试但生产用真 Redis 行为差异

**症状**：测试通过但生产 Redis 出错（如 Redis cluster / Sentinel）
**解决**：CI 中跑真 Redis（GitHub Actions service container），或在生产做 canary 验证

---

## 9. 生产部署 Checklist

### 9.1 启动前

- [ ] 已选定 backend（参考 §2 决策树）
- [ ] 已配置 `cache_enabled=true`
- [ ] 已配置 `cache_max_size`（参考 §4）
- [ ] 已配置 `cache_ttl_seconds`（参考 §3）
- [ ] 已配置 `cache_persist_path`（json/sqlite 必填）
- [ ] Redis 已配置 `cache_redis_url` + `cache_redis_namespace`
- [ ] `.env` 文件已 git-ignored（含 secret）

### 9.2 部署中

- [ ] 多实例部署时所有实例用**相同 backend + namespace**
- [ ] SQLite 文件目录有写权限（应用用户）
- [ ] Redis 网络可达（同机房 ≤ 1ms RTT）
- [ ] Redis maxmemory 已配（避免 OOM）
- [ ] 磁盘预留 ≥ 1GB（SQLite/JSON 后端）

### 9.3 部署后

- [ ] 跑 `curl /api/cache/stats` 验证 backend 生效
- [ ] 跑 100 次相同 prompt，验证 `hits` 增加 + `misses` 只 +1
- [ ] 监控 `hit_rate` ≥ 80%（稳态后）
- [ ] 监控 `size` < `max_size`（避免频繁 LRU）
- [ ] 设置告警（§7.3）
- [ ] 文档化 backend 选择理由（团队 oncall 参考）

### 9.4 升级路径

- [ ] 升级前备份 cache 文件（sqlite/json）
- [ ] 用 `cache-migrate` 工具平滑迁移（V0.43+）
- [ ] 升级后跑 `cache_stats()` 验证数据完整性
- [ ] 监控 hit_rate 1 小时确保无回归

---

## 10. 进阶：Cache 性能调优公式

如果需要根据具体业务数据优化：

```
预期 cache 收益 = calls_per_sec × cache_hit_rate × LLM_call_cost
                     ↑
               用 cache_stats() 监测

cache ROI = (cache_收益 - cache_成本) / cache_成本
                ↑
          Redis 服务器费用 + 维护成本

ROI > 3 时强烈推荐 cache
ROI < 1 时考虑关闭 cache
```

### 10.1 何时应该关闭 cache

- `hit_rate < 30%`（多数查询是新内容）
- `cache_cost > LLM_call_cost × 0.5`（Redis 比 LLM 还贵）
- 输入变化剧烈（每次 prompt 都不同，无复用价值）

### 10.2 何时应该升级 backend

| 当前 backend | 升级触发条件 | 目标 backend |
|--------------|--------------|--------------|
| `memory` | 需要重启保留 | `sqlite` |
| `sqlite` | 多机器部署 | `redis` |
| `redis` (LAN) | 跨 region 用户增长 | `redis` + region-local SQLite |
| `json` | 任何性能问题 | `sqlite`（V0.43 一键迁移） |

---

## 11. 参考资料

- **V0.47 基准报告**：`scripts/benchmark_cache_results.md`（4 backend × 4 workload）
- **V0.48 网络延迟基准**：`scripts/benchmark_cache_rtt_results.md`（fakeredis + RTT 注入）
- **V0.46 CacheBase 重构**：`docs/v0.46-summary.md`（待写）
- **Cache 迁移工具**：`src/novel2all/core/migration.py` + CLI `novel2all cache-migrate`
- **LLMConfig 字段**：`src/novel2all/core/provider.py:78-88`
- **Cache Backend 实现**：`src/novel2all/core/cache.py`
- **GitHub Issue**：性能问题请附 `cache_stats()` 输出 + benchmark 复现步骤

---

**作者注**：本指南基于 V0.47/V0.48 实测数据 + V0.33-V0.45 实战经验。建议每季度跑一次 benchmark 验证数据仍适用（库版本升级可能改变性能特征）。
