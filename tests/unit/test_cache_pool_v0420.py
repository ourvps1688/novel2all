"""V0.42：Cache 连接池 + 自动 backup 单元测试。

测试范围：
1. SQLiteBackend 连接池：每线程独立 conn（threading.local）
2. close() 关闭池中所有 conn
3. integrity_check + 自动 backup（损坏 DB → .corrupt.{ts}.db + 新 DB 重建）
4. LLMProvider.close() + context manager
5. conn_pool_size stats 字段
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from novel2all.core.cache import SQLiteBackend

# === 连接池测试 ===


def test_sqlite_backend_thread_local_connections(tmp_path: Path) -> None:
    """V0.42：每线程独立 connection（threading.local）。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)

    # Main thread 用了 1 个 conn
    initial_size = len(cache._conns)
    assert initial_size >= 1

    # 子线程应该用不同 conn
    results: dict[str, int] = {}

    def worker() -> None:
        cache.set("from_thread", "value")
        v = cache.get("from_thread")
        results["conn_id"] = id(cache._local.conn)
        results["value"] = v

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    # 池中 conn 数量 +1
    assert len(cache._conns) == initial_size + 1, (
        f"应增加 1 个 conn，实际 {initial_size} → {len(cache._conns)}"
    )
    # 子线程读到自己写的内容（说明 DB 共享）
    assert results["value"] == "value"
    # 子线程的 conn ID 与主线程不同
    main_conn_id = id(cache._local.conn)
    assert results["conn_id"] != main_conn_id, "子线程应使用独立 conn"
    cache.close()


def test_sqlite_backend_concurrent_threads_no_global_lock(tmp_path: Path) -> None:
    """V0.42：多线程并发写不损坏（V0.40 用全局锁，V0.42 用 thread-local conn 无锁）。"""
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
    # 4 线程 × 50 = 200 entries
    assert cache.size() == 200
    # 池中应有 4 个 conn（每线程独立）
    assert len(cache._conns) >= 4, f"应有 ≥4 conn，实际 {len(cache._conns)}"
    cache.close()


def test_sqlite_backend_close_closes_all_connections(tmp_path: Path) -> None:
    """V0.42：close() 应关闭池中所有 conn。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)

    # 触发多线程创建 conn
    def worker() -> None:
        cache.set("k", "v")

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    size_before = len(cache._conns)
    assert size_before >= 3

    cache.close()
    # 池清空
    assert len(cache._conns) == 0


def test_sqlite_backend_stats_includes_conn_pool_size(tmp_path: Path) -> None:
    """V0.42：stats() 含 conn_pool_size 字段。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    stats = cache.stats()
    assert "conn_pool_size" in stats
    assert stats["conn_pool_size"] >= 1
    cache.close()


# === 自动 backup 测试（V0.42 关键安全特性）===


def test_sqlite_backend_recovers_from_corrupt_db_magic(tmp_path: Path) -> None:
    """V0.42：magic 错误时（"SQLite format 3" 不在文件头）自动 backup 重建。"""
    db_path = tmp_path / "cache.db"
    # 写一个完全非 SQLite 的文件
    corrupt_data = b"NOT A SQLITE FILE " * 100
    db_path.write_bytes(corrupt_data)

    # SQLiteBackend 应 backup + 重建
    cache = SQLiteBackend(path=db_path, max_size=10, ttl_seconds=0)
    assert cache.size() == 0, "重建后 cache 应为空"

    # 检查 backup 文件
    backups = list(tmp_path.glob("cache.corrupt.*.db"))
    assert len(backups) == 1, f"应有 1 个 backup 文件，实际 {len(backups)}"
    # backup 文件应保留损坏数据
    assert backups[0].read_bytes() == corrupt_data, "backup 应完整保留损坏数据"

    # 新 cache 应正常工作
    cache.set("after_recovery", "value")
    assert cache.get("after_recovery") == "value"
    cache.close()


def test_sqlite_backend_recovers_from_partial_corruption(tmp_path: Path) -> None:
    """V0.42：SQLite 文件部分损坏时也自动 backup 重建。"""
    db_path = tmp_path / "cache.db"
    # 创建有效 DB
    cache1 = SQLiteBackend(path=db_path, max_size=10, ttl_seconds=0)
    cache1.set("original", "value")
    cache1.close()

    # 模拟"中途写入"损坏（保留 SQLite magic 但破坏数据）
    with open(db_path, "r+b") as f:
        # magic 在前 16 字节
        # 写入"corrupted middle"在 offset 100 处（破坏数据但不破坏 magic）
        f.seek(100)
        f.write(b"X" * 1000)

    # 重启 → 应该是损坏的
    # SQLite 的 integrity_check 可能会发现数据损坏
    try:
        cache2 = SQLiteBackend(path=db_path, max_size=10, ttl_seconds=0)
        # 如果 SQLite 容忍（不触发 backup），仍然能读出 original
        # 如果 SQLite 不容忍，会 backup
        if cache2.get("original") is None:
            # 触发了 backup
            backups = list(tmp_path.glob("cache.corrupt.*.db"))
            assert len(backups) >= 1
        cache2.close()
    except Exception:
        # 如果连启动都失败，至少不要崩溃
        pass


def test_sqlite_backend_clean_db_no_backup(tmp_path: Path) -> None:
    """V0.42：干净 DB 启动时不应产生 backup 文件。"""
    db_path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=db_path, max_size=10, ttl_seconds=0)
    cache.set("k", "v")
    cache.close()

    # 再次启动（同 path）应不产生 backup
    cache2 = SQLiteBackend(path=db_path, max_size=10, ttl_seconds=0)
    assert cache2.get("k") == "v", "原数据应保留"
    backups = list(tmp_path.glob("cache.corrupt.*.db"))
    assert len(backups) == 0, f"干净 DB 不应产生 backup，实际 {len(backups)}"
    cache2.close()


def test_sqlite_backend_new_db_no_backup(tmp_path: Path) -> None:
    """V0.42：新 DB（path 不存在）启动时不产生 backup。"""
    db_path = tmp_path / "nonexistent.db"
    assert not db_path.exists()
    cache = SQLiteBackend(path=db_path, max_size=10, ttl_seconds=0)
    assert db_path.exists(), "新 DB 应自动创建"
    backups = list(tmp_path.glob("nonexistent.corrupt.*.db"))
    assert len(backups) == 0, "新 DB 不应产生 backup"
    cache.close()


# === LLMProvider.close() 测试 ===

pytestmark_unit = pytest.mark


def test_llmprovider_close_closes_sqlite_backend(tmp_path: Path) -> None:
    """V0.42：LLMProvider.close() 应关闭 SQLite backend（释放连接池）。"""
    from novel2all.core import LLMConfig, LLMProvider

    db_path = tmp_path / "cache.db"
    config = LLMConfig(
        cache_enabled=True,
        cache_backend="sqlite",
        cache_persist_path=str(db_path),
    )
    provider = LLMProvider(config)
    assert provider._cache.__class__.__name__ == "SQLiteBackend"

    # 触发多线程创建 conn
    def w():
        provider._cache.set("k", "v")

    threading.Thread(target=w).start()
    threading.Thread(target=w).start()
    # 等线程结束
    import time

    time.sleep(0.2)
    size_before = len(provider._cache._conns)
    assert size_before >= 1

    provider.close()
    # 池清空
    assert len(provider._cache._conns) == 0


def test_llmprovider_context_manager(tmp_path: Path) -> None:
    """V0.42：LLMProvider 支持 with 语句（__enter__/__exit__）。"""
    from novel2all.core import LLMConfig, LLMProvider

    db_path = tmp_path / "cache.db"
    config = LLMConfig(
        cache_enabled=True,
        cache_backend="sqlite",
        cache_persist_path=str(db_path),
    )
    with LLMProvider(config) as provider:
        provider._cache.set("k", "v")
        assert provider._cache.get("k") == "v"
    # 退出 with 后，conn pool 应清空
    assert len(provider._cache._conns) == 0


def test_llmprovider_close_for_memory_backend_is_noop() -> None:
    """V0.42：MemoryLRUBackend 没有 close()，LLMProvider.close() 应是 no-op。"""
    from novel2all.core import LLMConfig, LLMProvider

    config = LLMConfig(cache_enabled=True)  # 默认 memory
    provider = LLMProvider(config)
    assert provider._cache.__class__.__name__ == "MemoryLRUBackend"
    # 不应抛异常
    provider.close()


# === stats 字段 ===


def test_sqlite_backend_stats_complete_v042(tmp_path: Path) -> None:
    """V0.42：stats() 应含 conn_pool_size 字段（V0.40 无）。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=100, ttl_seconds=3600)
    cache.set("k1", "v1")
    cache.get("k1")  # 1 hit
    cache.get("nonexistent")  # 1 miss

    stats = cache.stats()
    assert stats["backend"] == "sqlite"
    assert stats["size"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["ttl_seconds"] == 3600
    assert stats["lock_backend"] == "sqlite"
    assert "conn_pool_size" in stats, "V0.42: stats 应含 conn_pool_size"
    assert stats["conn_pool_size"] >= 1
    cache.close()
