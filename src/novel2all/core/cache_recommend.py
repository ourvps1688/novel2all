"""V0.51：Cache 配置智能推荐。

设计目标：
- 根据当前 cache_stats() 给出 backend / max_size / ttl_seconds 的建议
- 数据驱动（基于 V0.47 benchmark + V0.49 调优指南的规则）
- 输出可立即执行的 action 列表（含理由 + 预期收益）

数据来源：
- 输入：cache_stats() 返回字典（来自 V0.46 CacheBase.stats()）
- 输入：当前 LLMConfig（用于对比当前配置）
- 规则：见 RECOMMEND_RULES（每个 backend/TTL/size 决策的阈值）

输出结构：
{
    "current": {"backend": "json", "max_size": 256, "ttl_seconds": 0},
    "recommended": {
        "backend": {"value": "sqlite", "reason": "...", "impact": "45x faster"},
        "max_size": {"value": 512, "reason": "cache 满了，命中率会下降"},
        "ttl_seconds": {"value": 86400, "reason": "..."}
    },
    "actions": [  # 立即可执行的动作列表（按优先级排序）
        {"priority": "high", "action": "switch_backend", "from": "json", "to": "sqlite", "reason": "..."},
        ...
    ],
    "health_score": 0.85,  # 0.0-1.0，越高越健康
    "issues": ["backend_suboptimal", "size_full"],  # 检测到的问题
}

不是所有的 stats 都能产生推荐（运行时间太短、stats 缺失等）。
返回时标记 confidence="low|medium|high" 让 UI 区分显示。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FieldRecommendation:
    """单个字段的推荐。"""

    current: Any
    recommended: Any
    reason: str
    impact: str = ""  # 预期影响（如 "45x faster" / "降本 2x"）
    confidence: str = "high"  # low | medium | high


@dataclass
class CacheRecommendation:
    """V0.51：完整的 cache 配置推荐。"""

    current: dict[str, Any]
    recommended: dict[str, FieldRecommendation]
    actions: list[dict[str, Any]]
    health_score: float  # 0.0 - 1.0
    issues: list[str]
    confidence: str = "high"  # 整体推荐置信度
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "recommended": {k: asdict(v) for k, v in self.recommended.items()},
            "actions": self.actions,
            "health_score": round(self.health_score, 3),
            "issues": self.issues,
            "confidence": self.confidence,
            "notes": self.notes,
        }


# === 推荐规则（数据驱动） ===

# V0.47 benchmark: json 写性能 291 ops/s, sqlite 写 54K ops/s（提升 ~185x）
#                  json 读性能 1.2K ops/s, sqlite 读 54K ops/s（提升 ~45x）
JSON_TO_SQLITE_IMPACT = "性能提升 45-185x（V0.47 benchmark 实测）"

# V0.49 调优指南：max_size = 2-5x unique keys 数为佳
SIZE_FULL_THRESHOLD = 0.95  # size / max_size >= 95% → 触发扩容
SIZE_LOW_THRESHOLD = 0.30  # size / max_size <= 30% → 可缩容

# V0.49：TTL 推荐
TTL_LOW_HIT_RATE_THRESHOLD = 0.30  # 命中率 < 30% → TTL 可能太短
TTL_HIGH_HIT_RATE_THRESHOLD = 0.85  # 命中率 > 85% → TTL 可加长

# 健康评分权重
WEIGHTS = {
    "backend_optimal": 0.30,
    "size_healthy": 0.25,
    "ttl_healthy": 0.20,
    "hit_rate_healthy": 0.25,
}


def recommend_cache_config(
    stats: dict[str, Any],
    current_backend: str,
    current_max_size: int,
    current_ttl_seconds: int,
    total_lookups_threshold: int = 50,
) -> CacheRecommendation:
    """V0.51：根据 stats 推荐 cache 配置。

    Args:
        stats: cache_stats() 返回的字典（必填字段：hits, misses, size, max_size, backend, ttl_seconds）
        current_backend: 当前 backend 类型（memory/json/sqlite/redis）
        current_max_size: 当前 max_size
        current_ttl_seconds: 当前 ttl_seconds
        total_lookups_threshold: 总查询数 < 此阈值时 confidence="low"（数据不足）

    Returns:
        CacheRecommendation（含 recommended / actions / health_score / issues）
    """
    hits = stats.get("hits", 0)
    misses = stats.get("misses", 0)
    total = hits + misses
    hit_rate = stats.get("hit_rate", hits / total if total > 0 else 0.0)
    size = stats.get("size", 0)
    size_ratio = size / current_max_size if current_max_size > 0 else 0.0

    # 数据不足时降低置信度
    confidence = "high" if total >= total_lookups_threshold else "low"
    notes: list[str] = []
    if total < total_lookups_threshold:
        notes.append(
            f"数据量不足（仅 {total} 次查询，< {total_lookups_threshold}），"
            f"推荐仅供参考。建议累积更多流量后再看。"
        )

    recommended: dict[str, FieldRecommendation] = {}
    actions: list[dict[str, Any]] = []
    issues: list[str] = []

    # === 1. Backend 推荐 ===

    backend_rec = _recommend_backend(current_backend, total, hit_rate, size_ratio)
    recommended["backend"] = backend_rec
    if backend_rec.current != backend_rec.recommended:
        issues.append("backend_suboptimal")
        actions.append(
            {
                "priority": "high" if backend_rec.impact else "low",
                "action": "switch_backend",
                "from": current_backend,
                "to": backend_rec.recommended,
                "reason": backend_rec.reason,
                "impact": backend_rec.impact,
                "how": _how_to_switch_backend(current_backend, backend_rec.recommended),
            }
        )

    # === 2. max_size 推荐 ===

    size_rec = _recommend_max_size(current_max_size, size, size_ratio, current_backend)
    recommended["max_size"] = size_rec
    if size_rec.current != size_rec.recommended:
        if size_ratio >= SIZE_FULL_THRESHOLD:
            issues.append("size_full")
        elif size_ratio <= SIZE_LOW_THRESHOLD:
            issues.append("size_underutilized")
        actions.append(
            {
                "priority": "medium" if size_ratio >= SIZE_FULL_THRESHOLD else "low",
                "action": "resize_cache",
                "from": current_max_size,
                "to": size_rec.recommended,
                "reason": size_rec.reason,
                "impact": size_rec.impact,
                "how": f"修改环境变量 NOVEL2ALL_LLM_CACHE_MAX_SIZE={size_rec.recommended}",
            }
        )

    # === 3. ttl_seconds 推荐 ===

    ttl_rec = _recommend_ttl(current_ttl_seconds, hit_rate, total, current_backend)
    recommended["ttl_seconds"] = ttl_rec
    if ttl_rec.current != ttl_rec.recommended:
        if hit_rate < TTL_LOW_HIT_RATE_THRESHOLD:
            issues.append("ttl_too_short")
        elif hit_rate > TTL_HIGH_HIT_RATE_THRESHOLD:
            issues.append("ttl_too_long")
        actions.append(
            {
                "priority": "low",
                "action": "adjust_ttl",
                "from": current_ttl_seconds,
                "to": ttl_rec.recommended,
                "reason": ttl_rec.reason,
                "impact": ttl_rec.impact,
                "how": f"修改环境变量 NOVEL2ALL_LLM_CACHE_TTL={ttl_rec.recommended}",
            }
        )

    # === 4. 计算 health_score ===

    health_score = _compute_health_score(
        backend=current_backend,
        recommended_backend=recommended["backend"].recommended,
        size_ratio=size_ratio,
        hit_rate=hit_rate,
        ttl_seconds=current_ttl_seconds,
        total=total,
    )

    return CacheRecommendation(
        current={
            "backend": current_backend,
            "max_size": current_max_size,
            "ttl_seconds": current_ttl_seconds,
            "size": size,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hit_rate, 4),
            "total_lookups": total,
        },
        recommended=recommended,
        actions=actions,
        health_score=health_score,
        issues=issues,
        confidence=confidence,
        notes=notes,
    )


def _recommend_backend(
    current: str,
    total: int,
    hit_rate: float,
    size_ratio: float,
) -> FieldRecommendation:
    """V0.51：推荐 backend。

    规则：
    - json → sqlite（性能 45x，V0.47 benchmark）
    - memory → sqlite（如果 total > 1000，重启后丢失 cache 不划算）
    - sqlite → redis（如果 size_ratio > 95% 且总条目 > 5000，多实例共享场景）
    - 其他：保持现状
    """
    if current == "json":
        return FieldRecommendation(
            current="json",
            recommended="sqlite",
            reason=(
                "JSONFile 性能差（write_heavy 仅 291 ops/s），且无原子事务保护。"
                "SQLite 提供 45-185x 性能提升 + ACID + 跨 OS 安全。"
            ),
            impact=JSON_TO_SQLITE_IMPACT,
            confidence="high",
        )
    if current == "memory" and total > 1000:
        return FieldRecommendation(
            current="memory",
            recommended="sqlite",
            reason=(
                f"已累积 {total} 次查询，但 cache 仅在内存中，进程重启后会全部丢失。"
                "SQLite 持久化可保留命中率累计。"
            ),
            impact="避免重启后命中率归零（预估节省 30-50% LLM 成本）",
            confidence="medium",
        )
    if current == "sqlite" and size_ratio > 0.95:
        return FieldRecommendation(
            current="sqlite",
            recommended="redis",
            reason=(
                "Cache 接近满载（≥95%），单机 SQLite 可能成为瓶颈。"
                "如有多实例或跨进程需求，Redis 可共享 cache。"
            ),
            impact="支持多实例共享 + 容量上限交给 Redis 管理",
            confidence="low",
        )
    return FieldRecommendation(
        current=current,
        recommended=current,
        reason=f"当前 backend '{current}' 已适配部署场景，无需变更。",
        impact="",
        confidence="high",
    )


def _recommend_max_size(
    current: int,
    size: int,
    ratio: float,
    backend: str,
) -> FieldRecommendation:
    """V0.51：推荐 max_size。

    规则：
    - size_ratio >= 95% → 2x current（避免频繁 LRU 淘汰）
    - size_ratio <= 30% → 0.5x current（节省内存，前提 size >= 100）
    - 其他：保持
    """
    if ratio >= SIZE_FULL_THRESHOLD:
        new_size = current * 2
        return FieldRecommendation(
            current=current,
            recommended=new_size,
            reason=(
                f"Cache 接近满载（{size}/{current} = {ratio:.1%}），频繁 LRU 淘汰会导致命中率下降。"
            ),
            impact="预计命中率提升 5-15%",
            confidence="high",
        )
    if ratio <= SIZE_LOW_THRESHOLD and size >= 100:
        new_size = max(64, current // 2)
        return FieldRecommendation(
            current=current,
            recommended=new_size,
            reason=(f"Cache 利用率偏低（{size}/{current} = {ratio:.1%}），可缩容以节省内存。"),
            impact=f"节省约 {current - new_size} 条目的内存",
            confidence="medium",
        )
    return FieldRecommendation(
        current=current,
        recommended=current,
        reason=f"Cache 大小合理（{size}/{current} = {ratio:.1%}）。",
        impact="",
        confidence="high",
    )


def _recommend_ttl(
    current: int,
    hit_rate: float,
    total: int,
    backend: str,
) -> FieldRecommendation:
    """V0.51：推荐 ttl_seconds。

    规则：
    - ttl=0（永不过期）+ 内容会变 → 推荐 86400（24h，LLM 升级频率）
    - ttl>0 + hit_rate < 30% → 2x current（TTL 太短，频繁失效）
    - ttl>0 + hit_rate > 85% → 0.5x current（TTL 太长，可能服务 stale）
    - 总查询太少 → 保持现状（confidence=low）
    """
    if total < 50:
        return FieldRecommendation(
            current=current,
            recommended=current,
            reason=f"查询次数太少（{total}），暂不调整 TTL。",
            impact="",
            confidence="low",
        )

    if current == 0:
        # 永不过期 → 推荐 24h（LLM 内容稳定但会迭代）
        return FieldRecommendation(
            current=0,
            recommended=86400,
            reason=(
                "TTL=0（永不过期）可能在 LLM 升级 / prompt 调整后返回 stale 内容。"
                "24h TTL 兼顾命中率和新鲜度。"
            ),
            impact="避免 stale 内容（但可能命中率略降 1-3%）",
            confidence="medium",
        )
    if hit_rate < TTL_LOW_HIT_RATE_THRESHOLD:
        new_ttl = current * 2
        return FieldRecommendation(
            current=current,
            recommended=new_ttl,
            reason=(
                f"命中率偏低（{hit_rate:.1%} < {TTL_LOW_HIT_RATE_THRESHOLD:.0%}），"
                f"可能 TTL 太短导致频繁失效。"
            ),
            impact="TTL 加倍，预计命中率提升 5-10%",
            confidence="medium",
        )
    if hit_rate > TTL_HIGH_HIT_RATE_THRESHOLD:
        new_ttl = max(60, current // 2)
        return FieldRecommendation(
            current=current,
            recommended=new_ttl,
            reason=(
                f"命中率极高（{hit_rate:.1%} > {TTL_HIGH_HIT_RATE_THRESHOLD:.0%}），"
                f"可能 TTL 过长导致 stale 内容风险。"
            ),
            impact="TTL 减半，提升内容新鲜度",
            confidence="low",
        )
    return FieldRecommendation(
        current=current,
        recommended=current,
        reason=f"TTL={current}s 适中（命中率 {hit_rate:.1%}）。",
        impact="",
        confidence="high",
    )


def _compute_health_score(
    *,
    backend: str,
    recommended_backend: str,
    size_ratio: float,
    hit_rate: float,
    ttl_seconds: int,
    total: int,
) -> float:
    """V0.51：计算 0.0-1.0 的健康分。

    各维度加权：
    - backend_optimal (0.30)：backend 是否最优
    - size_healthy (0.25)：size 在 [30%, 95%] 区间
    - ttl_healthy (0.20)：ttl 与 hit_rate 匹配
    - hit_rate_healthy (0.25)：命中率 >= 50% 为佳
    """
    score = 0.0

    # Backend optimal
    if backend == recommended_backend:
        score += WEIGHTS["backend_optimal"]

    # Size healthy (30% <= ratio <= 95% 为佳)
    if 0.30 <= size_ratio <= 0.95:
        score += WEIGHTS["size_healthy"]
    elif size_ratio < 0.30:
        score += WEIGHTS["size_healthy"] * 0.7  # 略低分（可用但浪费）
    else:  # > 95%
        score += WEIGHTS["size_healthy"] * 0.3  # 低分（频繁淘汰）

    # TTL healthy
    if ttl_seconds == 0 and total > 100:
        score += WEIGHTS["ttl_healthy"] * 0.6  # 永不过期有 stale 风险
    elif 60 <= ttl_seconds <= 7 * 86400:
        score += WEIGHTS["ttl_healthy"]
    else:
        score += WEIGHTS["ttl_healthy"] * 0.5

    # Hit rate healthy
    if total < 10:
        score += WEIGHTS["hit_rate_healthy"] * 0.5  # 数据不足
    elif hit_rate >= 0.80:
        score += WEIGHTS["hit_rate_healthy"]
    elif hit_rate >= 0.50:
        score += WEIGHTS["hit_rate_healthy"] * 0.7
    elif hit_rate >= 0.30:
        score += WEIGHTS["hit_rate_healthy"] * 0.4
    else:
        score += WEIGHTS["hit_rate_healthy"] * 0.1

    return min(1.0, max(0.0, score))


def _how_to_switch_backend(current: str, target: str) -> str:
    """V0.51：生成 backend 切换的操作步骤。"""
    if current == "json" and target == "sqlite":
        return (
            "1) 设置 NOVEL2ALL_LLM_CACHE_BACKEND=sqlite\n"
            "2) 设置 NOVEL2ALL_LLM_CACHE_PERSIST_PATH=/path/to/cache.db\n"
            "3) 跑 `novel2all cache-migrate --src json --src-path old.json --dst sqlite --dst-path new.db`\n"
            "4) 重启应用"
        )
    if current == "memory" and target == "sqlite":
        return (
            "1) 设置 NOVEL2ALL_LLM_CACHE_BACKEND=sqlite\n"
            "2) 设置 NOVEL2ALL_LLM_CACHE_PERSIST_PATH=/path/to/cache.db\n"
            "3) 重启应用（旧 memory cache 丢弃，首次启动后重新累积）"
        )
    if current == "sqlite" and target == "redis":
        return (
            "1) 启动 Redis 服务（docker run -d -p 6379:6379 redis:7-alpine）\n"
            "2) 设置 NOVEL2ALL_LLM_CACHE_BACKEND=redis\n"
            "3) 设置 NOVEL2ALL_LLM_CACHE_REDIS_URL=redis://localhost:6379/0\n"
            "4) 跑 `novel2all cache-migrate --src sqlite --src-path old.db --dst redis --dst-path redis://localhost:6379/0`\n"
            "5) 重启应用"
        )
    return f"请参考 docs/cache-tuning-guide.md §6 迁移路径（{current} → {target}）"
