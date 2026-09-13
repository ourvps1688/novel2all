"""V0.33 Cache TTL + 持久化测试。

覆盖：
1. MemoryLRUBackend 基本 get/set（与 V0.29 行为一致）
2. MemoryLRUBackend TTL 过期（time.time() 检查）
3. MemoryLRUBackend TTL=0 = 永不过期
4. JSONFileBackend 写入 + 重启加载（持久化）
5. JSONFileBackend TTL 过期 + 启动时过滤
6. JSONFileBackend 原子写入（temp + rename）
7. LLMConfig 新字段（cache_backend / cache_ttl_seconds / cache_persist_path）
8. LLMProvider 默认 memory backend
9. LLMProvider json backend 加载已有 cache 文件
10. cache_stats() 新字段（backend / ttl_seconds / persist_path）
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.cache import (
    JSONFileBackend,
    MemoryLRUBackend,
    encode_key,
)

# === MemoryLRUBackend 测试 ===


def test_memory_backend_basic_get_set() -> None:
    """V0.33：MemoryLRUBackend 基本 get/set（与 V0.29 行为一致）。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    assert cache.get("nonexistent") is None


def test_memory_backend_lru_eviction() -> None:
    """V0.33：超 max_size 时 LRU 淘汰最旧。"""
    cache = MemoryLRUBackend(max_size=2, ttl_seconds=0)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")  # 应淘汰 a
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"


def test_memory_backend_lru_update_on_get() -> None:
    """V0.33：get 时更新 LRU 位置（最近使用）。"""
    cache = MemoryLRUBackend(max_size=2, ttl_seconds=0)
    cache.set("a", "1")
    cache.set("b", "2")
    # 访问 a → 移到末尾
    assert cache.get("a") == "1"
    # 添加 c → 淘汰 b（a 最近使用）
    cache.set("c", "3")
    assert cache.get("b") is None
    assert cache.get("a") == "1"
    assert cache.get("c") == "3"


def test_memory_backend_ttl_expiry() -> None:
    """V0.33：TTL 过期 → get 返回 None + 删除 entry。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=1)  # 1 秒 TTL
    cache.set("k", "v")
    assert cache.get("k") == "v"
    # 等待过期
    time.sleep(1.2)
    assert cache.get("k") is None


def test_memory_backend_ttl_zero_means_no_expiry() -> None:
    """V0.33：ttl_seconds=0 = 永不过期。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set("k", "v")
    time.sleep(0.2)
    assert cache.get("k") == "v"


def test_memory_backend_stats() -> None:
    """V0.33：MemoryLRUBackend.stats() 返回所有 V0.33 字段。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=60)
    cache.set("k", "v")
    cache.get("k")
    cache.get("nonexistent")
    stats = cache.stats()
    assert stats["backend"] == "memory"
    assert stats["ttl_seconds"] == 60
    assert stats["persist_path"] is None
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1
    assert stats["max_size"] == 10


def test_memory_backend_clear() -> None:
    """V0.33：clear() 重置 hits/misses + 清空 entries。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set("k", "v")
    cache.get("k")
    assert cache.stats()["hits"] == 1
    cache.clear()
    stats = cache.stats()
    assert stats["hits"] == 0
    assert stats["size"] == 0


def test_memory_backend_accepts_tuple_key() -> None:
    """V0.33：MemoryLRUBackend 接受 tuple key（与 V0.29 dict-key 兼容）。"""
    cache = MemoryLRUBackend(max_size=10, ttl_seconds=0)
    cache.set(("model", "sys_hash", "user_hash", 0.7), "v")
    assert cache.get(("model", "sys_hash", "user_hash", 0.7)) == "v"


# === JSONFileBackend 测试 ===


def test_json_backend_save_and_load(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 写入 + 新实例加载（持久化）。"""
    path = tmp_path / "cache.json"

    # 第一个实例：写入
    cache1 = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    cache1.set("k1", "v1")
    cache1.set("k2", "v2")
    assert path.exists()

    # 第二个实例：从同一文件加载
    cache2 = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache2.get("k1") == "v1"
    assert cache2.get("k2") == "v2"
    # 大小继承（不是新空 backend）
    assert cache2.size() == 2


def test_json_backend_ttl_expiry_on_load(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 启动时过滤 TTL 过期 entry。"""
    path = tmp_path / "cache.json"

    # 写入带 TTL=1 秒的 cache
    cache1 = JSONFileBackend(path=path, max_size=10, ttl_seconds=1)
    cache1.set("k1", "v1")
    time.sleep(1.2)  # 等过期

    # 新实例加载 → k1 已被过滤
    cache2 = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache2.get("k1") is None
    assert cache2.size() == 0


def test_json_backend_ttl_expiry_at_runtime(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend get 时检查 TTL，过期返回 None。"""
    path = tmp_path / "cache.json"
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=1)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    time.sleep(1.2)
    assert cache.get("k") is None


def test_json_backend_atomic_write(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 写入用临时文件 + rename（原子操作）。"""
    path = tmp_path / "cache.json"
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    cache.set("k", "v")

    # 验证：写入后无 .tmp 残留
    tmp_files = list(path.parent.glob(".cache.json.*.tmp"))
    assert len(tmp_files) == 0, f"应无临时文件残留: {tmp_files}"

    # 验证：文件是合法 JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["entries"]) == 1


def test_json_backend_lru_eviction_on_max_size(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 超 max_size 时淘汰最旧（按 last_accessed_at 排序）。"""
    path = tmp_path / "cache.json"
    cache = JSONFileBackend(path=path, max_size=2, ttl_seconds=0)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")  # 淘汰 a
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"


def test_json_backend_clear_persists(tmp_path: Path) -> None:
    """V0.33：clear() 写空 entries 到文件（持久化）。"""
    path = tmp_path / "cache.json"
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    assert path.exists()

    cache.clear()
    # 重新加载验证已清空
    cache2 = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache2.size() == 0


def test_json_backend_stats(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend.stats() 返回所有字段。"""
    path = tmp_path / "cache.json"
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=120)
    cache.set("k", "v")
    cache.get("k")
    stats = cache.stats()
    assert stats["backend"] == "json"
    assert stats["ttl_seconds"] == 120
    assert stats["persist_path"] == str(path)
    assert stats["hits"] == 1


def test_json_backend_handles_corrupt_file(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 加载损坏文件时跳过（不抛错）。"""
    path = tmp_path / "cache.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    # 损坏文件 → 空 cache
    assert cache.size() == 0


def test_json_backend_handles_version_mismatch(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 版本不匹配时跳过加载。"""
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps({"version": 99, "entries": []}),
        encoding="utf-8",
    )
    cache = JSONFileBackend(path=path, max_size=10, ttl_seconds=0)
    assert cache.size() == 0


# === LLMConfig 新字段测试 ===


def test_llmconfig_has_v033_cache_fields() -> None:
    """V0.33：LLMConfig 加 cache_backend / cache_ttl_seconds / cache_persist_path。"""
    config = LLMConfig()
    assert hasattr(config, "cache_backend")
    assert config.cache_backend == "memory"
    assert hasattr(config, "cache_ttl_seconds")
    assert config.cache_ttl_seconds == 0
    assert hasattr(config, "cache_persist_path")
    assert config.cache_persist_path is None


def test_llmconfig_default_values_backward_compatible() -> None:
    """V0.33：默认配置与 V0.29 行为一致（memory backend + 无 TTL）。"""
    config = LLMConfig()
    assert config.cache_enabled is False
    assert config.cache_max_size == 256
    assert config.cache_backend == "memory"
    assert config.cache_ttl_seconds == 0


# === LLMProvider 集成测试 ===


def test_llmprovider_uses_memory_backend_by_default() -> None:
    """V0.33：LLMProvider 默认用 MemoryLRUBackend。"""
    config = LLMConfig(cache_enabled=True)
    provider = LLMProvider(config)
    assert isinstance(provider._cache, MemoryLRUBackend)
    stats = provider.cache_stats()
    assert stats["backend"] == "memory"


def test_llmprovider_uses_json_backend_when_configured(tmp_path: Path) -> None:
    """V0.33：LLMConfig.cache_backend='json' → LLMProvider 用 JSONFileBackend。"""
    persist_path = tmp_path / "novel2all_cache.json"
    config = LLMConfig(
        cache_enabled=True,
        cache_backend="json",
        cache_persist_path=str(persist_path),
    )
    provider = LLMProvider(config)
    assert isinstance(provider._cache, JSONFileBackend)
    stats = provider.cache_stats()
    assert stats["backend"] == "json"
    assert stats["persist_path"] == str(persist_path)


def test_llmprovider_json_backend_loads_existing_cache(tmp_path: Path) -> None:
    """V0.33：JSONFileBackend 启动时从文件加载已有 cache。"""
    persist_path = tmp_path / "novel2all_cache.json"

    # 第一个 provider：写入
    config1 = LLMConfig(
        cache_enabled=True,
        cache_backend="json",
        cache_persist_path=str(persist_path),
    )
    provider1 = LLMProvider(config1)
    provider1._cache.set(("model", "sys", "user", 0.7), "test_value")

    # 第二个 provider：从同一文件加载
    config2 = LLMConfig(
        cache_enabled=True,
        cache_backend="json",
        cache_persist_path=str(persist_path),
    )
    provider2 = LLMProvider(config2)
    assert provider2._cache.get(("model", "sys", "user", 0.7)) == "test_value"


def test_llmprovider_cache_stats_returns_v033_fields() -> None:
    """V0.33：cache_stats() 新增 backend / ttl_seconds / persist_path 字段。"""
    config = LLMConfig(cache_enabled=True, cache_ttl_seconds=3600)
    provider = LLMProvider(config)
    stats = provider.cache_stats()
    assert "backend" in stats
    assert "ttl_seconds" in stats
    assert "persist_path" in stats
    assert stats["backend"] == "memory"
    assert stats["ttl_seconds"] == 3600
    assert stats["enabled"] is True


def test_llmprovider_cache_clear_works_with_json_backend(tmp_path: Path) -> None:
    """V0.33：cache_clear() 在 JSONFileBackend 上也工作（清空 + 写空文件）。"""
    persist_path = tmp_path / "novel2all_cache.json"
    config = LLMConfig(
        cache_enabled=True,
        cache_backend="json",
        cache_persist_path=str(persist_path),
    )
    provider = LLMProvider(config)
    provider._cache.set(("k",), "v")
    assert provider._cache.size() == 1

    provider.cache_clear()
    assert provider._cache.size() == 0
    # 文件被清空（重启加载也是空）
    provider2 = LLMProvider(config)
    assert provider2._cache.size() == 0


# === encode_key 测试 ===


def test_encode_key_with_tuple() -> None:
    """V0.33：encode_key 把 tuple 编码为字符串（JSON 持久化需要）。"""
    key = ("model", "sys_hash_123", "user_hash_456", 0.7)
    encoded = encode_key(key)
    assert isinstance(encoded, str)
    assert ":" in encoded


def test_encode_key_with_string() -> None:
    """V0.33：encode_key 字符串原样返回。"""
    assert encode_key("plain_key") == "plain_key"
