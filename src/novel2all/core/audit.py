"""V1.0 GA Day 11-15：审计日志（auth 事件 + 关键操作）。"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# === Constants ===

DEFAULT_DB_PATH: ClassVar[Path] = Path(".novel2all/audit.db")


# === Data Models ===


@dataclass
class AuditEvent:
    """V1.0 GA：审计事件。"""

    event_type: str  # "login" / "logout" / "login_failed" / "user_created" / "user_deleted" / "project_shared" / "project_revoked" / "rate_limited"
    user_id: int | None  # None = 未登录 / 匿名
    username: str | None  # 用于日志（user_id 可能已被删除）
    ip: str | None
    success: bool  # True = 成功 / False = 失败
    detail: str | None  # 自由文本（如 user_agent / 项目路径）
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "user_id": self.user_id,
            "username": self.username,
            "ip": self.ip,
            "success": self.success,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class AuditStore:
    """V1.0 GA：SQLite-backed 审计日志存储。"""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        """V1.0 GA：sqlite3 connect + 启用 foreign_keys + WAL。"""
        from novel2all.core.db_tuning import apply_tuning

        conn = sqlite3.connect(self.db_path)
        apply_tuning(conn)
        return conn

    def _init_db(self) -> None:
        """V1.0 GA：初始化 audit_events 表。"""
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    user_id INTEGER,
                    username TEXT,
                    ip TEXT,
                    success INTEGER NOT NULL,
                    detail TEXT,
                    timestamp REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_user
                    ON audit_events(user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_event_type
                    ON audit_events(event_type, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                    ON audit_events(timestamp DESC);
            """)

    def record(
        self,
        event_type: str,
        *,
        user_id: int | None = None,
        username: str | None = None,
        ip: str | None = None,
        success: bool = True,
        detail: str | None = None,
    ) -> None:
        """V1.0 GA：记录一个审计事件（线程安全）。"""
        event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            username=username,
            ip=ip,
            success=success,
            detail=detail,
            timestamp=time.time(),
        )
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """INSERT INTO audit_events
                        (event_type, user_id, username, ip, success, detail, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_type,
                        event.user_id,
                        event.username,
                        event.ip,
                        1 if event.success else 0,
                        event.detail,
                        event.timestamp,
                    ),
                )
            logger.info(
                "AUDIT: %s user=%s ip=%s success=%s detail=%s",
                event.event_type,
                event.username or event.user_id or "anonymous",
                event.ip or "?",
                event.success,
                event.detail or "",
            )
        except Exception as e:
            # 审计日志失败不影响主流程
            logger.warning("V1.0 GA: audit record failed: %s", e)

    def query(
        self,
        *,
        event_type: str | None = None,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """V1.0 GA：查询审计事件（按时间倒序）。"""
        conditions = []
        params: list[Any] = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"""SELECT event_type, user_id, username, ip, success, detail, timestamp
                    FROM audit_events {where_clause}
                    ORDER BY timestamp DESC LIMIT ?""",
                (*params, limit),
            )
            rows = cur.fetchall()
        return [
            {
                "event_type": r[0],
                "user_id": r[1],
                "username": r[2],
                "ip": r[3],
                "success": bool(r[4]),
                "detail": r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]

    def cleanup_old(self, max_age_seconds: int = 90 * 24 * 3600) -> int:
        """V1.0 GA：清理 90 天前的旧事件。"""
        cutoff = time.time() - max_age_seconds
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM audit_events WHERE timestamp < ?", (cutoff,))
            return cur.rowcount
