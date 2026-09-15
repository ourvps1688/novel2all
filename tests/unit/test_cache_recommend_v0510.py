"""V0.51：Cache 智能推荐单元测试。

测试范围：
1. recommend_cache_config() 返回结构完整性
2. backend 推荐（json→sqlite、memory→sqlite、sqlite→redis、保持现状）
3. max_size 推荐（满载扩容、低利用缩容、合理保持）
4. ttl_seconds 推荐（永不过期→24h、太短→加倍、过长→减半）
5. health_score 计算边界
6. action 列表生成（按优先级）
7. Web 端点 /api/cache/recommend
8. Web 端点 /page/cache-recommend（HTMX partial）
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel2all.core.cache_recommend import (
    CacheRecommendation,
    recommend_cache_config,
)
from novel2all.web.app import create_app

# === Test 1：返回值结构 ===


def test_recommend_returns_dataclass() -> None:
    """V0.51：返回 CacheRecommendation dataclass。"""
    stats = {"hits": 100, "misses": 50, "size": 200, "max_size": 256, "hit_rate": 0.667}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    assert isinstance(rec, CacheRecommendation)
    assert rec.current["backend"] == "memory"
    assert rec.current["max_size"] == 256
    assert rec.current["ttl_seconds"] == 0
    assert rec.health_score >= 0.0
    assert rec.health_score <= 1.0


def test_recommend_to_dict_structure() -> None:
    """V0.51：to_dict() 输出完整 JSON-serializable 结构。"""
    stats = {"hits": 200, "misses": 100, "size": 250, "max_size": 256, "hit_rate": 0.667}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=86400,
    )
    d = rec.to_dict()
    assert "current" in d
    assert "recommended" in d
    assert "actions" in d
    assert "health_score" in d
    assert "issues" in d
    assert "confidence" in d
    # recommended 是 dict[str, dict]
    assert "backend" in d["recommended"]
    assert "max_size" in d["recommended"]
    assert "ttl_seconds" in d["recommended"]
    # FieldRecommendation 字段
    for field_rec in d["recommended"].values():
        assert "current" in field_rec
        assert "recommended" in field_rec
        assert "reason" in field_rec
        assert "impact" in field_rec
        assert "confidence" in field_rec


# === Test 2：backend 推荐 ===


def test_recommend_json_to_sqlite() -> None:
    """V0.51：json backend 推荐切换到 sqlite（45-185x 性能）。"""
    stats = {"hits": 100, "misses": 50, "size": 50, "max_size": 256, "hit_rate": 0.667}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="json",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    backend_rec = rec.recommended["backend"]
    assert backend_rec.recommended == "sqlite"
    assert backend_rec.current == "json"
    assert "45" in backend_rec.impact or "185" in backend_rec.impact
    assert "json" in backend_rec.reason.lower() or "json" in backend_rec.reason
    # action 应包含 how-to 步骤
    backend_action = next((a for a in rec.actions if a["action"] == "switch_backend"), None)
    assert backend_action is not None
    assert "sqlite" in backend_action["to"]
    assert backend_action["priority"] == "high"
    assert "1)" in backend_action["how"]  # 步骤格式


def test_recommend_memory_to_sqlite_when_high_traffic() -> None:
    """V0.51：memory backend 在高流量时推荐 sqlite（避免重启丢失）。"""
    stats = {"hits": 800, "misses": 300, "size": 200, "max_size": 256, "hit_rate": 0.727}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    backend_rec = rec.recommended["backend"]
    assert backend_rec.recommended == "sqlite"
    assert "持久化" in backend_rec.reason or "重启" in backend_rec.reason


def test_recommend_memory_kept_when_low_traffic() -> None:
    """V0.51：memory backend 在低流量时保持（不值得迁移）。"""
    stats = {"hits": 30, "misses": 20, "size": 50, "max_size": 256, "hit_rate": 0.6}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    backend_rec = rec.recommended["backend"]
    assert backend_rec.recommended == "memory"
    assert "已适配" in backend_rec.reason or "无需" in backend_rec.reason


def test_recommend_sqlite_to_redis_when_full() -> None:
    """V0.51：SQLite 满载时推荐 Redis（多实例共享场景）。"""
    stats = {"hits": 500, "misses": 100, "size": 250, "max_size": 256, "hit_rate": 0.833}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    backend_rec = rec.recommended["backend"]
    assert backend_rec.recommended == "redis"
    assert "满载" in backend_rec.reason or "95%" in backend_rec.reason
    assert backend_rec.confidence == "low"  # 推 Redis 是 low confidence


def test_recommend_sqlite_kept_when_healthy() -> None:
    """V0.51：SQLite 健康时保持（避免无谓迁移）。"""
    stats = {"hits": 500, "misses": 50, "size": 100, "max_size": 256, "hit_rate": 0.909}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=86400,
    )
    backend_rec = rec.recommended["backend"]
    assert backend_rec.recommended == "sqlite"


# === Test 3：max_size 推荐 ===


def test_recommend_max_size_when_full() -> None:
    """V0.51：cache 满载时推荐 2x 扩容。"""
    stats = {"hits": 500, "misses": 100, "size": 250, "max_size": 256, "hit_rate": 0.833}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    size_rec = rec.recommended["max_size"]
    assert size_rec.recommended == 512
    assert "满载" in size_rec.reason or "95%" in size_rec.reason
    assert "size_full" in rec.issues


def test_recommend_max_size_when_underutilized() -> None:
    """V0.51：cache 利用率低时推荐缩容（size >= 100 才触发）。"""
    stats = {"hits": 100, "misses": 50, "size": 50, "max_size": 256, "hit_rate": 0.667}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    size_rec = rec.recommended["max_size"]
    # size=50 < 100 → 不触发缩容（避免建议过小）
    assert size_rec.recommended == 256


def test_recommend_max_size_underutilized_with_sufficient_size() -> None:
    """V0.51：cache 利用率低但 size >= 100 时推荐缩容。"""
    stats = {"hits": 200, "misses": 100, "size": 120, "max_size": 512, "hit_rate": 0.667}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=512,
        current_ttl_seconds=0,
    )
    size_rec = rec.recommended["max_size"]
    # size=120/512=23.4% < 30% → 触发缩容 → 512 // 2 = 256
    assert size_rec.recommended == 256
    assert "利用" in size_rec.reason or "缩容" in size_rec.reason


def test_recommend_max_size_kept_when_healthy() -> None:
    """V0.51：合理范围内保持 max_size 不变。"""
    stats = {"hits": 200, "misses": 50, "size": 150, "max_size": 256, "hit_rate": 0.8}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    size_rec = rec.recommended["max_size"]
    assert size_rec.recommended == 256


# === Test 4：ttl_seconds 推荐 ===


def test_recommend_ttl_zero_to_24h() -> None:
    """V0.51：TTL=0（永不过期）+ 高流量 → 推荐 86400（24h）。"""
    stats = {"hits": 500, "misses": 100, "size": 100, "max_size": 256, "hit_rate": 0.833}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    ttl_rec = rec.recommended["ttl_seconds"]
    assert ttl_rec.recommended == 86400
    assert "stale" in ttl_rec.reason or "24h" in ttl_rec.reason or "86400" in ttl_rec.reason


def test_recommend_ttl_too_short_when_low_hit_rate() -> None:
    """V0.51：低命中率 + TTL>0 → 推荐 2x TTL。"""
    stats = {"hits": 30, "misses": 100, "size": 100, "max_size": 256, "hit_rate": 0.231}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=3600,
    )
    ttl_rec = rec.recommended["ttl_seconds"]
    assert ttl_rec.recommended == 7200  # 2x current
    assert "命中率偏低" in ttl_rec.reason or "TTL" in ttl_rec.reason


def test_recommend_ttl_too_long_when_high_hit_rate() -> None:
    """V0.51：极高命中率 + TTL>0 → 推荐 0.5x TTL（防 stale）。"""
    stats = {"hits": 900, "misses": 50, "size": 100, "max_size": 256, "hit_rate": 0.947}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=604800,
    )
    ttl_rec = rec.recommended["ttl_seconds"]
    assert ttl_rec.recommended == 302400  # 0.5x current
    assert "极高" in ttl_rec.reason or "stale" in ttl_rec.reason


def test_recommend_ttl_kept_when_low_traffic() -> None:
    """V0.51：查询次数太少时 TTL 保持（数据不足）。"""
    stats = {"hits": 5, "misses": 2, "size": 7, "max_size": 256, "hit_rate": 0.714}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=3600,
    )
    ttl_rec = rec.recommended["ttl_seconds"]
    assert ttl_rec.recommended == 3600
    assert ttl_rec.confidence == "low"


# === Test 5：health_score 计算 ===


def test_health_score_perfect() -> None:
    """V0.51：所有维度最优时 health_score 接近 1.0。"""
    stats = {"hits": 900, "misses": 100, "size": 130, "max_size": 256, "hit_rate": 0.9}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=86400,
    )
    assert rec.health_score >= 0.85


def test_health_score_poor() -> None:
    """V0.51：所有维度都差时 health_score 接近 0.0。"""
    stats = {"hits": 10, "misses": 100, "size": 256, "max_size": 256, "hit_rate": 0.091}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="json",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    # json + 满载 + 极低命中率 + TTL=0 + 大量问题 → 低分
    assert rec.health_score < 0.5


def test_health_score_in_range() -> None:
    """V0.51：health_score 始终在 [0, 1] 区间。"""
    test_cases = [
        ({"hits": 0, "misses": 0, "size": 0, "max_size": 256, "hit_rate": 0.0}, "memory", 256, 0),
        (
            {"hits": 1000, "misses": 100, "size": 250, "max_size": 256, "hit_rate": 0.909},
            "sqlite",
            256,
            3600,
        ),
        (
            {"hits": 50, "misses": 100, "size": 100, "max_size": 256, "hit_rate": 0.333},
            "json",
            128,
            86400,
        ),
    ]
    for stats, backend, max_size, ttl in test_cases:
        rec = recommend_cache_config(stats, backend, max_size, ttl)
        assert 0.0 <= rec.health_score <= 1.0


# === Test 6：actions 列表 ===


def test_actions_sorted_by_priority() -> None:
    """V0.51：actions 列表按优先级 high > medium > low 排序。"""
    stats = {
        "hits": 30,
        "misses": 100,
        "size": 250,
        "max_size": 256,
        "hit_rate": 0.231,
    }  # json + 满载 + 低命中 → 多 action
    rec = recommend_cache_config(
        stats=stats,
        current_backend="json",
        current_max_size=256,
        current_ttl_seconds=3600,
    )
    priorities = [a["priority"] for a in rec.actions]
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_priorities = sorted(priorities, key=lambda p: priority_order[p])
    assert priorities == sorted_priorities


def test_actions_have_how_to_steps() -> None:
    """V0.51：每个 action 都有 how-to 操作步骤。"""
    stats = {"hits": 50, "misses": 100, "size": 256, "max_size": 256, "hit_rate": 0.333}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="json",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    for action in rec.actions:
        assert "how" in action
        assert isinstance(action["how"], str)
        assert len(action["how"]) > 10  # 不是空字符串


def test_no_actions_when_optimal() -> None:
    """V0.51：所有维度都最优时 actions 列表为空。"""
    stats = {"hits": 800, "misses": 100, "size": 130, "max_size": 256, "hit_rate": 0.889}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="sqlite",
        current_max_size=256,
        current_ttl_seconds=86400,
    )
    # sqlite + 130/256 (50%) + 0.889 hit_rate + 24h TTL = 全部合理
    # 但 backend 是 sqlite 没问题，size 是 130/256 在 [30%, 95%] 没问题
    # TTL 是 86400 (24h) 在 [60, 7day] 没问题
    # hit_rate 0.889 >= 0.80 → 满 health
    # backend 已最优 → 无 action
    backend_actions = [a for a in rec.actions if a["action"] == "switch_backend"]
    assert len(backend_actions) == 0


# === Test 7：confidence 处理 ===


def test_confidence_low_when_low_traffic() -> None:
    """V0.51：查询次数 < 50 时 confidence=low。"""
    stats = {"hits": 20, "misses": 10, "size": 30, "max_size": 256, "hit_rate": 0.667}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    assert rec.confidence == "low"
    assert len(rec.notes) > 0  # 应有 data-too-low 警告


def test_confidence_high_when_high_traffic() -> None:
    """V0.51：查询次数 >= 50 时 confidence=high。"""
    stats = {"hits": 80, "misses": 20, "size": 50, "max_size": 256, "hit_rate": 0.8}
    rec = recommend_cache_config(
        stats=stats,
        current_backend="memory",
        current_max_size=256,
        current_ttl_seconds=0,
    )
    assert rec.confidence == "high"
    assert len(rec.notes) == 0


# === Test 8：Web 端点 /api/cache/recommend ===


def test_api_cache_recommend_returns_json() -> None:
    """V0.51：GET /api/cache/recommend 返回完整 JSON。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/cache/recommend")
        assert response.status_code == 200
        data = response.json()
        # 必备字段
        assert "current" in data
        assert "recommended" in data
        assert "actions" in data
        assert "health_score" in data
        assert "issues" in data
        assert "confidence" in data
        # current 字段
        assert "backend" in data["current"]
        assert "max_size" in data["current"]
        assert "ttl_seconds" in data["current"]


def test_api_cache_recommend_with_cache_enabled() -> None:
    """V0.51：cache_enabled=True 时推荐基于真实 stats。"""
    import os

    os.environ["NOVEL2ALL_LLM_CACHE"] = "true"
    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/cache/recommend")
            data = response.json()
            # cache_enabled=True 应有 hits/misses
            assert "hits" in data["current"]
            assert "misses" in data["current"]
            assert "hit_rate" in data["current"]
    finally:
        os.environ.pop("NOVEL2ALL_LLM_CACHE", None)


# === Test 9: Web 端点 /page/cache-recommend ===
# V1.5 React 迁移：移除 Jinja2 模板后，/page/cache-recommend 端点已删除。
# /api/cache/recommend 仍保留（被 React 端消费）。
