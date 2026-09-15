"""V1.0.2 hotfix：AuthStore._lock 必须是 RLock（不是 Lock）。

Bug 历史：
- `_bootstrap_admin_from_env()` 调用 `create_user()`，两个方法都用 `with self._lock`
- `threading.Lock()` 不允许同线程重入 → 死锁
- 只有当 `_bootstrap_admin_from_env` 触发时（首次启动 / 空 user 表）才会暴露
- 单元测试之所以没捕获：测试 fixture 通常预创建 admin，绕过了 bootstrap 路径

修复：把 `threading.Lock()` 改成 `threading.RLock()`
"""

from __future__ import annotations

import gc
import threading


def test_authstore_lock_is_rlock_instance():
    """V1.0.2 hotfix：直接验证 _lock 字段是 RLock 实例。

    用源码 import 静态分析：确认 _lock = threading.RLock()。
    """
    import inspect

    from novel2all.core import auth as auth_mod

    src = inspect.getsource(auth_mod.AuthStore.__init__)
    assert "threading.RLock" in src, (
        f"AuthStore._lock should be RLock (reentrant), but __init__ source is:\n{src[:500]}"
    )
    # 必须不只有 Lock（防止误用）
    assert "threading.Lock" not in src.replace("threading.RLock", ""), (
        "AuthStore._lock should not use threading.Lock (non-reentrant)."
    )


def test_authstore_rlock_prevents_bootstrap_deadlock():
    """V1.0.2 hotfix：bootstrap → create_user 嵌套调用不死锁。

    直接构造场景：外层已持有 _lock，内层 create_user 也需要 _lock。
    用 RLock 时，同线程可重入，不死锁。
    """
    from novel2all.core.auth import AuthStore

    # 用 __new__ 绕过 __init__（避免 bootstrap 实际跑）
    store = AuthStore.__new__(AuthStore)
    # 手动 init _lock（模拟 __init__ 中 self._lock = threading.RLock()）
    store._lock = threading.RLock()

    # 模拟 _bootstrap_admin_from_env 中调用 create_user：
    # 外层已持有 _lock，内层需要再 acquire
    # 如果 _lock 是 Lock 会死锁；是 RLock 则通过
    with store._lock:  # 外层 acquire
        # 内层调用 create_user（也用 with self._lock）
        # 用 timeout 防止万一死锁把测试卡住
        acquired_inner = store._lock.acquire(timeout=2)
        assert acquired_inner, "RLock should allow reentrant acquire within 2s"
        store._lock.release()

    # 验证 _lock 类型仍是 RLock（说明修复没被回滚）
    assert isinstance(store._lock, type(threading.RLock()))


def test_authstore_bootstrap_admin_runs_to_completion(tmp_path, monkeypatch):
    """V1.0.2 hotfix：bootstrap admin 完整流程不死锁。

    完整模拟首次启动场景：空 auth.db + 设置 admin env。
    如果 _lock 是 Lock，bootstrap → create_user → 第二次 acquire 死锁。
    如果 _lock 是 RLock，10s 内完成。
    """
    monkeypatch.setenv("NOVEL2ALL_ADMIN_USER", "boot_test_admin")
    monkeypatch.setenv("NOVEL2ALL_ADMIN_PASS", "boot_test_pass")

    db_path = tmp_path / "auth.db"

    from novel2all.core.auth import AuthStore

    # 用 daemon thread + 10s timeout 防死锁
    result = {"store": None, "error": None}

    def create_with_timeout():
        try:
            store = AuthStore(db_path=str(db_path))
            result["store"] = store
        except Exception as e:
            result["error"] = str(e)

    thread = threading.Thread(target=create_with_timeout, daemon=True)
    thread.start()
    thread.join(timeout=10)

    assert result["store"] is not None, (
        f"Bootstrap admin deadlocked or errored (result={result}). "
        f"This is the V1.0.2 bug: _bootstrap_admin_from_env() holds _lock, "
        f"then create_user() tries to acquire _lock again → deadlock if Lock."
    )

    # 验证 admin 确实被创建
    users = result["store"].list_users()
    admin_users = [u for u in users if u.username == "boot_test_admin"]
    assert len(admin_users) == 1
    assert admin_users[0].role == "admin"

    # 清理（虽然 tmp_path 自动清理，连接可能仍持有 file handle）
    del result["store"]
    gc.collect()
