"""V0.33 Cache 后端抽象 + TTL + 持久化。

设计：
- CacheBackend Protocol：统一 get / set / size / clear / stats 接口
- MemoryLRUBackend：V0.29 真 LRU + V0.33 TTL（OrderedDict + 时间戳检查）
- JSONFileBackend：持久化（重启后 cache 保留）+ TTL

Key 类型：原 LLMProvider 用 tuple(model, sys_hash, user_hash, temperature) 作为 key，
JSON 后端需要可序列化 → 把 tuple 转成 ":" 拼接的字符串。

Stats：
- hits / misses / hit_rate（跨实例累计？仅内存，文件加载时重置）
- size / max_size / enabled
- backend（"memory" | "json"）
- ttl_seconds（0 = 不过期）
- persist_path（仅 json backend）

V0.33 持久化策略（简单优先）：
- 每次 set → 写入 JSON 文件（用临时文件 + atomic rename 防止损坏）
- 启动时 → 加载 JSON 文件，检查 TTL 过期
- 不实现文件锁（单进程假设；多进程会有 race condition，但 V0.33 接受）
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Cache key 的 tuple → str / str → tuple 转换
# 内部用 ":" 拼接（key 各部分不含 ":"；sha256 hexdigest 只含 0-9a-f，无冲突）
_KEY_SEP = ":"


def encode_key(key: tuple | str) -> str:
    """将 tuple key 编码为字符串（用于 JSON 持久化）。"""
    if isinstance(key, str):
        return key
    return _KEY_SEP.join(str(p) for p in key)


def decode_key(encoded: str) -> str:
    """从 JSON 加载的字符串 key 解码（这里我们保持为 str，调用方负责解析）。"""
    return encoded


class CacheBackend(Protocol):
    """Cache 后端接口（V0.33）。"""

    def get(self, key: tuple | str) -> str | None:
        """获取缓存值（V0.33：检查 TTL，过期返回 None）。"""
        ...

    def set(self, key: tuple | str, value: str) -> None:
        """设置缓存值（V0.33：记录 expires_at；超 max_size 时 LRU 淘汰）。"""
        ...

    def size(self) -> int:
        """当前缓存条目数。"""
        ...

    def clear(self) -> None:
        """清空缓存（重置 hits/misses 计数）。"""
        ...

    def stats(self) -> dict[str, Any]:
        """返回统计信息（用于 /api/cache/stats 面板）。"""
        ...


# === MemoryLRUBackend：进程内 LRU + TTL（V0.33 升级 V0.29）===


class MemoryLRUBackend:
    """V0.29 真 LRU + V0.33 TTL。

    LRU：OrderedDict，get 时 move_to_end 更新最近使用位置；
        set 时如超 max_size 调 popitem(last=False) 淘汰最旧条目。

    TTL：每个 entry 记 expires_at（time.time() + ttl_seconds）；
        0 = 永不过期。get 时检查，过期则删除 + 返回 None。
    """

    def __init__(self, max_size: int = 256, ttl_seconds: int = 0) -> None:
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._expires_at: dict[str, float | None] = {}  # key -> expires_at (None = 永不过期)
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: tuple | str) -> str | None:
        encoded = encode_key(key)
        # V0.33：检查 TTL
        expires_at = self._expires_at.get(encoded)
        if expires_at is not None and expires_at < time.time():
            # 过期 → 删除 + 返回 None
            self._cache.pop(encoded, None)
            self._expires_at.pop(encoded, None)
            self._misses += 1
            return None
        if encoded not in self._cache:
            self._misses += 1
            return None
        # 命中 → move_to_end 更新 LRU
        self._cache.move_to_end(encoded)
        self._hits += 1
        return self._cache[encoded]

    def set(self, key: tuple | str, value: str) -> None:
        encoded = encode_key(key)
        if encoded in self._cache:
            self._cache[encoded] = value
            self._cache.move_to_end(encoded)
        else:
            if len(self._cache) >= self._max_size:
                # 真 LRU：淘汰最旧
                old_key, _ = self._cache.popitem(last=False)
                self._expires_at.pop(old_key, None)
            self._cache[encoded] = value
        # V0.33：记录 expires_at
        if self._ttl_seconds > 0:
            self._expires_at[encoded] = time.time() + self._ttl_seconds
        else:
            self._expires_at[encoded] = None  # 永不过期

    def size(self) -> int:
        return len(self._cache)

    def keys(self) -> list[str]:
        """返回所有 cache keys（按 LRU 顺序：最旧在前）。"""
        return list(self._cache.keys())

    def values(self) -> list[str]:
        """返回所有 cache values（按 LRU 顺序：最旧在前）。"""
        return list(self._cache.values())

    def clear(self) -> None:
        self._cache.clear()
        self._expires_at.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "enabled": True,
            "backend": "memory",
            "size": self.size(),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "ttl_seconds": self._ttl_seconds,
            "persist_path": None,
        }


# === JSONFileBackend：持久化 LRU + TTL（V0.33）===


class JSONFileBackend:
    """V0.33 持久化 cache 后端（JSON 文件 + LRU + TTL）。

    行为：
    - 启动时从 JSON 文件加载（过滤掉 TTL 过期的）
    - 每次 set 写回文件（用临时文件 + atomic rename 防止损坏）
    - 文件格式：
      {
        "version": 1,
        "entries": [
          {"key": "...", "value": "...", "expires_at": 1234567890.0 or null, "last_accessed_at": ...},
          ...
        ]
      }

    注意：
    - 多进程并发写同一文件有 race condition（V0.33 接受；V0.34+ 加文件锁）
    - 不实现 LRU 写入顺序（按 expires_at + last_accessed_at 计算"最旧"）
    """

    FILE_VERSION = 1

    def __init__(self, path: Path, max_size: int = 256, ttl_seconds: int = 0) -> None:
        self._path = Path(path)
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        # 内存中的 entry 列表（按 last_accessed_at 排序）
        self._entries: list[dict[str, Any]] = []
        self._key_index: dict[str, int] = {}  # key -> index in _entries
        self._hits = 0
        self._misses = 0
        # 启动时加载
        self._load()

    def _load(self) -> None:
        """启动时从文件加载 entries（过滤 TTL 过期）。"""
        if not self._path.exists():
            logger.info("V0.33 JSONFileBackend: %s 不存在，跳过加载", self._path)
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("V0.33 JSONFileBackend: 加载失败 %s: %s", self._path, e)
            return
        version = data.get("version", 1)
        if version != self.FILE_VERSION:
            logger.warning(
                "V0.33 JSONFileBackend: 版本不匹配 (file=%d, expected=%d), 跳过",
                version,
                self.FILE_VERSION,
            )
            return
        now = time.time()
        valid_entries = []
        for entry in data.get("entries", []):
            expires_at = entry.get("expires_at")
            if expires_at is not None and expires_at < now:
                continue  # 跳过过期
            valid_entries.append(entry)
        # 按 last_accessed_at 升序（最旧在前，方便 LRU 淘汰）
        valid_entries.sort(key=lambda e: e.get("last_accessed_at", 0))
        # 截断到 max_size（保留最近使用的）
        if len(valid_entries) > self._max_size:
            valid_entries = valid_entries[-self._max_size :]
        self._entries = valid_entries
        self._rebuild_index()
        logger.info(
            "V0.33 JSONFileBackend: 从 %s 加载 %d 条（可能过滤了过期）",
            self._path,
            len(self._entries),
        )

    def _rebuild_index(self) -> None:
        """重建 key → index 映射。"""
        self._key_index = {entry["key"]: i for i, entry in enumerate(self._entries)}

    def _save(self) -> None:
        """写回文件（用临时文件 + atomic rename 防止损坏）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 写入临时文件 → rename
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                json.dump(
                    {"version": self.FILE_VERSION, "entries": self._entries},
                    tmp,
                    ensure_ascii=False,
                    indent=None,  # 紧凑（不浪费空间）
                )
                tmp_path = tmp.name
            # atomic rename（Windows 上可能不支持，但通常能用）
            Path(tmp_path).replace(self._path)
        except OSError as e:
            logger.error("V0.33 JSONFileBackend: 写入失败 %s: %s", self._path, e)

    def get(self, key: tuple | str) -> str | None:
        encoded = encode_key(key)
        idx = self._key_index.get(encoded)
        if idx is None:
            self._misses += 1
            return None
        entry = self._entries[idx]
        # V0.33：检查 TTL
        expires_at = entry.get("expires_at")
        if expires_at is not None and expires_at < time.time():
            # 过期 → 删除
            del self._entries[idx]
            del self._key_index[encoded]
            self._rebuild_index()
            self._save()
            self._misses += 1
            return None
        # 命中 → 更新 last_accessed_at
        entry["last_accessed_at"] = time.time()
        self._hits += 1
        # 移动到列表末尾（最近使用）
        self._entries.append(self._entries.pop(idx))
        self._rebuild_index()
        return entry["value"]

    def set(self, key: tuple | str, value: str) -> None:
        encoded = encode_key(key)
        now = time.time()
        expires_at = now + self._ttl_seconds if self._ttl_seconds > 0 else None
        idx = self._key_index.get(encoded)
        if idx is not None:
            # 已存在 → 更新
            entry = self._entries[idx]
            entry["value"] = value
            entry["expires_at"] = expires_at
            entry["last_accessed_at"] = now
            # 移到列表末尾
            self._entries.append(self._entries.pop(idx))
        else:
            # 新条目
            if len(self._entries) >= self._max_size:
                # 真 LRU：淘汰最旧（列表头部）
                old = self._entries.pop(0)
                self._key_index.pop(old["key"], None)
            new_entry = {
                "key": encoded,
                "value": value,
                "expires_at": expires_at,
                "last_accessed_at": now,
            }
            self._entries.append(new_entry)
        self._rebuild_index()
        self._save()

    def size(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._key_index.clear()
        self._hits = 0
        self._misses = 0
        self._save()  # 写空 entries

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "enabled": True,
            "backend": "json",
            "size": self.size(),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "ttl_seconds": self._ttl_seconds,
            "persist_path": str(self._path),
        }
