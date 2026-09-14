"""V0.30.6 B5：多用户基础架构测试（密码 / 用户 CRUD / 限流）。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from novel2all.core.auth import (
    AuthStore,
    ProjectMembership,
    RateLimiter,
    User,
    hash_password,
    verify_password,
)
from novel2all.core.session import Session, SessionStore

# === Fixtures ===


@pytest.fixture
def store(tmp_path: Path) -> AuthStore:
    """V0.30.6 B5：临时 SQLite AuthStore。"""
    return AuthStore(db_path=tmp_path / "auth.db")


@pytest.fixture
def session_store(tmp_path: Path) -> SessionStore:
    """V0.30.6 B5：临时 SQLite SessionStore。"""
    return SessionStore(db_path=tmp_path / "sessions.db")


# === Test 1: Password Hashing ===


class TestPasswordHashing:
    """V0.30.6 B5：密码哈希 roundtrip + 安全性。"""

    def test_hash_password_format(self) -> None:
        """V0.30.6 B5：哈希格式 = pbkdf2_sha256$iterations$salt$hash。"""
        h = hash_password("hello")
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert int(parts[1]) == 600_000  # OWASP 2023 推荐
        assert len(parts[2]) == 32  # 16 bytes hex = 32 chars
        assert len(parts[3]) == 64  # 32 bytes hex = 64 chars

    def test_verify_password_roundtrip(self) -> None:
        """V0.30.6 B5：哈希 → 验证 → True。"""
        h = hash_password("correct_password")
        assert verify_password("correct_password", h) is True

    def test_verify_password_wrong(self) -> None:
        """V0.30.6 B5：错误密码 → False。"""
        h = hash_password("correct_password")
        assert verify_password("wrong_password", h) is False

    def test_hash_salt_randomness(self) -> None:
        """V0.30.6 B5：相同密码 2 次哈希结果不同（salt 随机）。"""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # salt 不同

    def test_verify_password_corrupted_hash(self) -> None:
        """V0.30.6 B5：损坏的哈希 → False（不 crash）。"""
        assert verify_password("test", "invalid_hash_format") is False
        assert verify_password("test", "pbkdf2_sha256$notanumber$salt$hash") is False
        assert verify_password("test", "wrong_algo$600000$aa$bb") is False


# === Test 2: User CRUD ===


class TestUserCRUD:
    """V0.30.6 B5：用户 CRUD。"""

    def test_create_user_returns_user(self, store: AuthStore) -> None:
        """V0.30.6 B5：创建用户返回 User 对象。"""
        user = store.create_user("alice", "secret123")
        assert isinstance(user, User)
        assert user.username == "alice"
        assert user.role == "editor"  # 默认
        assert user.id > 0
        assert user.disabled is False

    def test_create_user_with_role(self, store: AuthStore) -> None:
        """V0.30.6 B5：创建用户指定 role。"""
        user = store.create_user("admin_user", "pass", role="admin")
        assert user.role == "admin"

    def test_create_user_duplicate_raises(self, store: AuthStore) -> None:
        """V0.30.6 B5：重复用户名 → ValueError。"""
        store.create_user("alice", "pass1")
        with pytest.raises(ValueError, match="already exists"):
            store.create_user("alice", "pass2")

    def test_create_user_invalid_role_raises(self, store: AuthStore) -> None:
        """V0.30.6 B5：无效 role → ValueError。"""
        with pytest.raises(ValueError, match="Invalid role"):
            store.create_user("alice", "pass", role="superadmin")

    def test_create_user_too_short_username(self, store: AuthStore) -> None:
        """V0.30.6 B5：用户名 < 3 字 → ValueError。"""
        with pytest.raises(ValueError, match="too short"):
            store.create_user("ab", "pass")

    def test_authenticate_success(self, store: AuthStore) -> None:
        """V0.30.6 B5：正确密码认证成功。"""
        store.create_user("alice", "secret123")
        user = store.authenticate("alice", "secret123")
        assert user is not None
        assert user.username == "alice"

    def test_authenticate_wrong_password(self, store: AuthStore) -> None:
        """V0.30.6 B5：错误密码 → None。"""
        store.create_user("alice", "secret123")
        assert store.authenticate("alice", "wrong") is None

    def test_authenticate_unknown_user(self, store: AuthStore) -> None:
        """V0.30.6 B5：未知用户 → None。"""
        assert store.authenticate("nobody", "any") is None

    def test_authenticate_disabled_user(self, store: AuthStore) -> None:
        """V0.30.6 B5：禁用用户 → None。"""
        user = store.create_user("alice", "secret")
        store.set_user_disabled(user.id, True)
        assert store.authenticate("alice", "secret") is None

    def test_get_user_by_username(self, store: AuthStore) -> None:
        """V0.30.6 B5：按用户名查。"""
        store.create_user("alice", "pass")
        user = store.get_user_by_username("alice")
        assert user is not None
        assert user.username == "alice"

    def test_get_user_by_id(self, store: AuthStore) -> None:
        """V0.30.6 B5：按 ID 查。"""
        created = store.create_user("alice", "pass")
        fetched = store.get_user_by_id(created.id)
        assert fetched.username == "alice"

    def test_list_users(self, store: AuthStore) -> None:
        """V0.30.6 B5：列所有用户。"""
        store.create_user("alice", "p")
        store.create_user("bob", "p")
        users = store.list_users()
        assert len(users) == 2
        assert {u.username for u in users} == {"alice", "bob"}

    def test_delete_user(self, store: AuthStore) -> None:
        """V0.30.6 B5：删除用户。"""
        user = store.create_user("alice", "p")
        assert store.delete_user(user.id) is True
        assert store.get_user_by_id(user.id) is None

    def test_delete_user_cascades_memberships(self, store: AuthStore) -> None:
        """V0.30.6 B5：删除用户级联删除 memberships。"""
        user = store.create_user("alice", "p")
        store.grant_project_access(user.id, "/path/to/proj", "owner", user.id)
        store.delete_user(user.id)
        assert store.get_project_role(user.id, "/path/to/proj") is None

    def test_user_to_dict_hides_hash(self) -> None:
        """V0.30.6 B5：to_dict 默认隐藏 password_hash。"""
        user = User(1, "alice", "hash_secret", "editor", 1234567890.0)
        d = user.to_dict()
        assert "password_hash" not in d
        assert d["username"] == "alice"

    def test_user_to_dict_with_hash(self) -> None:
        """V0.30.6 B5：to_dict(with_hash=True) 暴露 password_hash（admin 内部用）。"""
        user = User(1, "alice", "hash_secret", "editor", 1234567890.0)
        d = user.to_dict(with_hash=True)
        assert d["password_hash"] == "hash_secret"


# === Test 3: ProjectMembership ===


class TestProjectMembership:
    """V0.30.6 B5：项目授权 CRUD。"""

    def test_grant_and_get_role(self, store: AuthStore) -> None:
        """V0.30.6 B5：授予 + 查询。"""
        user = store.create_user("alice", "p")
        store.grant_project_access(user.id, "/proj/a", "owner", user.id)
        assert store.get_project_role(user.id, "/proj/a") == "owner"

    def test_grant_upsert_updates_role(self, store: AuthStore) -> None:
        """V0.30.6 B5：重复 grant 同 (user, project) → upsert 更新 role。"""
        user = store.create_user("alice", "p")
        admin = store.create_user("admin", "p", role="admin")
        store.grant_project_access(user.id, "/proj", "viewer", admin.id)
        store.grant_project_access(user.id, "/proj", "editor", admin.id)
        assert store.get_project_role(user.id, "/proj") == "editor"

    def test_get_project_role_unauthorized(self, store: AuthStore) -> None:
        """V0.30.6 B5：无权限用户 → None。"""
        user = store.create_user("alice", "p")
        assert store.get_project_role(user.id, "/no/access") is None

    def test_grant_invalid_role_raises(self, store: AuthStore) -> None:
        """V0.30.6 B5：无效 project role → ValueError。"""
        user = store.create_user("alice", "p")
        with pytest.raises(ValueError, match="Invalid project role"):
            store.grant_project_access(user.id, "/proj", "superadmin", user.id)

    def test_revoke_project_access(self, store: AuthStore) -> None:
        """V0.30.6 B5：撤销权限。"""
        user = store.create_user("alice", "p")
        store.grant_project_access(user.id, "/proj", "viewer", user.id)
        assert store.revoke_project_access(user.id, "/proj") is True
        assert store.get_project_role(user.id, "/proj") is None

    def test_revoke_nonexistent_returns_false(self, store: AuthStore) -> None:
        """V0.30.6 B5：撤销不存在的授权 → False。"""
        user = store.create_user("alice", "p")
        assert store.revoke_project_access(user.id, "/proj") is False

    def test_list_user_projects(self, store: AuthStore) -> None:
        """V0.30.6 B5：列用户的所有项目。"""
        user = store.create_user("alice", "p")
        admin = store.create_user("admin", "p", role="admin")
        store.grant_project_access(user.id, "/proj1", "owner", admin.id)
        store.grant_project_access(user.id, "/proj2", "editor", admin.id)
        projects = store.list_user_projects(user.id)
        assert len(projects) == 2
        assert {p.project_root for p in projects} == {"/proj1", "/proj2"}

    def test_list_project_users(self, store: AuthStore) -> None:
        """V0.30.6 B5：列项目的所有用户授权。"""
        alice = store.create_user("alice", "p")
        bob = store.create_user("bob", "p")
        admin = store.create_user("admin", "p", role="admin")
        store.grant_project_access(alice.id, "/proj", "owner", admin.id)
        store.grant_project_access(bob.id, "/proj", "editor", admin.id)
        users = store.list_project_users("/proj")
        assert len(users) == 2

    def test_membership_to_dict(self) -> None:
        """V0.30.6 B5：to_dict 字段完整。"""
        m = ProjectMembership(1, "/proj", "owner", 1234.0, 2)
        d = m.to_dict()
        assert d["user_id"] == 1
        assert d["project_root"] == "/proj"
        assert d["role"] == "owner"
        assert d["granted_at"] == 1234.0
        assert d["granted_by"] == 2


# === Test 4: RateLimiter ===


class TestRateLimiter:
    """V0.30.6 B5：限流（防爆破）。"""

    def test_initial_not_locked(self) -> None:
        """V0.30.6 B5：初始状态不限流。"""
        limiter = RateLimiter()
        assert limiter.is_locked("1.2.3.4") is False

    def test_locked_after_max_fails(self) -> None:
        """V0.30.6 B5：5 次失败 → 锁定。"""
        limiter = RateLimiter(max_fails=5, window_seconds=300, lockout_seconds=300)
        for _ in range(5):
            locked = limiter.record_fail("1.2.3.4")
        assert locked is True
        assert limiter.is_locked("1.2.3.4") is True

    def test_not_locked_below_threshold(self) -> None:
        """V0.30.6 B5：4 次失败 → 仍可用。"""
        limiter = RateLimiter(max_fails=5)
        for _ in range(4):
            assert limiter.record_fail("1.2.3.4") is False
        assert limiter.is_locked("1.2.3.4") is False

    def test_success_resets_counter(self) -> None:
        """V0.30.6 B5：成功后重置计数。"""
        limiter = RateLimiter(max_fails=5)
        for _ in range(4):
            limiter.record_fail("1.2.3.4")
        limiter.record_success("1.2.3.4")
        # 再失败 4 次不会锁定（计数已重置）
        for _ in range(4):
            assert limiter.record_fail("1.2.3.4") is False

    def test_different_ips_isolated(self) -> None:
        """V0.30.6 B5：不同 IP 独立计数。"""
        limiter = RateLimiter(max_fails=3)
        for _ in range(3):
            limiter.record_fail("ip1")
        assert limiter.is_locked("ip1") is True
        assert limiter.is_locked("ip2") is False

    def test_lockout_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """V0.30.6 B5：锁定时间到期后解锁。"""
        limiter = RateLimiter(max_fails=3, window_seconds=300, lockout_seconds=1)
        for _ in range(3):
            limiter.record_fail("1.2.3.4")
        assert limiter.is_locked("1.2.3.4") is True
        time.sleep(1.1)
        assert limiter.is_locked("1.2.3.4") is False


# === Test 5: SessionStore ===


class TestSessionStore:
    """V0.30.6 B5：Session 存储 + 过期清理。"""

    def test_create_session(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：创建 session 返回 ID。"""
        sess = session_store.create(user_id=1)
        assert isinstance(sess, Session)
        assert len(sess.id) >= 32
        assert sess.user_id == 1

    def test_get_session(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：按 ID 查 session。"""
        sess = session_store.create(user_id=1)
        fetched = session_store.get(sess.id)
        assert fetched is not None
        assert fetched.id == sess.id
        assert fetched.user_id == 1

    def test_get_nonexistent_returns_none(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：查不存在的 session → None。"""
        assert session_store.get("nonexistent_id") is None

    def test_delete_session(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：删除 session。"""
        sess = session_store.create(user_id=1)
        assert session_store.delete(sess.id) is True
        assert session_store.get(sess.id) is None

    def test_delete_user_sessions(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：删除用户的所有 session。"""
        for _ in range(3):
            session_store.create(user_id=1)
        session_store.create(user_id=2)
        deleted = session_store.delete_user_sessions(user_id=1)
        assert deleted == 3

    def test_cleanup_expired(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：清理过期 session。"""
        sess = session_store.create(user_id=1)
        # 手动让 session 过期
        with sqlite3_w(session_store.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE id = ?", (time.time() - 10, sess.id)
            )
        deleted = session_store.cleanup_expired()
        assert deleted >= 1
        assert session_store.get(sess.id) is None

    def test_session_refreshes_last_used(self, session_store: SessionStore) -> None:
        """V0.30.6 B5：get 自动更新 last_used_at。"""
        sess = session_store.create(user_id=1)
        original_last_used = sess.last_used_at
        time.sleep(0.05)
        fetched = session_store.get(sess.id)
        assert fetched.last_used_at > original_last_used


def sqlite3_w(path: Path):
    """V0.30.6 B5：测试 helper（with-context manager for sqlite3.connect）。"""
    import sqlite3

    class _ConnCM:
        def __enter__(self):
            self.conn = sqlite3.connect(str(path))
            return self.conn

        def __exit__(self, *exc):
            self.conn.commit()
            self.conn.close()

    return _ConnCM()


# === Test 6: Concurrent access (threading.Lock) ===


class TestConcurrency:
    """V0.30.6 B5：多线程并发安全。"""

    def test_concurrent_user_create(self, tmp_path: Path) -> None:
        """V0.30.6 B5：多线程并发创建用户不冲突（threading.Lock 保护）。"""
        store = AuthStore(db_path=tmp_path / "auth.db")
        results: list[User] = []
        errors: list[Exception] = []

        def create_user(i: int) -> None:
            try:
                user = store.create_user(f"user_{i}", "pass")
                results.append(user)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_user, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
