"""V0.30.6 B5：多用户基础架构。

设计原则（per MEMORY 用户偏好）：
- Session Cookie：HttpOnly + SameSite=Strict；不存 localStorage
- 单账号 ADMIN_USER/ADMIN_PASS 环境变量 + 多用户 DB（SQLite）
- 限流：同 IP 5 分钟内 5 次失败 → 锁定 5 分钟
- 零外部依赖：stdlib hashlib + secrets + sqlite3

数据模型：
- User：id, username, password_hash, role, created_at, disabled
- ProjectMembership：user_id, project_root, role, created_at
  - role: 'owner' | 'editor' | 'viewer'

存储：`.novel2all/auth.db`（SQLite）
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# === Constants ===

# V0.30.6 B5：密码哈希参数（PBKDF2-HMAC-SHA256，600K 迭代 = OWASP 2023 推荐）
PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_BYTES = 16
PBKDF2_HASH_BYTES = 32

# V0.30.6 B5：限流（每 IP 5 分钟 5 次失败 → 锁 5 分钟）
RATE_LIMIT_MAX_FAILS = 5
RATE_LIMIT_WINDOW_SECONDS = 300
RATE_LIMIT_LOCKOUT_SECONDS = 300

# V0.30.6 B5：Session 配置
SESSION_COOKIE_NAME = "n2a_session"
SESSION_LIFETIME_SECONDS = 7 * 24 * 3600  # 7 天
SESSION_REFRESH_THRESHOLD = 24 * 3600  # 1 天内快过期时刷新


# === Data Models ===


@dataclass
class User:
    """V0.30.6 B5：用户。"""

    id: int
    username: str
    password_hash: str
    role: str  # 'admin' | 'editor' | 'viewer'
    created_at: float
    disabled: bool = False

    def to_dict(self, *, with_hash: bool = False) -> dict[str, Any]:
        """V0.30.6 B5：导出 dict（默认隐藏 password_hash）。"""
        d = {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "disabled": self.disabled,
        }
        if with_hash:
            d["password_hash"] = self.password_hash
        return d


@dataclass
class ProjectMembership:
    """V0.30.6 B5：用户对项目的访问权限。"""

    user_id: int
    project_root: str  # 绝对路径
    role: str  # 'owner' | 'editor' | 'viewer'
    granted_at: float
    granted_by: int  # user_id of granter

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "project_root": self.project_root,
            "role": self.role,
            "granted_at": self.granted_at,
            "granted_by": self.granted_by,
        }


# === Password Hashing ===


def hash_password(plain: str) -> str:
    """V0.30.6 B5：PBKDF2-HMAC-SHA256 哈希密码。

    Returns:
        格式：pbkdf2_sha256$iterations$salt_hex$hash_hex
    """
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=PBKDF2_HASH_BYTES
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${hash_bytes.hex()}"


def verify_password(plain: str, stored_hash: str) -> bool:
    """V0.30.6 B5：验证密码（constant-time 比较）。"""
    try:
        algo, iterations_str, salt_hex, hash_hex = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    # constant-time 比较（防 timing attack）
    return secrets.compare_digest(candidate, expected)


# === AuthStore ===


class AuthStore:
    """V0.30.6 B5：SQLite-backed 用户/项目授权存储。"""

    DEFAULT_DB_PATH: ClassVar[Path] = Path(".novel2all/auth.db")

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = (
            threading.RLock()
        )  # V1.0.2 hotfix：RLock 而非 Lock，避免 _bootstrap_admin_from_env → create_user 重入死锁
        self._init_db()
        self._bootstrap_admin_from_env()

    def _connect(self):
        """V0.30.6 B5：sqlite3 connect + 启用 foreign_keys（PRAGMA）。"""
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """V0.30.6 B5：初始化 SQLite 表。"""
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'viewer')),
                    created_at REAL NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS memberships (
                    user_id INTEGER NOT NULL,
                    project_root TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('owner', 'editor', 'viewer')),
                    granted_at REAL NOT NULL,
                    granted_by INTEGER NOT NULL,
                    PRIMARY KEY (user_id, project_root),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memberships_project
                    ON memberships(project_root);
            """)

    def _bootstrap_admin_from_env(self) -> None:
        """V0.30.6 B5：从环境变量创建初始 admin（如果用户表为空）。"""
        admin_user = os.environ.get("NOVEL2ALL_ADMIN_USER")
        admin_pass = os.environ.get("NOVEL2ALL_ADMIN_PASS")
        if not admin_user or not admin_pass:
            return

        with self._lock:
            conn = self._connect()
            cur = conn.execute("SELECT COUNT(*) FROM users")
            (count,) = cur.fetchone()
            if count == 0:
                self.create_user(admin_user, admin_pass, role="admin")
                logger.info("B5 bootstrap admin from env: %s", admin_user)
            conn.close()

    # === User CRUD ===

    def create_user(
        self,
        username: str,
        password: str,
        *,
        role: str = "editor",
    ) -> User:
        """V0.30.6 B5：创建用户。

        Args:
            username: 用户名（唯一）
            password: 明文密码（自动哈希）
            role: 'admin' | 'editor' | 'viewer'

        Returns:
            创建的 User

        Raises:
            ValueError: 用户名已存在或角色无效
        """
        if role not in {"admin", "editor", "viewer"}:
            raise ValueError(f"Invalid role: {role}")
        if len(username) < 3:
            raise ValueError("Username too short (min 3 chars)")

        password_hash = hash_password(password)
        now = time.time()
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO users (username, password_hash, role, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (username, password_hash, role, now),
                )
                user_id = cur.lastrowid
            return User(
                id=user_id,
                username=username,
                password_hash=password_hash,
                role=role,
                created_at=now,
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Username already exists: {username}") from e

    def authenticate(self, username: str, password: str) -> User | None:
        """V0.30.6 B5：验证用户名 + 密码。

        Returns:
            验证成功返回 User；失败返回 None（含账号禁用）
        """
        user = self.get_user_by_username(username)
        if user is None or user.disabled:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def get_user_by_username(self, username: str) -> User | None:
        """V0.30.6 B5：按用户名查用户。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT id, username, password_hash, role, created_at, disabled
                   FROM users WHERE username = ?""",
                (username,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return User(*row)

    def get_user_by_id(self, user_id: int) -> User | None:
        """V0.30.6 B5：按 ID 查用户。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT id, username, password_hash, role, created_at, disabled
                   FROM users WHERE id = ?""",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return User(*row)

    def list_users(self) -> list[User]:
        """V0.30.6 B5：列所有用户。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT id, username, password_hash, role, created_at, disabled
                   FROM users ORDER BY id"""
            )
            rows = cur.fetchall()
        return [User(*r) for r in rows]

    def delete_user(self, user_id: int) -> bool:
        """V0.30.6 B5：删除用户（CASCADE 删除 memberships）。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0

    def set_user_disabled(self, user_id: int, disabled: bool) -> bool:
        """V0.30.6 B5：启用/禁用用户。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET disabled = ? WHERE id = ?",
                (1 if disabled else 0, user_id),
            )
            return cur.rowcount > 0

    # === ProjectMembership ===

    def grant_project_access(
        self,
        user_id: int,
        project_root: str,
        role: str,
        granted_by: int,
    ) -> ProjectMembership:
        """V0.30.6 B5：授予用户项目访问权限（upsert）。"""
        if role not in {"owner", "editor", "viewer"}:
            raise ValueError(f"Invalid project role: {role}")
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO memberships (user_id, project_root, role, granted_at, granted_by)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, project_root) DO UPDATE SET
                       role = excluded.role,
                       granted_at = excluded.granted_at,
                       granted_by = excluded.granted_by""",
                (user_id, project_root, role, now, granted_by),
            )
        return ProjectMembership(user_id, project_root, role, now, granted_by)

    def revoke_project_access(self, user_id: int, project_root: str) -> bool:
        """V0.30.6 B5：撤销用户项目访问权限。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM memberships WHERE user_id = ? AND project_root = ?",
                (user_id, project_root),
            )
            return cur.rowcount > 0

    def get_project_role(self, user_id: int, project_root: str) -> str | None:
        """V0.30.6 B5：查用户对项目的角色（无权限返回 None）。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT role FROM memberships
                   WHERE user_id = ? AND project_root = ?""",
                (user_id, project_root),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def list_user_projects(self, user_id: int) -> list[ProjectMembership]:
        """V0.30.6 B5：列用户的所有项目授权。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT user_id, project_root, role, granted_at, granted_by
                   FROM memberships WHERE user_id = ? ORDER BY granted_at DESC""",
                (user_id,),
            )
            rows = cur.fetchall()
        return [ProjectMembership(*r) for r in rows]

    def list_project_users(self, project_root: str) -> list[ProjectMembership]:
        """V0.30.6 B5：列项目所有用户授权。"""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """SELECT user_id, project_root, role, granted_at, granted_by
                   FROM memberships WHERE project_root = ? ORDER BY granted_at""",
                (project_root,),
            )
            rows = cur.fetchall()
        return [ProjectMembership(*r) for r in rows]


# === Rate Limiter ===


class RateLimiter:
    """V0.30.6 B5：限流（防爆破）。

    规则：同 IP 5 分钟内 5 次失败 → 锁定 5 分钟（拒绝任何登录尝试）。
    """

    def __init__(
        self,
        max_fails: int = RATE_LIMIT_MAX_FAILS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        lockout_seconds: int = RATE_LIMIT_LOCKOUT_SECONDS,
    ) -> None:
        self.max_fails = max_fails
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._lock = (
            threading.RLock()
        )  # V1.0.2 hotfix：RLock 而非 Lock，避免 _bootstrap_admin_from_env → create_user 重入死锁
        self._fail_counts: dict[str, list[float]] = {}  # ip -> [timestamps]
        self._locked_until: dict[str, float] = {}  # ip -> epoch

    def is_locked(self, ip: str) -> bool:
        """V0.30.6 B5：检查 IP 是否被锁定。"""
        with self._lock:
            locked_until = self._locked_until.get(ip, 0)
            return time.time() < locked_until

    def record_fail(self, ip: str) -> bool:
        """V0.30.6 B5：记录登录失败。

        Returns:
            True = 已触发锁定 / False = 未触发
        """
        with self._lock:
            now = time.time()
            # 清理窗口外的旧记录
            self._fail_counts[ip] = [
                ts for ts in self._fail_counts.get(ip, []) if now - ts < self.window_seconds
            ]
            self._fail_counts[ip].append(now)

            if len(self._fail_counts[ip]) >= self.max_fails:
                self._locked_until[ip] = now + self.lockout_seconds
                # 重置失败计数
                self._fail_counts[ip] = []
                return True
            return False

    def record_success(self, ip: str) -> None:
        """V0.30.6 B5：登录成功 → 重置失败计数 + 锁定。"""
        with self._lock:
            self._fail_counts.pop(ip, None)
            self._locked_until.pop(ip, None)
