"""V0.33 Cache 后端抽象 + TTL + 持久化 + V0.37 跨进程文件锁。

设计：
- CacheBackend Protocol：统一 get / set / size / clear / stats 接口
- MemoryLRUBackend：V0.29 真 LRU + V0.33 TTL（OrderedDict + 时间戳检查）
- JSONFileBackend：持久化（重启后 cache 保留）+ TTL + V0.37 文件锁
- V0.37 CacheLock：跨平台文件锁（fcntl on POSIX / msvcrt on Windows）

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
- V0.37：set 时加 CacheLock（跨进程互斥），避免两个进程同时写损坏文件
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Protocol, Self

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


# === V0.37 CacheLock：跨平台文件锁 ===
# 解决多进程并发写 JSONFileBackend 时的 race condition
# - POSIX (Linux/macOS): fcntl.flock() 自动释放 + 跨进程互斥
# - Windows: msvcrt.locking() 显式锁定 1 字节
# - 不可用时：降级为无锁模式 + warning（单进程仍安全）


class CacheLock:
    """V0.37：跨进程文件锁（用于 JSONFileBackend 写入互斥）。

    用法：
        with CacheLock(path):
            # 读 / 修改 / 写 cache 文件（原子操作）

    设计：
    - 锁文件 = path + ".lock"（与 cache 文件同目录）
    - 锁内容 = 1 字节（POSIX flock 不需要内容，Windows msvcrt 需要）
    - 自动清理：__exit__ 时 close fd + 尝试删除 lock 文件
    - 降级：如果 fcntl/msvcrt 都不可用，warning + 无锁（单进程安全）

    注意：
    - 不同 OS 的锁**不互斥**（POSIX 锁 vs Windows 锁）。多 OS 共享 cache 文件不安全。
    - 同 OS 多进程：✅ 互斥（fcntl.flock 自动跨进程）
    """

    def __init__(self, target_path: Path) -> None:
        self.target_path = Path(target_path)
        self.lock_path = self.target_path.with_suffix(self.target_path.suffix + ".lock")
        self._fd: Any = None
        self._backend: str = "none"  # V0.37：默认无锁（探测失败时）
        # 探测可用后端
        if sys.platform == "win32":
            try:
                import msvcrt  # noqa: F401

                self._backend = "msvcrt"
            except ImportError:
                pass
        else:
            try:
                import fcntl  # noqa: F401

                self._backend = "fcntl"
            except ImportError:
                pass
        if self._backend == "none":
            logger.warning(
                "V0.37 CacheLock: 平台 %s 无 fcntl/msvcrt 模块，降级为无锁模式（多进程不安全）",
                sys.platform,
            )

    @property
    def backend(self) -> str:
        """返回实际使用的锁后端（fcntl / msvcrt / none）。"""
        return self._backend

    def __enter__(self) -> Self:
        """获取排他锁。失败时抛 BlockingIOError。"""
        if self._backend == "none":
            return self
        # V0.37：使用 append 模式 + 二进制 + os.open() 避免 Windows 权限问题
        # "w" 模式会 truncate，可能在另一进程持有文件时失败
        if self._backend == "msvcrt":
            # Windows: 用 os.open() 显式 O_CREAT | O_RDWR + 共享读（让其他进程能读但 lock 互斥）
            self._fd = os.fdopen(
                os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_RDWR | os.O_BINARY,
                    0o644,
                ),
                "rb+",
            )
            # 确保文件至少 1 字节（msvcrt.locking 需要）
            try:
                self._fd.seek(0, 2)  # 移到末尾
                if self._fd.tell() == 0:
                    self._fd.write(b"\x00")
                    self._fd.flush()
                self._fd.seek(0)
            except OSError:
                pass
        else:
            # POSIX: 文本模式 + "w" 模式（fcntl 不在意文件内容）
            self._fd = open(self.lock_path, "w", encoding="utf-8")
            self._fd.write("0")
            self._fd.flush()
        try:
            if self._backend == "fcntl":
                import fcntl

                fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif self._backend == "msvcrt":
                import msvcrt

                msvcrt.locking(self._fd.fileno(), msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, OSError, PermissionError) as e:
            try:
                self._fd.close()
            except OSError:
                pass
            self._fd = None
            # V0.37：转 PermissionError 为 BlockingIOError（统一异常类型）
            if isinstance(e, PermissionError):
                raise BlockingIOError(str(e)) from e
            raise
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """释放锁 + 清理 lock 文件。"""
        if self._fd is not None:
            try:
                if self._backend == "fcntl":
                    import fcntl

                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                elif self._backend == "msvcrt":
                    import msvcrt

                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as e:
                logger.warning("V0.37 CacheLock: 释放锁失败: %s", e)
            finally:
                self._fd.close()
                self._fd = None
        # 尝试删除 lock 文件（best effort）
        try:
            self.lock_path.unlink()
        except OSError:
            pass


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
    - V0.37：_save() 用 CacheLock 跨进程互斥（解决 race condition）
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
        # V0.37：探测可用的文件锁后端
        self._lock_backend = CacheLock(self._path).backend
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
        """V0.37：写回文件（用临时文件 + atomic rename + CacheLock 跨进程互斥）。

        多进程并发写：两个进程同时 set() 会导致文件损坏（最后一个写入胜出，丢失另一个的修改）。
        V0.37 加 CacheLock（fcntl on POSIX / msvcrt on Windows）确保原子性。
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # V0.37：用 CacheLock 跨进程互斥
        with CacheLock(self._path):
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
                logger.error("V0.37 JSONFileBackend: 写入失败 %s: %s", self._path, e)

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
            # 过期 → 删除（V0.37：加锁避免并发写）
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
            "lock_backend": self._lock_backend,  # V0.37: fcntl | msvcrt | none
        }
