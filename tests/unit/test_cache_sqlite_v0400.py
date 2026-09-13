"""V0.40：SQLite cache backend 单元测试。

测试范围：
1. SQLiteBackend 基础：get/set/size/clear/stats
2. TTL 行为：ttl=0 永不过期，ttl>0 按 expires_at 过期
3. LRU 淘汰：超过 max_size 按 last_accessed_at ASC 删除
4. 持久化：跨实例数据保留
5. 并发：多线程同时写不损坏 DB
6. WAL 模式：journal_mode 应为 WAL
7. 跨 OS 兼容：SQLite 锁机制自带，无需 fcntl/msvcrt
8. LLMConfig 集成：cache_backend="sqlite" 自动选 SQLiteBackend
9. CacheLock 不需要：SQLiteBackend 不用 CacheLock
10. close() 方法：显式关闭连接
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from novel2all.core.cache import SQLiteBackend

# === 基础功能测试 ===


def test_sqlite_backend_basic_set_get(tmp_path: Path) -> None:
    """V0.40：基本 set/get roundtrip。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    assert cache.size() == 1


def test_sqlite_backend_get_missing_returns_none(tmp_path: Path) -> None:
    """V0.40：get 不存在的 key 返回 None。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache.get("nonexistent") is None
    assert cache._misses == 1


def test_sqlite_backend_overwrite_existing(tmp_path: Path) -> None:
    """V0.40：set 已存在的 key 应覆盖（INSERT OR REPLACE）。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    cache.set("k1", "v2_updated")
    assert cache.get("k1") == "v2_updated"
    assert cache.size() == 1


def test_sqlite_backend_tuple_key(tmp_path: Path) -> None:
    """V0.40：tuple key 通过 encode_key 转为字符串。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    tuple_key = ("model", "sys_hash", "user_hash", 0.7)
    cache.set(tuple_key, "response")
    assert cache.get(tuple_key) == "response"
    # 验证 SQLite 内部存的是字符串（encode_key 用 ":" 分隔）
    assert cache.get("model:sys_hash:user_hash:0.7") == "response"


# === TTL 测试 ===


def test_sqlite_backend_ttl_zero_never_expires(tmp_path: Path) -> None:
    """V0.40：ttl=0 永不过期。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    # 即使等 1 秒也不过期（TTL=0）
    time.sleep(0.1)
    assert cache.get("k1") == "v1"


def test_sqlite_backend_ttl_expiration(tmp_path: Path) -> None:
    """V0.40：ttl>0 时过期条目返回 None。"""
    path = tmp_path / "cache.db"
    # TTL = 1 秒
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=1)
    cache.set("k1", "v1")
    # 立即读取应命中
    assert cache.get("k1") == "v1"
    # 等 1.2 秒后过期
    time.sleep(1.2)
    assert cache.get("k1") is None, "TTL 过期后应返回 None"


def test_sqlite_backend_ttl_cleanup_on_init(tmp_path: Path) -> None:
    """V0.40：初始化时自动清理过期条目。"""
    path = tmp_path / "cache.db"

    # 第一次：写入 ttl=1 秒的条目
    cache1 = SQLiteBackend(path=path, max_size=10, ttl_seconds=1)
    cache1.set("k1", "v1")
    cache1.close()
    time.sleep(1.2)

    # 第二次：相同路径 + ttl=1 秒，初始化时应清理 k1
    cache2 = SQLiteBackend(path=path, max_size=10, ttl_seconds=1)
    assert cache2.size() == 0, "启动时应清理过期条目"


# === LRU 测试 ===


def test_sqlite_backend_lru_eviction(tmp_path: Path) -> None:
    """V0.40：超过 max_size 时按 last_accessed_at ASC 淘汰最旧。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=3, ttl_seconds=0)
    cache.set("k1", "v1")
    time.sleep(0.01)  # 拉开时间戳
    cache.set("k2", "v2")
    time.sleep(0.01)
    cache.set("k3", "v3")
    assert cache.size() == 3
    # 触发淘汰
    cache.set("k4", "v4")
    assert cache.size() == 3
    # k1 应被淘汰（最旧）
    assert cache.get("k1") is None
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"
    assert cache.get("k4") == "v4"


def test_sqlite_backend_lru_get_updates_access_time(tmp_path: Path) -> None:
    """V0.40：get 命中时更新 last_accessed_at（V0.29 真 LRU 语义）。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=3, ttl_seconds=0)
    cache.set("k1", "v1")
    time.sleep(0.01)
    cache.set("k2", "v2")
    time.sleep(0.01)
    cache.set("k3", "v3")
    # 访问 k1（应更新 last_accessed_at → 变成最新）
    cache.get("k1")
    # 触发淘汰
    cache.set("k4", "v4")
    # k2 应被淘汰（现在最旧的是 k2，k1 被访问过更新了）
    assert cache.get("k1") == "v1"
    assert cache.get("k2") is None
    assert cache.get("k3") == "v3"
    assert cache.get("k4") == "v4"


# === 持久化测试 ===


def test_sqlite_backend_persistence_across_instances(tmp_path: Path) -> None:
    """V0.40：跨实例保留数据（V0.33 关键能力）。"""
    path = tmp_path / "cache.db"

    # 第一个实例写
    cache1 = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    cache1.set("k1", "v1")
    cache1.set("k2", "v2")
    assert cache1.size() == 2
    cache1.close()

    # 第二个实例读（同 path）
    cache2 = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache2.size() == 2
    assert cache2.get("k1") == "v1"
    assert cache2.get("k2") == "v2"


# === 并发测试 ===


def test_sqlite_backend_concurrent_threads(tmp_path: Path) -> None:
    """V0.40：多线程并发写不损坏 DB（SQLite 内置锁 + autocommit）。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=1000, ttl_seconds=0)

    errors: list[str] = []

    def worker(thread_id: int) -> None:
        try:
            for i in range(50):
                cache.set(f"t{thread_id}_k{i}", f"v{i}")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发写异常: {errors[:2]}"
    # 4 线程 × 50 entries = 200（无重复 key）
    assert cache.size() == 200
    # DB 文件仍合法
    with sqlite3.connect(str(path)) as conn:
        n = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        assert n == 200


# === Schema 验证 ===


def test_sqlite_backend_wal_mode_active(tmp_path: Path) -> None:
    """V0.40：默认启用 WAL 模式（reader 不阻塞 writer）。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    # 检查 journal_mode
    mode = cache._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"应启用 WAL 模式，实际={mode}"
    cache.close()


def test_sqlite_backend_schema_has_required_columns(tmp_path: Path) -> None:
    """V0.40：schema 应含 key/value/expires_at/last_accessed_at/created_at。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    # PRAGMA table_info
    cols = cache._conn.execute("PRAGMA table_info(cache)").fetchall()
    col_names = [c[1] for c in cols]
    for required in ("key", "value", "expires_at", "last_accessed_at", "created_at"):
        assert required in col_names, f"schema 应含 {required}，实际={col_names}"
    cache.close()


def test_sqlite_backend_has_lru_index(tmp_path: Path) -> None:
    """V0.40：last_accessed_at 索引加速 LRU 淘汰。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    indexes = cache._conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    index_names = [i[0] for i in indexes]
    assert "idx_last_accessed" in index_names, f"应含 LRU 索引，实际={index_names}"
    cache.close()


# === LLMConfig 集成测试 ===


def test_llmconfig_supports_sqlite_backend(tmp_path: Path) -> None:
    """V0.40：LLMConfig.cache_backend="sqlite" 应自动选 SQLiteBackend。"""
    from novel2all.core import LLMConfig, LLMProvider

    db_path = tmp_path / "cache.db"
    config = LLMConfig(
        cache_enabled=True,
        cache_backend="sqlite",
        cache_persist_path=str(db_path),
    )
    provider = LLMProvider(config)
    assert provider._cache.__class__.__name__ == "SQLiteBackend"
    # stats 应含 backend="sqlite"
    stats = provider.cache_stats()
    assert stats["backend"] == "sqlite"
    assert stats["lock_backend"] == "sqlite"


def test_llmconfig_default_sqlite_path(tmp_path: Path) -> None:
    """V0.40：cache_backend="sqlite" 但不指定 path 时，用默认路径 .novel2all/cache.db。"""
    import os

    from novel2all.core import LLMConfig, LLMProvider

    # 切到 tmp_path
    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        config = LLMConfig(cache_enabled=True, cache_backend="sqlite")
        provider = LLMProvider(config)
        stats = provider.cache_stats()
        # 默认路径应含 .novel2all 和 cache.db（跨平台：/ or \）
        normalized = stats["persist_path"].replace("\\", "/")
        assert ".novel2all/cache.db" in normalized
    finally:
        os.chdir(old_cwd)


def test_llmconfig_json_backend_still_works(tmp_path: Path) -> None:
    """V0.40：V0.33 JSON backend 仍工作（向后兼容）。"""
    from novel2all.core import LLMConfig, LLMProvider

    json_path = tmp_path / "cache.json"
    config = LLMConfig(
        cache_enabled=True,
        cache_backend="json",
        cache_persist_path=str(json_path),
    )
    provider = LLMProvider(config)
    assert provider._cache.__class__.__name__ == "JSONFileBackend"


def test_llmconfig_memory_backend_default(tmp_path: Path) -> None:
    """V0.40：默认 backend 仍是 memory（向后兼容）。"""
    from novel2all.core import LLMConfig, LLMProvider

    config = LLMConfig(cache_enabled=True)  # cache_backend 默认 "memory"
    provider = LLMProvider(config)
    assert provider._cache.__class__.__name__ == "MemoryLRUBackend"


# === close() 测试 ===


def test_sqlite_backend_close_releases_connection(tmp_path: Path) -> None:
    """V0.40：close() 应释放 SQLite 连接。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    cache.close()
    # 重新打开应能读取（说明连接被正确关闭 + 数据落盘）
    cache2 = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache2.get("k1") == "v1"


# === 跨 OS / 跨进程验证（无需 fcntl/msvcrt）===


def test_sqlite_backend_no_cache_lock_needed(tmp_path: Path) -> None:
    """V0.40：SQLiteBackend 不需要 CacheLock（内置锁机制）。

    验证：没有 lock_backend 字段依赖 CacheLock 类。
    """
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    # stats 的 lock_backend 应是 "sqlite"（不是 fcntl/msvcrt/none）
    assert cache.stats()["lock_backend"] == "sqlite"
    cache.close()


# === Stats 测试 ===


def test_sqlite_backend_stats_complete(tmp_path: Path) -> None:
    """V0.40：stats() 应含全部 V0.40 字段。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=100, ttl_seconds=3600)
    cache.set("k1", "v1")
    cache.get("k1")  # 1 hit
    cache.get("nonexistent")  # 1 miss

    stats = cache.stats()
    assert stats["enabled"] is True
    assert stats["backend"] == "sqlite"
    assert stats["size"] == 1
    assert stats["max_size"] == 100
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["ttl_seconds"] == 3600
    assert str(path) in stats["persist_path"]
    assert stats["lock_backend"] == "sqlite"
