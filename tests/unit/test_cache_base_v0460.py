"""V0.46：CacheBase 抽象基类单元测试。

测试范围：
1. CacheBase 是 ABC，不能直接实例化
2. 4 backend（MemoryLRU/JSONFile/SQLite/Redis）全部继承 CacheBase
3. 4 backend 的 stats() 字典结构一致（V0.45 兼容）
4. backend_name ClassVar 正确设置
5. _stats_persist_path/_stats_lock_backend/_stats_extras 钩子工作
6. 默认 close() 是 no-op（MemoryLRU/JSONFile 验证）
7. _reset_stats() 替代 4 backend 中重复的 hits/misses 重置
8. CacheBackend Protocol 兼容性（structural subtyping）
9. 新 backend 只需 set backend_name + 覆盖钩子（验证 CacheBase 的扩展性）
"""

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any

import pytest

from novel2all.core.cache import (
    CacheBase,
    JSONFileBackend,
    MemoryLRUBackend,
    RedisBackend,
    SQLiteBackend,
)

# === Test 1：CacheBase 是 ABC ===


def test_cache_base_is_abstract_class() -> None:
    """V0.46：CacheBase 继承 ABC，不能直接实例化。"""
    assert issubclass(CacheBase, ABC)
    # 直接实例化应抛 TypeError（缺 abstract 方法）
    with pytest.raises(TypeError) as exc_info:
        CacheBase()  # type: ignore[abstract]
    assert "abstract" in str(exc_info.value).lower() or "Can't instantiate" in str(exc_info.value)


def test_cache_base_abstract_methods() -> None:
    """V0.46：get/set/size/clear/keys 是 abstract（必须由子类实现）。"""
    abstract_methods = CacheBase.__abstractmethods__
    assert "get" in abstract_methods
    assert "set" in abstract_methods
    assert "size" in abstract_methods
    assert "clear" in abstract_methods
    assert "keys" in abstract_methods


# === Test 2：4 backend 全部继承 CacheBase ===


def test_memory_lru_inherits_cache_base() -> None:
    """V0.46：MemoryLRUBackend 继承 CacheBase。"""
    assert issubclass(MemoryLRUBackend, CacheBase)


def test_json_file_inherits_cache_base() -> None:
    """V0.46：JSONFileBackend 继承 CacheBase。"""
    assert issubclass(JSONFileBackend, CacheBase)


def test_sqlite_inherits_cache_base() -> None:
    """V0.46：SQLiteBackend 继承 CacheBase。"""
    assert issubclass(SQLiteBackend, CacheBase)


def test_redis_inherits_cache_base() -> None:
    """V0.46：RedisBackend 继承 CacheBase。"""
    assert issubclass(RedisBackend, CacheBase)


# === Test 3：backend_name ClassVar 正确设置 ===


def test_memory_lru_backend_name() -> None:
    """V0.46：MemoryLRUBackend.backend_name == 'memory'。"""
    assert MemoryLRUBackend.backend_name == "memory"


def test_json_file_backend_name() -> None:
    """V0.46：JSONFileBackend.backend_name == 'json'。"""
    assert JSONFileBackend.backend_name == "json"


def test_sqlite_backend_name() -> None:
    """V0.46：SQLiteBackend.backend_name == 'sqlite'。"""
    assert SQLiteBackend.backend_name == "sqlite"


def test_redis_backend_name() -> None:
    """V0.46：RedisBackend.backend_name == 'redis'。"""
    assert RedisBackend.backend_name == "redis"


# === Test 4：stats() 字典结构一致（V0.45 兼容）===


def test_memory_lru_stats_structure() -> None:
    """V0.46：MemoryLRUBackend.stats() 返回完整字典（10 字段 + V0.46 不变的字段顺序）。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    cache.get("k1")  # hit
    cache.get("missing")  # miss

    stats = cache.stats()
    # 核心字段（V0.45 兼容）
    assert stats["enabled"] is True
    assert stats["backend"] == "memory"
    assert stats["size"] == 1
    assert stats["max_size"] == 10
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["ttl_seconds"] == 0
    assert stats["persist_path"] is None
    assert stats["lock_backend"] == "none"


def test_json_file_stats_structure(tmp_path: Path) -> None:
    """V0.46：JSONFileBackend.stats() 包含 path + lock_backend。"""
    path = tmp_path / "cache.json"
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    stats = cache.stats()
    assert stats["backend"] == "json"
    assert stats["persist_path"] == str(path)
    assert stats["lock_backend"] in ("fcntl", "msvcrt", "none")


def test_sqlite_stats_structure(tmp_path: Path) -> None:
    """V0.46：SQLiteBackend.stats() 包含 path + lock_backend='sqlite' + conn_pool_size。"""
    path = tmp_path / "cache.db"
    cache = SQLiteBackend(path=path, max_size=10, ttl_seconds=0)
    stats = cache.stats()
    assert stats["backend"] == "sqlite"
    assert stats["persist_path"] == str(path)
    assert stats["lock_backend"] == "sqlite"
    assert "conn_pool_size" in stats  # V0.46 extras
    assert stats["conn_pool_size"] >= 1


def test_redis_stats_structure() -> None:
    """V0.46：RedisBackend.stats() 包含 url + namespace + used_memory_bytes（fakeredis mock）。"""
    fakeredis = pytest.importorskip("fakeredis")
    from unittest.mock import patch

    fake_server = fakeredis.FakeServer()
    with patch("redis.Redis.from_url", return_value=fakeredis.FakeRedis(server=fake_server)):
        cache = RedisBackend(
            url="redis://fake:6379/0", max_size=10, ttl_seconds=0, namespace="test"
        )
    stats = cache.stats()
    assert stats["backend"] == "redis"
    assert stats["persist_path"] == "redis://fake:6379/0"
    assert stats["lock_backend"] == "redis"
    assert stats["namespace"] == "test"  # V0.46 extras
    assert "used_memory_bytes" in stats


# === Test 5：_reset_stats() 工作 ===


def test_reset_stats_clears_hits_misses() -> None:
    """V0.46：_reset_stats() 清零 hits/misses（被 clear() 复用）。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    cache.get("k1")
    cache.get("k2")
    assert cache._hits == 1
    assert cache._misses == 1

    cache._reset_stats()
    assert cache._hits == 0
    assert cache._misses == 0


def test_clear_uses_reset_stats(tmp_path: Path) -> None:
    """V0.46：clear() 后 hits/misses 应为 0（验证 _reset_stats 集成）。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    cache.get("k1")
    cache.clear()
    assert cache._hits == 0
    assert cache._misses == 0
    assert cache.size() == 0

    # JSONFile 也用 _reset_stats
    cache2 = JSONFileBackend(path=tmp_path / "c.json", max_size=10)
    cache2.set("k1", "v1")
    cache2.get("k1")
    cache2.clear()
    assert cache2._hits == 0
    assert cache2._misses == 0


# === Test 6：默认 close() 是 no-op ===


def test_memory_lru_close_is_noop() -> None:
    """V0.46：MemoryLRUBackend.close() 继承 CacheBase 默认 no-op，不抛错。"""
    cache = MemoryLRUBackend(max_size=10)
    cache.set("k1", "v1")
    # close() 应成功执行且无副作用
    cache.close()
    # 数据应仍可访问（close 后内存仍可用）
    assert cache.get("k1") == "v1"


def test_json_file_close_is_noop(tmp_path: Path) -> None:
    """V0.46：JSONFileBackend.close() 继承默认 no-op。"""
    cache = JSONFileBackend(path=tmp_path / "c.json", max_size=10)
    cache.set("k1", "v1")
    cache.close()  # 不抛错
    assert cache.get("k1") == "v1"


def test_cache_base_close_default_is_noop() -> None:
    """V0.46：CacheBase.close() 默认实现是 no-op（子类可覆盖）。"""
    # 通过 MemoryLRUBackend 间接测试（其 close() 不重写）
    cache = MemoryLRUBackend(max_size=10)
    # close 应不抛错且无副作用
    cache.close()


# === Test 7：子类 _stats_extras 钩子覆盖 ===


def test_stats_extras_empty_default() -> None:
    """V0.46：MemoryLRU 不覆盖 _stats_extras，默认返回 {}。"""
    cache = MemoryLRUBackend(max_size=10)
    assert cache._stats_extras() == {}


def test_stats_extras_sqlite_returns_pool_size(tmp_path: Path) -> None:
    """V0.46：SQLite _stats_extras() 返回 conn_pool_size。"""
    cache = SQLiteBackend(path=tmp_path / "c.db", max_size=10)
    extras = cache._stats_extras()
    assert "conn_pool_size" in extras
    assert extras["conn_pool_size"] >= 1


# === Test 8：子类 _stats_persist_path 钩子覆盖 ===


def test_stats_persist_path_memory_default() -> None:
    """V0.46：MemoryLRU 默认 _stats_persist_path() 返回 None。"""
    cache = MemoryLRUBackend(max_size=10)
    assert cache._stats_persist_path() is None


def test_stats_persist_path_json(tmp_path: Path) -> None:
    """V0.46：JSONFile _stats_persist_path() 返回 str(path)。"""
    path = tmp_path / "c.json"
    cache = JSONFileBackend(path=path, max_size=10)
    assert cache._stats_persist_path() == str(path)


def test_stats_persist_path_sqlite(tmp_path: Path) -> None:
    """V0.46：SQLite _stats_persist_path() 返回 str(.db path)。"""
    path = tmp_path / "c.db"
    cache = SQLiteBackend(path=path, max_size=10)
    assert cache._stats_persist_path() == str(path)


def test_stats_persist_path_redis() -> None:
    """V0.46：Redis _stats_persist_path() 返回 url。"""
    fakeredis = pytest.importorskip("fakeredis")
    from unittest.mock import patch

    fake_server = fakeredis.FakeServer()
    with patch("redis.Redis.from_url", return_value=fakeredis.FakeRedis(server=fake_server)):
        cache = RedisBackend(url="redis://test:6379/0")
    assert cache._stats_persist_path() == "redis://test:6379/0"


# === Test 9：子类 _stats_lock_backend 钩子覆盖 ===


def test_stats_lock_backend_memory_default() -> None:
    """V0.46：MemoryLRU 默认 _stats_lock_backend() 返回 'none'。"""
    cache = MemoryLRUBackend(max_size=10)
    assert cache._stats_lock_backend() == "none"


def test_stats_lock_backend_json(tmp_path: Path) -> None:
    """V0.46：JSONFile _stats_lock_backend() 返回探测到的后端。"""
    cache = JSONFileBackend(path=tmp_path / "c.json", max_size=10)
    assert cache._stats_lock_backend() in ("fcntl", "msvcrt", "none")


def test_stats_lock_backend_sqlite(tmp_path: Path) -> None:
    """V0.46：SQLite _stats_lock_backend() 返回 'sqlite'。"""
    cache = SQLiteBackend(path=tmp_path / "c.db", max_size=10)
    assert cache._stats_lock_backend() == "sqlite"


def test_stats_lock_backend_redis() -> None:
    """V0.46：Redis _stats_lock_backend() 返回 'redis'。"""
    fakeredis = pytest.importorskip("fakeredis")
    from unittest.mock import patch

    fake_server = fakeredis.FakeServer()
    with patch("redis.Redis.from_url", return_value=fakeredis.FakeRedis(server=fake_server)):
        cache = RedisBackend(url="redis://test:6379/0")
    assert cache._stats_lock_backend() == "redis"


# === Test 10：stats() 字段顺序保证 V0.45 兼容 ===


def test_stats_field_order_preserved() -> None:
    """V0.46：stats() 返回字典字段顺序与 V0.45 RedisBackend 一致。

    顺序：enabled, backend, size, max_size, hits, misses, hit_rate, ttl_seconds, persist_path, lock_backend
    然后子类 extras 在末尾。
    """
    cache = MemoryLRUBackend(max_size=10)
    keys = list(cache.stats().keys())
    # 前 10 字段必须按此顺序（与 V0.45 RedisBackend.stats() 完全一致）
    expected_prefix = [
        "enabled",
        "backend",
        "size",
        "max_size",
        "hits",
        "misses",
        "hit_rate",
        "ttl_seconds",
        "persist_path",
        "lock_backend",
    ]
    assert keys[: len(expected_prefix)] == expected_prefix


# === Test 11：CacheBase 扩展性验证 ===


def test_subclass_minimal_effort() -> None:
    """V0.46：自定义 CacheBase 子类只需设 backend_name + 实现 abstract 方法 + 可选钩子。"""

    class FakeCache(CacheBase):
        """最小 CacheBase 子类：仅设 backend_name + 实现抽象方法。"""

        backend_name = "fake"

        def __init__(self, max_size: int = 256, ttl_seconds: int = 0) -> None:
            super().__init__(max_size=max_size, ttl_seconds=ttl_seconds)
            self._data: dict[str, str] = {}

        def get(self, key: tuple | str) -> str | None:
            from novel2all.core.cache import encode_key

            encoded = encode_key(key)
            if encoded in self._data:
                self._hits += 1
                return self._data[encoded]
            self._misses += 1
            return None

        def set(self, key: tuple | str, value: str) -> None:
            from novel2all.core.cache import encode_key

            self._data[encode_key(key)] = value

        def size(self) -> int:
            return len(self._data)

        def clear(self) -> None:
            self._data.clear()
            self._reset_stats()

        def keys(self) -> list[str]:
            return list(self._data.keys())

    # 不覆盖任何钩子也能工作（继承默认）
    fake = FakeCache(max_size=100, ttl_seconds=60)
    fake.set("k1", "v1")
    fake.get("k1")  # hit
    fake.get("k2")  # miss

    stats = fake.stats()
    assert stats["backend"] == "fake"  # 来自 backend_name ClassVar
    assert stats["size"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["max_size"] == 100
    assert stats["ttl_seconds"] == 60
    assert stats["persist_path"] is None  # 默认钩子
    assert stats["lock_backend"] == "none"  # 默认钩子
    # 没覆盖 _stats_extras，stats 字典应只有 10 字段
    assert len(stats) == 10


# === Test 12：subclass override _stats_extras works ===


def test_subclass_with_extras() -> None:
    """V0.46：子类覆盖 _stats_extras() 即可添加自定义 stats 字段。"""

    class CustomCache(CacheBase):
        backend_name = "custom"

        def __init__(self) -> None:
            super().__init__()
            self._data: dict[str, str] = {}

        def get(self, key: tuple | str) -> str | None:
            from novel2all.core.cache import encode_key

            encoded = encode_key(key)
            if encoded in self._data:
                self._hits += 1
                return self._data[encoded]
            self._misses += 1
            return None

        def set(self, key: tuple | str, value: str) -> None:
            from novel2all.core.cache import encode_key

            self._data[encode_key(key)] = value

        def size(self) -> int:
            return len(self._data)

        def clear(self) -> None:
            self._data.clear()
            self._reset_stats()

        def keys(self) -> list[str]:
            return list(self._data.keys())

        def _stats_extras(self) -> dict[str, Any]:
            return {"custom_field": "custom_value", "count": 42}

    cache = CustomCache()
    stats = cache.stats()
    # 10 基础字段 + 2 extras = 12
    assert len(stats) == 12
    assert stats["custom_field"] == "custom_value"
    assert stats["count"] == 42


# === Test 13：基类实现仍可单独调用（template method pattern）===


def test_stats_calls_size_each_time() -> None:
    """V0.46：stats() 每次调用都调 size()（动态反映当前状态）。"""
    cache = MemoryLRUBackend(max_size=10)
    cache.set("k1", "v1")
    s1 = cache.stats()
    cache.set("k2", "v2")
    s2 = cache.stats()
    assert s1["size"] == 1
    assert s2["size"] == 2


def test_clear_actually_calls_reset() -> None:
    """V0.46：clear() 通过 _reset_stats() 重置，验证抽象调用。"""
    cache = MemoryLRUBackend(max_size=10)
    cache.set("k1", "v1")
    cache.get("k1")  # hit
    cache.get("k2")  # miss
    assert cache._hits == 1
    assert cache._misses == 1

    cache.clear()
    # _reset_stats() 被调用，hits/misses 应为 0
    assert cache._hits == 0
    assert cache._misses == 0
    # data 也应被清空
    assert cache.size() == 0


# === Test 14：与 CacheBackend Protocol 兼容（structural subtyping）===


def test_backends_satisfy_cache_backend_protocol() -> None:
    """V0.46：4 backend 仍满足 CacheBackend Protocol（向后兼容）。"""
    backends: list[type[CacheBase]] = [
        MemoryLRUBackend,
        JSONFileBackend,
        SQLiteBackend,
        RedisBackend,
    ]
    for cls in backends:
        # 拥有所有 Protocol 要求的 duck-typed 方法
        for method in ("get", "set", "size", "clear", "stats", "keys", "close"):
            assert hasattr(cls, method), f"{cls.__name__} 缺少 {method} 方法"


# === Test 15：基类公共字段正确初始化 ===


def test_base_init_sets_common_fields() -> None:
    """V0.46：CacheBase.__init__ 初始化 _max_size/_ttl_seconds/_hits/_misses。"""
    cache = MemoryLRUBackend(max_size=100, ttl_seconds=60)
    # 这些字段由基类初始化，子类 __init__ 第一行 super().__init__() 设置
    assert cache._max_size == 100
    assert cache._ttl_seconds == 60
    assert cache._hits == 0
    assert cache._misses == 0


def test_json_init_sets_common_fields(tmp_path: Path) -> None:
    """V0.46：JSONFileBackend.__init__ 也通过 super() 设置公共字段。"""
    cache = JSONFileBackend(path=tmp_path / "c.json", max_size=200, ttl_seconds=120)
    assert cache._max_size == 200
    assert cache._ttl_seconds == 120
    assert cache._hits == 0
    assert cache._misses == 0


def test_sqlite_init_sets_common_fields(tmp_path: Path) -> None:
    """V0.46：SQLiteBackend.__init__ 通过 super() 设置公共字段。"""
    cache = SQLiteBackend(path=tmp_path / "c.db", max_size=300, ttl_seconds=180)
    assert cache._max_size == 300
    assert cache._ttl_seconds == 180
    assert cache._hits == 0
    assert cache._misses == 0


def test_redis_init_sets_common_fields() -> None:
    """V0.46：RedisBackend.__init__ 通过 super() 设置公共字段。"""
    fakeredis = pytest.importorskip("fakeredis")
    from unittest.mock import patch

    fake_server = fakeredis.FakeServer()
    with patch("redis.Redis.from_url", return_value=fakeredis.FakeRedis(server=fake_server)):
        cache = RedisBackend(url="redis://fake:6379/0", max_size=400, ttl_seconds=240)
    assert cache._max_size == 400
    assert cache._ttl_seconds == 240
    assert cache._hits == 0
    assert cache._misses == 0
