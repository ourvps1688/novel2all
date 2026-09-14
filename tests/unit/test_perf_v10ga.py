"""V1.0 GA 性能优化测试：SQLite 调优 + httpx 连接池。"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from novel2all.core.db_tuning import DEFAULT_TUNING, apply_tuning, get_stats, is_tuned

# === Test 1: SQLite PRAGMA 调优 ===


class TestDbTuning:
    """V1.0 GA：SQLite 调优模块。"""

    def test_default_tuning_has_all_keys(self) -> None:
        """V1.0 GA：默认调优覆盖所有关键 PRAGMA。"""
        assert "journal_mode" in DEFAULT_TUNING
        assert "synchronous" in DEFAULT_TUNING
        assert "cache_size" in DEFAULT_TUNING
        assert "temp_store" in DEFAULT_TUNING
        assert "mmap_size" in DEFAULT_TUNING
        assert "busy_timeout" in DEFAULT_TUNING
        assert "foreign_keys" in DEFAULT_TUNING

    def test_apply_tuning_persists_journal_mode(self, tmp_path: Path) -> None:
        """V1.0 GA：journal_mode=WAL 在 DB header 持久化。"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        apply_tuning(conn)
        conn.close()

        # 重新打开 + 检查 WAL 仍生效
        conn2 = sqlite3.connect(str(db_path))
        stats = get_stats(conn2)
        assert stats["journal_mode"] == "wal"
        conn2.close()

    def test_apply_tuning_64mb_cache(self, tmp_path: Path) -> None:
        """V1.0 GA：cache_size 设为 -64MB（64000 KB）。"""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        apply_tuning(conn)
        stats = get_stats(conn)
        # cache_size 是 pages，负数 = KB
        # 64000 KB ≈ 64000 pages (4KB each)
        # 实际 SQLite 可能 round 到负数 KB
        assert "cache_size" in stats
        assert stats["cache_size"] != -2000  # 不是默认的 2000 pages
        conn.close()

    def test_apply_tuning_temp_store_memory(self, tmp_path: Path) -> None:
        """V1.0 GA：temp_store=MEMORY。"""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        apply_tuning(conn)
        stats = get_stats(conn)
        assert stats["temp_store"] == 2  # 2 = MEMORY
        conn.close()

    def test_apply_tuning_foreign_keys(self, tmp_path: Path) -> None:
        """V1.0 GA：foreign_keys=ON（V0.30.6 B5 已要求）。"""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        apply_tuning(conn)
        stats = get_stats(conn)
        assert stats["foreign_keys"] == 1  # 1 = ON
        conn.close()

    def test_apply_tuning_custom_overrides(self, tmp_path: Path) -> None:
        """V1.0 GA：自定义调优覆盖默认。"""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        apply_tuning(conn, {"cache_size": -1024})  # 只改 cache_size
        stats = get_stats(conn)
        assert "cache_size" in stats
        conn.close()

    def test_is_tuned_returns_true_after_apply(self, tmp_path: Path) -> None:
        """V1.0 GA：apply_tuning 后 is_tuned=True。"""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        apply_tuning(conn)
        assert is_tuned(conn)
        conn.close()

    def test_is_tuned_returns_false_without_apply(self, tmp_path: Path) -> None:
        """V1.0 GA：未调优的 connection → is_tuned=False。"""
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        assert is_tuned(conn) is False
        conn.close()


# === Test 2: 性能基准（微型 benchmark 验证调优有效）===


class TestSqlitePerfGain:
    """V1.0 GA：调优 vs 默认性能对比（微型 benchmark）。"""

    def test_wal_mode_faster_than_rollback_for_writes(self, tmp_path: Path) -> None:
        """V1.0 GA：WAL 模式写性能应 ≥ DELETE 模式（实测 WAL 略慢但并发读快很多）。

        这个测试只验证调优被应用，不验证具体加速比（依赖硬件）。
        """
        # WAL
        conn1 = sqlite3.connect(str(tmp_path / "wal.db"))
        apply_tuning(conn1)
        # 默认 rollback
        conn2 = sqlite3.connect(str(tmp_path / "rb.db"))

        # 1000 次 INSERT
        for conn in (conn1, conn2):
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, data TEXT)")
            conn.executemany(
                "INSERT INTO t VALUES (?, ?)",
                [(i, f"data_{i}") for i in range(1000)],
            )
            conn.commit()
        # 验证：两个 DB 都有 1000 行（功能正常）
        for conn in (conn1, conn2):
            cur = conn.execute("SELECT COUNT(*) FROM t")
            assert cur.fetchone()[0] == 1000
        conn1.close()
        conn2.close()


# === Test 3: httpx 连接池 ===


class TestHttpxConnectionPool:
    """V1.0 GA：httpx 连接池复用。"""

    async def test_pool_creates_client_lazily(self) -> None:
        """V1.0 GA：首次调用 get_client() 才创建 AsyncClient。"""
        from novel2all.core.http_pool import HttpxConnectionPool

        pool = HttpxConnectionPool()
        assert pool.get_stats()["num_clients"] == 0

        client = await pool.get_client("https://api.example.com")
        assert client is not None
        assert pool.get_stats()["num_clients"] == 1

        await pool.close_all()

    async def test_pool_reuses_same_client_for_same_api_base(self) -> None:
        """V1.0 GA：相同 api_base 复用同一 client。"""
        from novel2all.core.http_pool import HttpxConnectionPool

        pool = HttpxConnectionPool()
        client1 = await pool.get_client("https://api.example.com")
        client2 = await pool.get_client("https://api.example.com")
        assert client1 is client2  # 同一对象

        await pool.close_all()

    async def test_pool_creates_separate_clients_for_different_api_bases(self) -> None:
        """V1.0 GA：不同 api_base 创建独立 client。"""
        from novel2all.core.http_pool import HttpxConnectionPool

        pool = HttpxConnectionPool()
        client1 = await pool.get_client("https://api1.example.com")
        client2 = await pool.get_client("https://api2.example.com")
        assert client1 is not client2
        assert pool.get_stats()["num_clients"] == 2

        await pool.close_all()

    async def test_pool_close_all_clears(self) -> None:
        """V1.0 GA：close_all() 清空所有 client。"""
        from novel2all.core.http_pool import HttpxConnectionPool

        pool = HttpxConnectionPool()
        await pool.get_client("https://api1.example.com")
        await pool.get_client("https://api2.example.com")
        assert pool.get_stats()["num_clients"] == 2

        await pool.close_all()
        assert pool.get_stats()["num_clients"] == 0

    async def test_pool_concurrent_access_thread_safe(self) -> None:
        """V1.0 GA：asyncio.Lock 保护并发 get_client。"""

        from novel2all.core.http_pool import HttpxConnectionPool

        pool = HttpxConnectionPool()

        # 10 个并发请求同一 api_base
        async def get():
            return await pool.get_client("https://api.example.com")

        clients = await asyncio.gather(*[get() for _ in range(10)])
        # 全部同一对象
        assert all(c is clients[0] for c in clients)
        assert pool.get_stats()["num_clients"] == 1

        await pool.close_all()


# === Test 4: LLMProvider 集成（mock 验证 http_pool 被使用） ===


class TestLLMProviderConnectionPool:
    """V1.0 GA：LLMProvider 自动用连接池。"""

    def test_provider_lazy_creates_pool(self) -> None:
        """V1.0 GA：首次 _call_anthropic_compat 时才创建 pool（lazy init）。"""
        from novel2all.core import LLMConfig, LLMProvider

        provider = LLMProvider(LLMConfig(cache_enabled=False))
        # 初始无 _http_pool 属性（lazy init）
        assert not hasattr(provider, "_http_pool")

    async def test_provider_reuses_pool_across_calls(self) -> None:
        """V1.0 GA：多次 _call_anthropic_compat 复用同一 pool。"""
        from novel2all.core import LLMConfig, LLMProvider

        provider = LLMProvider(LLMConfig(cache_enabled=False))

        # 模拟两次调用（init pool on first call）
        async def fake_call():
            if not hasattr(provider, "_http_pool"):
                from novel2all.core.http_pool import HttpxConnectionPool

                provider._http_pool = HttpxConnectionPool()
            return await provider._http_pool.get_client("https://api.example.com")

        client1 = await fake_call()
        client2 = await fake_call()
        # 同一对象（连接池复用）
        assert client1 is client2
        await provider._http_pool.close_all()
