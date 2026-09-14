"""V0.30.6 B5：Session 管理。

设计：session token 存 SQLite（独立于 auth.db），HttpOnly Cookie。
- session_id: secrets.token_urlsafe(32)
- expires_at: created_at + SESSION_LIFETIME_SECONDS
- 自动清理过期 session（启动时 + 周期性）
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """V0.30.6 B5：会话。"""

    id: str
    user_id: int
    created_at: float
    expires_at: float
    last_used_at: float

    def is_expired(self) -> bool:
        """V0.30.6 B5：检查是否过期。"""
        return time.time() >= self.expires_at


class SessionStore:
    """V0.30.6 B5：SQLite-backed session 存储。"""

    DEFAULT_DB_PATH: ClassVar[Path] = Path(".novel2all/sessions.db")

    def __init__(self, db_path: Path | None = None, lifetime_seconds: int = 7 * 24 * 3600) -> None:
        from novel2all.core.auth import SESSION_LIFETIME_SECONDS

        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lifetime_seconds = lifetime_seconds or SESSION_LIFETIME_SECONDS
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        """V0.30.6 B5：sqlite3 connect + 启用 foreign_keys（PRAGMA）。"""
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """V0.30.6 B5：初始化 sessions 表。"""
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_used_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user
                    ON sessions(user_id)
            """)

    def create(self, user_id: int) -> Session:
        """V0.30.6 B5：创建新 session。

        Returns:
            新创建的 Session（含 session_id 给 Cookie 用）
        """
        now = time.time()
        session = Session(
            id=secrets.token_urlsafe(32),
            user_id=user_id,
            created_at=now,
            expires_at=now + self.lifetime_seconds,
            last_used_at=now,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO sessions (id, user_id, created_at, expires_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session.id,
                    session.user_id,
                    session.created_at,
                    session.expires_at,
                    session.last_used_at,
                ),
            )
        return session

    def get(self, session_id: str) -> Session | None:
        """V0.30.6 B5：获取 session（自动检查过期 + 自动刷新 last_used_at）。"""
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT id, user_id, created_at, expires_at, last_used_at
                   FROM sessions WHERE id = ?""",
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            sess = Session(*row)
            if sess.is_expired():
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                return None

            # 更新 last_used_at
            conn.execute(
                "UPDATE sessions SET last_used_at = ? WHERE id = ?",
                (now, session_id),
            )
            sess.last_used_at = now
            return sess

    def delete(self, session_id: str) -> bool:
        """V0.30.6 B5：删除 session（logout）。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cur.rowcount > 0

    def delete_user_sessions(self, user_id: int) -> int:
        """V0.30.6 B5：删除用户的所有 sessions（如禁用账户时）。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            return cur.rowcount

    def cleanup_expired(self) -> int:
        """V0.30.6 B5：清理过期 session（启动时调用）。

        Returns:
            删除的过期 session 数量
        """
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            return cur.rowcount
