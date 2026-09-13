"""V0.33 Cache 后端抽象 + TTL + 持久化 + V0.37 跨进程文件锁 + V0.40 SQLite backend。

设计：
- CacheBackend Protocol：统一 get / set / size / clear / stats 接口
- MemoryLRUBackend：V0.29 真 LRU + V0.33 TTL（OrderedDict + 时间戳检查）
- JSONFileBackend：持久化（重启后 cache 保留）+ TTL + V0.37 文件锁
- V0.37 CacheLock：跨平台文件锁（fcntl on POSIX / msvcrt on Windows）
- V0.40 SQLiteBackend：ACID + WAL 模式 + 跨 POSIX/Windows 安全（SQLite 内置锁）

V0.40 新增 SQLiteBackend（解决 V0.37 跨 OS 锁不互斥限制）：
- SQLite 内置锁机制（POSIX/Windows 通用），无需 fcntl/msvcrt
- WAL 模式：reader 不阻塞 writer
- ACID 事务：INSERT OR REPLACE 原子 upsert
- 进程/线程安全：sqlite3 模块内已处理
- 适合：长期运行 + 多进程 + 跨 OS 共享 cache 文件

Key 类型：原 LLMProvider 用 tuple(model, sys_hash, user_hash, temperature) 作为 key，
JSON 后端需要可序列化 → 把 tuple 转成 ":" 拼接的字符串。
SQLite backend 直接存 TEXT，无需额外编码（用 encode_key 统一接口）。

Stats：
- hits / misses / hit_rate（跨实例累计？仅内存，文件加载时重置）
- size / max_size / enabled
- backend（"memory" | "json" | "sqlite"）
- ttl_seconds（0 = 不过期）
- persist_path（仅 json / sqlite backend）
- lock_backend（V0.37：fcntl / msvcrt / none；V0.40 sqlite: "sqlite"）
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import tempfile
import threading
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

    def keys(self) -> list[str]:
        """V0.43：返回所有 cache keys（按 LRU 顺序：最旧在前）。

        用于 cache 迁移（memory → json / sqlite 等）。
        """
        ...

    def close(self) -> None:
        """V0.42：显式关闭后端（释放资源，如 SQLite 连接池）。

        MemoryLRU / JSONFile 是 no-op，SQLite 会关闭所有池中连接。
        """
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

    def close(self) -> None:
        """V0.42：no-op（MemoryLRU 无资源需释放）。"""

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
            "lock_backend": "none",  # V0.40: memory 无需锁
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

    def keys(self) -> list[str]:
        """V0.43：返回所有 encoded keys（按 LRU 顺序：最旧在前）。"""
        return [entry["key"] for entry in self._entries]

    def close(self) -> None:
        """V0.42：no-op（JSONFile 无连接池）。"""


# === SQLiteBackend：V0.40 新增（解决 V0.37 跨 OS 锁不互斥限制）===


class SQLiteBackend:
    """V0.40 SQLite cache backend — V0.42 升级：连接池 + 自动 backup。

    优势（vs JSONFileBackend）：
    - **跨 OS 安全**：SQLite 内置锁机制，POSIX/Windows 通用（无需 fcntl/msvcrt）
    - **ACID 事务**：INSERT OR REPLACE 原子 upsert
    - **并发读**：WAL 模式让 reader 不阻塞 writer
    - **零新依赖**：sqlite3 是 Python 标准库
    - **可跨 OS 共享 cache 文件**：从 Linux 拷贝到 Windows 直接可用

    劣势：
    - 性能略低于纯内存（但收益 > 复杂度）
    - 单文件最大 ~140TB（远超需求）
    - WAL 模式会产生 -wal / -shm 辅助文件

    Schema：
        CREATE TABLE cache (
            key TEXT PRIMARY KEY,        -- 编码后的 cache key（encode_key 输出）
            value TEXT NOT NULL,          -- 缓存内容
            expires_at REAL,              -- 过期时间戳（NULL = 永不过期）
            last_accessed_at REAL NOT NULL, -- V0.29 LRU 用
            created_at REAL NOT NULL       -- 调试用
        );

    进程/线程安全（V0.42 升级）：
    - **连接池**：每线程独立 connection（threading.local），无需全局锁
    - WAL 模式：reader 不阻塞 writer
    - 跨进程：SQLite 内置文件锁 + 写串行化（自动）
    - **V0.42 自动 backup**：启动时 PRAGMA integrity_check，损坏则重命名为 .corrupt.{ts}
    """

    FILE_VERSION = 2  # V0.40 升级版本（与 JSONFileBackend 不兼容）

    def __init__(
        self,
        path: Path,
        max_size: int = 256,
        ttl_seconds: int = 0,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

        # V0.42：连接池 — 每线程独立 connection（threading.local）
        self._local = threading.local()
        # 维护所有已创建 connection 的引用（用于 close）
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()  # 仅保护 _conns 列表

        # V0.42：启动时检查完整性 + 自动 backup
        self._check_and_recover()

        # 初始化 schema（用主连接 + LRU eviction）
        main_conn = self._get_conn()
        main_conn.execute("PRAGMA journal_mode=WAL")
        main_conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema(main_conn)
        self._cleanup_expired(main_conn)
        self._evict_if_needed(main_conn)
        logger.info(
            "V0.42 SQLiteBackend: %s (max_size=%d, ttl=%d, conn_pool=on)",
            self._path,
            max_size,
            ttl_seconds,
        )

    def _check_and_recover(self) -> None:
        """V0.42：启动时检查 DB 完整性，损坏则 backup + 重启。

        先尝试用 SQLite header magic 判断（避免触发 integrity_check 的"file is not
        a database"异常锁住文件）。如果 magic 不对，直接 backup 重建。
        如果 magic 对但 integrity_check 失败（如部分损坏），也 backup 重建。
        """
        if not self._path.exists():
            return

        # Step 1: 快速 magic 检查（"SQLite format 3" 16 字节头）
        try:
            with open(self._path, "rb") as f:
                header = f.read(16)
            if not header.startswith(b"SQLite format 3"):
                logger.warning(
                    "V0.42 SQLiteBackend: DB 文件 magic 错误（%r），视为损坏",
                    header[:8],
                )
                self._rename_corrupt()
                return
        except OSError as e:
            logger.warning("V0.42 SQLiteBackend: 读取文件失败: %s", e)
            self._rename_corrupt()
            return

        # Step 2: 用 integrity_check 深度检查（确保连接在 finally 中关闭）
        test_conn: sqlite3.Connection | None = None
        try:
            test_conn = sqlite3.connect(str(self._path), timeout=5.0)
            result = test_conn.execute("PRAGMA integrity_check").fetchone()
            if result and result[0] == "ok":
                return
            logger.warning("V0.42 SQLiteBackend: integrity_check 失败: %s", result)
        except Exception as e:
            logger.warning("V0.42 SQLiteBackend: integrity_check 异常: %s（视为损坏）", e)
        finally:
            if test_conn is not None:
                try:
                    test_conn.close()
                except Exception:
                    pass

        # 损坏 → rename
        self._rename_corrupt()

    def _rename_corrupt(self) -> None:
        """V0.42：将损坏的 DB 文件重命名为 .corrupt.{timestamp}.db。"""
        timestamp = int(time.time())
        backup_path = self._path.with_suffix(f".corrupt.{timestamp}.db")
        # Windows 上需要先尝试删除可能残留的 -wal / -shm 文件
        for suffix in ("-wal", "-shm", "-journal"):
            extra = self._path.with_suffix(self._path.suffix + suffix)
            if extra.exists():
                try:
                    extra.unlink()
                except OSError:
                    pass
        try:
            self._path.rename(backup_path)
            logger.warning(
                "V0.42 SQLiteBackend: 损坏 DB 已备份到 %s，新 DB 将重建",
                backup_path,
            )
        except OSError as e:
            logger.error("V0.42 SQLiteBackend: 备份失败（%s），将尝试在损坏 DB 上启动", e)

    def _get_conn(self) -> sqlite3.Connection:
        """V0.42：获取当前线程的 connection（thread-local）。"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self._path),
                isolation_level=None,
                timeout=5.0,
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
            with self._conns_lock:
                self._conns.append(conn)
        return self._local.conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        """初始化 schema（含 last_accessed_at 索引）。"""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL,
                last_accessed_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_last_accessed ON cache(last_accessed_at)")

    def _cleanup_expired(self, conn: sqlite3.Connection) -> None:
        """V0.42：清理过期条目。"""
        if self._ttl_seconds > 0:
            now = time.time()
            deleted = conn.execute(
                "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            ).rowcount
            if deleted > 0:
                logger.info("V0.42 SQLiteBackend: 启动时清理 %d 条过期", deleted)

    def _evict_if_needed(self, conn: sqlite3.Connection) -> None:
        """V0.29 真 LRU。"""
        count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        if count <= self._max_size:
            return
        to_delete = count - self._max_size
        conn.execute(
            """
            DELETE FROM cache WHERE key IN (
                SELECT key FROM cache ORDER BY last_accessed_at ASC LIMIT ?
            )
            """,
            (to_delete,),
        )

    def get(self, key: tuple | str) -> str | None:
        """V0.42：thread-local conn，无全局锁。"""
        encoded = encode_key(key)
        now = time.time()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?",
            (encoded,),
        ).fetchone()
        if row is None:
            self._misses += 1
            return None
        value, expires_at = row
        if expires_at is not None and expires_at < now:
            conn.execute("DELETE FROM cache WHERE key = ?", (encoded,))
            self._misses += 1
            return None
        conn.execute(
            "UPDATE cache SET last_accessed_at = ? WHERE key = ?",
            (now, encoded),
        )
        self._hits += 1
        return value

    def set(self, key: tuple | str, value: str) -> None:
        """V0.42：thread-local conn。"""
        encoded = encode_key(key)
        now = time.time()
        expires_at = now + self._ttl_seconds if self._ttl_seconds > 0 else None
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO cache (key, value, expires_at, last_accessed_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                expires_at=excluded.expires_at,
                last_accessed_at=excluded.last_accessed_at
            """,
            (encoded, value, expires_at, now, now),
        )
        self._evict_if_needed(conn)

    def size(self) -> int:
        """V0.42：用 thread-local conn。"""
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]

    def keys(self) -> list[str]:
        """V0.43：返回所有 encoded keys（按 LRU 顺序：最旧在前）。"""
        conn = self._get_conn()
        rows = conn.execute("SELECT key FROM cache ORDER BY last_accessed_at ASC").fetchall()
        return [r[0] for r in rows]

    def clear(self) -> None:
        """清空 cache + 重置 stats。"""
        conn = self._get_conn()
        conn.execute("DELETE FROM cache")
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "enabled": True,
            "backend": "sqlite",
            "size": self.size(),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "ttl_seconds": self._ttl_seconds,
            "persist_path": str(self._path),
            "lock_backend": "sqlite",
            "conn_pool_size": len(self._conns),  # V0.42: 连接池大小
        }

    def close(self) -> None:
        """V0.42：关闭所有连接池中的 connection。"""
        with self._conns_lock:
            for conn in self._conns:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning("V0.42 SQLiteBackend: 关闭连接错误: %s", e)
            self._conns.clear()
        logger.info("V0.42 SQLiteBackend: 所有连接已关闭")


# === RedisBackend：V0.45 新增（分布式 cache）===


class RedisBackend:
    """V0.45：Redis cache backend — 分布式 / 跨机器 / 跨进程。

    优势（vs SQLite/Memory/JSON）：
    - **分布式**：多机器 / 多容器共享 cache（web 集群 + CLI 跨机器）
    - **生产级**：Redis 内置 LRU / 持久化 / 高可用（sentinel/cluster）
    - **跨进程安全**：Redis 内置单线程命令队列（自动串行化）
    - **内置 TTL**：Redis EXPIRE（无需应用层检查）
    - **原子操作**：SETNX / SETEX / MSET 等

    劣势：
    - 需要 Redis 服务（额外基础设施）
    - 性能比内存 / SQLite 慢（网络 round-trip）
    - 单 Redis 节点容量有限（建议 100K-1M keys）

    Key 格式：
        {namespace}:{encoded_key}        # e.g., "novel2all:model:hash_0:user_hash_0:0.7"

    LRU 策略（由 Redis 配置决定）：
        - maxmemory-policy: allkeys-lru  # 整体 LRU
        - maxmemory-policy: volatile-lru  # 仅 TTL keys

    进程/线程安全（V0.45）：
    - redis-py 客户端自带连接池（ConnectionPool）
    - 单线程 asyncio 兼容：redis.asyncio.Redis
    - 多线程：每个线程自动从池获取连接
    """

    FILE_VERSION = 3  # V0.45 升级版本

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        max_size: int = 256,
        ttl_seconds: int = 0,
        namespace: str = "novel2all",
    ) -> None:
        """V0.45：初始化 Redis backend。

        Args:
            url: Redis 连接 URL（默认 redis://localhost:6379/0）
            max_size: LRU 上限（建议 Redis maxmemory 配置对齐）
            ttl_seconds: TTL（0 = 永不过期，但 Redis 仍可配 maxmemory-policy）
            namespace: key 前缀（避免多应用共享 Redis 时冲突）
        """
        try:
            import redis
        except ImportError as e:
            raise ImportError(
                "V0.45 RedisBackend 需要 redis 包。请运行：pip install 'redis>=5.0.0'"
            ) from e

        self._url = url
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._namespace = namespace
        self._hits = 0
        self._misses = 0

        # 创建连接池（redis-py 自动管理线程安全）
        self._client = redis.Redis.from_url(
            url,
            decode_responses=False,  # 存 bytes（value 是 str.encode()）
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
        # 启动时检查连接
        try:
            self._client.ping()
            logger.info("V0.45 RedisBackend: 连接成功 %s", url)
        except Exception as e:
            logger.error("V0.45 RedisBackend: Redis 连接失败 %s: %s", url, e)
            raise

    def _key(self, key: tuple | str) -> str:
        """V0.45：生成 Redis key（带 namespace 前缀）。"""
        encoded = encode_key(key)
        return f"{self._namespace}:{encoded}"

    def get(self, key: tuple | str) -> str | None:
        """V0.45：获取 cache value（Redis GET）。"""
        try:
            value = self._client.get(self._key(key))
        except Exception as e:
            logger.warning("V0.45 RedisBackend: GET 失败: %s", e)
            self._misses += 1
            return None

        if value is None:
            self._misses += 1
            return None
        # V0.45：返回 bytes → str
        self._hits += 1
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def set(self, key: tuple | str, value: str) -> None:
        """V0.45：设置 cache value（Redis SET + EXPIRE）。"""
        redis_key = self._key(key)
        try:
            if self._ttl_seconds > 0:
                # V0.45：用 set(name, value, ex=ttl) 替代 deprecated setex()
                self._client.set(redis_key, value.encode("utf-8"), ex=self._ttl_seconds)
            else:
                self._client.set(redis_key, value.encode("utf-8"))
        except Exception as e:
            logger.warning("V0.45 RedisBackend: SET 失败: %s", e)

    def size(self) -> int:
        """V0.45：当前 cache 条目数（Redis DBSIZE）。"""
        try:
            return self._client.dbsize()
        except Exception:
            return 0

    def clear(self) -> None:
        """V0.45：清空 cache（仅清本 namespace 的 keys，避免误删其他应用）。"""
        pattern = f"{self._namespace}:*"
        try:
            # SCAN 比 KEYS 更安全（不阻塞 Redis）
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("V0.45 RedisBackend: clear 失败: %s", e)
        self._hits = 0
        self._misses = 0

    def keys(self) -> list[str]:
        """V0.45：返回所有 encoded keys（带 namespace 前缀）。"""
        pattern = f"{self._namespace}:*"
        result: list[str] = []
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                # 去掉 namespace 前缀，返回纯 encoded key
                prefix = f"{self._namespace}:"
                for k in keys:
                    if isinstance(k, bytes):
                        k = k.decode("utf-8")
                    if k.startswith(prefix):
                        result.append(k[len(prefix) :])
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("V0.45 RedisBackend: keys 失败: %s", e)
        return result

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        try:
            redis_info = self._client.info(section="memory")
            used_memory = redis_info.get("used_memory", 0)
        except Exception:
            used_memory = 0
        return {
            "enabled": True,
            "backend": "redis",
            "size": self.size(),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "ttl_seconds": self._ttl_seconds,
            "persist_path": self._url,
            "lock_backend": "redis",  # V0.45: Redis 内置单线程队列
            "namespace": self._namespace,
            "used_memory_bytes": used_memory,
        }

    def close(self) -> None:
        """V0.45：关闭 Redis 连接池。"""
        try:
            self._client.close()
            logger.info("V0.45 RedisBackend: 连接池已关闭")
        except Exception as e:
            logger.warning("V0.45 RedisBackend: 关闭错误: %s", e)
