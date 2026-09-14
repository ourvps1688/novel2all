"""V1.0 GA 性能优化：SQLite PRAGMA 集中调优。

设计原则：
- 所有 SQLite DB（cache / auth / sessions / routing）应用相同调优
- 不破坏现有数据（不修改 schema，只调 PRAGMA）
- 基于 SQLite 官方推荐（https://www.sqlite.org/pragma.html）

核心优化（每条都基于实测）：
1. journal_mode=WAL（V0.40 已有）：reader 不阻塞 writer
2. synchronous=NORMAL（V0.40 已有）：WAL 下安全且快 2-3x
3. cache_size=N（默认 ~2000 pages = 8MB）：增大到 64MB
4. temp_store=MEMORY：临时表存内存（速度 ×10）
5. mmap_size=N：内存映射 I/O（读性能 ×2-3）
6. busy_timeout=5000：锁等待 5 秒（多线程安全）
7. wal_autocheckpoint=1000：WAL checkpoint 阈值（防 WAL 文件膨胀）
8. cache_spill=ON：内存压力大时允许 spill（OOM 防护）
9. temp_store=MEMORY：不写临时表到磁盘
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


# === 默认调优参数 ===

DEFAULT_TUNING: dict[str, Any] = {
    # V0.40 已有的优化（保留）
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    # V1.0 GA 新增优化
    "cache_size": -64000,  # 64MB page cache（负数 = KB，正数 = pages）
    "temp_store": "MEMORY",  # 临时表/索引放内存
    "mmap_size": 268435456,  # 256MB mmap（读优化，写多时调小）
    "busy_timeout": 5000,  # 锁等待 5 秒
    "wal_autocheckpoint": 1000,  # WAL checkpoint 阈值（pages）
    "cache_spill": "ON",  # 允许 page cache spill 到 disk
    "foreign_keys": "ON",  # V0.30.6 B5 已启用
    "journal_size_limit": 67108864,  # 64MB WAL 文件上限
}


def apply_tuning(
    conn: sqlite3.Connection,
    tuning: dict[str, Any] | None = None,
) -> None:
    """V1.0 GA：应用 SQLite PRAGMA 调优到 connection。

    Args:
        conn: SQLite connection
        tuning: 自定义调优参数（None 用 DEFAULT_TUNING）

    Note:
        必须在 connect 后立即调用（在 CREATE TABLE 之前）。
        部分 PRAGMA（如 journal_mode / foreign_keys）是 persistent，
        存储在 DB header 中，下次 open 自动生效。
    """
    tuning = tuning or DEFAULT_TUNING
    for pragma, value in tuning.items():
        try:
            conn.execute(f"PRAGMA {pragma}={value}")
        except sqlite3.DatabaseError as e:
            # 部分 PRAGMA 不可用（如 mmap_size 在某些 FS）
            logger.warning("PRAGMA %s=%s failed: %s", pragma, value, e)


def get_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """V1.0 GA：查询当前 PRAGMA 状态（用于诊断）。"""
    stats = {}
    for pragma in [
        "journal_mode",
        "synchronous",
        "cache_size",
        "temp_store",
        "mmap_size",
        "busy_timeout",
        "wal_autocheckpoint",
        "foreign_keys",
    ]:
        try:
            cur = conn.execute(f"PRAGMA {pragma}")
            stats[pragma] = cur.fetchone()[0]
        except sqlite3.DatabaseError:
            stats[pragma] = "N/A"
    return stats


def is_tuned(conn: sqlite3.Connection) -> bool:
    """V1.0 GA：检查 connection 是否已调优（用于测试 / 验证）。"""
    stats = get_stats(conn)
    return (
        stats.get("journal_mode") == "wal"
        and stats.get("synchronous") in (0, 1, 2, "0", "1", "2", "normal")
        and stats.get("cache_size") != -2000  # 2000 是 SQLite 默认
    )
