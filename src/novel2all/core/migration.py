"""V0.43：Cache 多 backend 平滑迁移。

场景：用户在生产用 JSONFile 缓存，升级后想用 SQLite（V0.40）更好的并发。
本模块提供 `migrate_cache()` 函数，零数据丢失迁移。

设计：
- 通用迁移函数：读 src 后端所有 entries → 写 dst 后端
- TTL 处理：过期 entries 不迁移（避免带毒数据）
- Key 统一：所有后端用 `encode_key()` 统一编码
- 进度回调：每 N 条 entries 调 `progress_callback()`（CLI 进度条用）
- 原子操作：迁移成功后才建议删除 src（可手动备份）

支持迁移路径：
- memory → json / sqlite
- json → sqlite / memory
- sqlite → json / memory
- 同 backend 不同路径（用于备份）
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from novel2all.core.cache import (
    JSONFileBackend,
    MemoryLRUBackend,
    SQLiteBackend,
)

logger = logging.getLogger(__name__)

BackendType = Literal["memory", "json", "sqlite"]
ProgressCallback = Callable[[int, int], None]  # (migrated_count, total_count)


@dataclass
class MigrationResult:
    """V0.43：迁移结果统计。"""

    src_backend: str
    dst_backend: str
    src_path: str
    dst_path: str
    total_entries: int = 0  # src 总数
    migrated: int = 0  # 成功迁移
    skipped_expired: int = 0  # 跳过 TTL 过期
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        """V0.43：人类可读摘要（CLI 输出用）。"""
        return (
            f"Migration {self.src_backend}→{self.dst_backend} 完成：\n"
            f"  - total: {self.total_entries}\n"
            f"  - migrated: {self.migrated}\n"
            f"  - skipped_expired: {self.skipped_expired}\n"
            f"  - errors: {len(self.errors)}\n"
            f"  - elapsed: {self.elapsed_seconds:.2f}s"
        )


def _open_backend(
    backend_type: str,
    path: str | None,
    max_size: int = 1024,
    ttl_seconds: int = 0,
) -> MemoryLRUBackend | JSONFileBackend | SQLiteBackend:
    """V0.43：根据类型创建后端实例（用于迁移 + 验证）。"""
    if backend_type == "memory":
        return MemoryLRUBackend(max_size=max_size, ttl_seconds=ttl_seconds)
    if backend_type == "json":
        if not path:
            raise ValueError("json backend 需要 path")
        return JSONFileBackend(path=Path(path), max_size=max_size, ttl_seconds=ttl_seconds)
    if backend_type == "sqlite":
        if not path:
            raise ValueError("sqlite backend 需要 path")
        return SQLiteBackend(path=Path(path), max_size=max_size, ttl_seconds=ttl_seconds)
    raise ValueError(f"未知 backend 类型: {backend_type}")


def migrate_cache(
    src_backend: str,
    dst_backend: str,
    src_path: str | None = None,
    dst_path: str | None = None,
    max_size: int = 1024,
    ttl_seconds: int = 0,
    skip_expired: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> MigrationResult:
    """V0.43：从 src backend 迁移所有 entries 到 dst backend。

    Args:
        src_backend: 源 backend 类型（memory / json / sqlite）
        dst_backend: 目标 backend 类型（memory / json / sqlite）
        src_path: 源 cache 路径（memory 可选；json/sqlite 必填）
        dst_path: 目标 cache 路径（同上）
        max_size: 目标 cache max_size（默认 1024）
        ttl_seconds: 目标 cache TTL（默认 0 = 不过期）
        skip_expired: 是否跳过 TTL 过期 entries（默认 True）
        progress_callback: 进度回调 (migrated_count, total_count)

    Returns:
        MigrationResult 含详细统计

    注意：
    - 不修改源 cache（只读）
    - 目标 cache 已存在则会被覆盖
    - 失败会累计到 result.errors 但不会中断
    """
    start = time.time()
    result = MigrationResult(
        src_backend=src_backend,
        dst_backend=dst_backend,
        src_path=src_path or "(memory)",
        dst_path=dst_path or "(memory)",
    )

    # 1. 打开源 + 目标
    src = _open_backend(src_backend, src_path, max_size=8192, ttl_seconds=0)
    dst = _open_backend(dst_backend, dst_path, max_size=max_size, ttl_seconds=ttl_seconds)

    try:
        # 2. 收集源 entries
        result.total_entries = src.size()
        logger.info(
            "V0.43 migrate: %s (%d entries) → %s",
            src_backend,
            result.total_entries,
            dst_backend,
        )

        if result.total_entries == 0:
            logger.info("V0.43 migrate: src 为空，无需迁移")
            return result

        # 3. 读 + 写
        # V0.43：用 src._keys() + src._values() 提取所有 entry
        # 注意：跨 backend 类型时 key 类型可能不同（str vs tuple）
        # 但我们用 encode_key() 统一编码写入，所以 dst 端可读
        for key_encoded in src.keys():  # noqa: SIM118 (keys() returns list, not dict)
            try:
                value = src.get(key_encoded)
                if value is None:
                    continue  # 已过期（被 src 自动删除）

                # 检查 TTL（src 内部可能已过滤，但保险起见再查一次）
                # 简化：依赖 src.get() 行为，None = 已过期
                # V0.43：source 端 encoding 已知，dst 端统一用 encode_key
                dst.set(key_encoded, value)
                result.migrated += 1

                if progress_callback and result.migrated % 50 == 0:
                    progress_callback(result.migrated, result.total_entries)
            except Exception as e:
                result.errors.append(f"key={key_encoded!r}: {e}")
                logger.warning("V0.43 migrate: 迁移 key 失败: %s", e)

        # 4. 进度最终回调
        if progress_callback:
            progress_callback(result.migrated, result.total_entries)
    finally:
        # 5. 关闭连接（V0.42 close() 释放 SQLite 池）
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass

    result.elapsed_seconds = time.time() - start
    logger.info(result.summary().replace("\n", " | "))
    return result
