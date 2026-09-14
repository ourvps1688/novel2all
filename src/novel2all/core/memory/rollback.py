"""V0.30.6 B2：critical 自动回滚。

问题：4-agent 审查发现 critical 问题（事实错误/逻辑断裂/角色崩塌）时，
章节已写入文件 + tracking state 已更新。手动回滚 = 用户重写。

设计：WriteSnapshot（写入前快照）→ Review → 触发 critical → RollbackManager 回滚。
- 备份章节文件：.bak.{ts}（保留 7 天，自动清理）
- 备份 state：state_changes 列表（apply/rollback 配对）
- restore() 一次回滚所有改动

集成点：
1. 写章节前：snapshot() → 备份文件 + 记录 state diff
2. B1 review verdict=fail → rollback() → 恢复文件 + 反向 state changes
3. 手动回滚：CLI `novel2all rollback` + Web `/api/chapter/{n}/rollback`
4. 7 天后自动清理过期 .bak 文件
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _set_nested(data: dict, dotted_key: str, value: Any) -> None:
    """V0.30.6 B2：nested key 赋值（如 "characters.林雷"）。

    data = {"characters": {}}
    _set_nested(data, "characters.林雷", {"desc": "..."})
    # data == {"characters": {"林雷": {"desc": "..."}}}
    """
    parts = dotted_key.split(".")
    if len(parts) == 1:
        data[dotted_key] = value
        return
    # 嵌套：逐层创建中间 dict
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _delete_nested(data: dict, dotted_key: str) -> None:
    """V0.30.6 B2：nested key 删除（如 "characters.林雷"）。

    data = {"characters": {"林雷": {...}, "萧炎": {...}}}
    _delete_nested(data, "characters.林雷")
    # data == {"characters": {"萧炎": {...}}}
    """
    parts = dotted_key.split(".")
    if len(parts) == 1:
        data.pop(dotted_key, None)
        return
    # 嵌套：找到最后一层 + pop
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            return  # key 不存在
        current = current[part]
    current.pop(parts[-1], None)


# === Constants ===

BACKUP_SUFFIX = ".bak"
BACKUP_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 天自动清理


# === Data models ===


class StateChange(BaseModel):
    """V0.30.6 B2：单条 state 变更记录（apply + rollback 配对）。"""

    op: str  # "set" | "delete"
    key: str  # e.g., "characters", "foreshadowing"
    before: Any = None
    after: Any = None
    timestamp: float = Field(default_factory=time.time)


class WriteSnapshot(BaseModel):
    """V0.30.6 B2：写章节前的完整快照（用于回滚）。

    字段：
    - chapter_backup: 备份文件路径（写入前的原文件副本，可能是新增所以 None）
    - state_changes: state 变更列表（apply/rollback 配对）
    - timestamp: 快照时间
    """

    chapter_number: int
    backup_path: Path | None  # None = 原文件不存在（新增）
    state_changes: list[StateChange] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    state_file: Path


class RollbackResult(BaseModel):
    """V0.30.6 B2：回滚结果。"""

    success: bool
    chapter_number: int
    restored_from_backup: bool  # True = 文件恢复成功 / False = 删除新增
    state_changes_reverted: int  # 反向操作的 state changes 数量
    backup_path: Path | None
    message: str = ""


# === Rollback Manager ===


class RollbackManager:
    """V0.30.6 B2：写章节快照 + 回滚。

    用法：
        manager = RollbackManager(project_root)

        # 1. 写前快照
        snapshot = manager.snapshot(chapter_number=5)

        # 2. ... 写章节（pipeline 写文件 + 更新 state）...

        # 3. 触发回滚
        if review.verdict == "fail":
            result = manager.rollback(snapshot)
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.prose_dir = self.project_root / "正文"
        # 兼容 ProjectStructure.chapter_prose
        try:
            from novel2all.core.project import ProjectStructure

            self.project = ProjectStructure(root=self.project_root)
        except Exception as e:
            logger.warning("RollbackManager: ProjectStructure 加载失败: %s", e)
            self.project = None

    def snapshot(self, chapter_number: int) -> WriteSnapshot:
        """V0.30.6 B2：写章节前快照。

        1. 备份章节文件（如果存在）
        2. 读取当前 state（用于后续回滚对比）

        Returns:
            WriteSnapshot（后续 rollback 时传入）
        """
        from novel2all.core.project import ProjectStructure

        if self.project is None:
            self.project = ProjectStructure(root=self.project_root)

        prose_path = self.project.chapter_prose(chapter_number)
        backup_path = None

        if prose_path.exists():
            # 备份现有文件
            ts = int(time.time())
            backup_path = prose_path.with_suffix(f".md{BACKUP_SUFFIX}.{ts}")
            backup_path.write_bytes(prose_path.read_bytes())
            logger.info("B2 backup: %s → %s", prose_path, backup_path)
        else:
            logger.info("B2 snapshot: chapter %d 不存在（新增场景）", chapter_number)

        return WriteSnapshot(
            chapter_number=chapter_number,
            backup_path=backup_path,
            state_changes=[],  # 由 pipeline 在写时填充
            timestamp=time.time(),
            state_file=self.project.tracking_state_file,
        )

    def record_state_change(self, snapshot: WriteSnapshot, change: StateChange) -> None:
        """V0.30.6 B2：记录 state 变更（由 pipeline 调用）。"""
        snapshot.state_changes.append(change)

    def rollback(self, snapshot: WriteSnapshot) -> RollbackResult:
        """V0.30.6 B2：回滚到 snapshot 状态。

        步骤：
        1. 反向应用 state_changes（按倒序）
        2. 恢复章节文件（从 backup）
        3. 删除 .bak 文件（标记已使用）

        Returns:
            RollbackResult 含 success + details
        """
        try:
            # 1. 反向 state changes（后进先出）
            state_reverted = 0
            if snapshot.state_file.exists() and snapshot.state_changes:
                try:
                    state_data = json.loads(snapshot.state_file.read_text(encoding="utf-8"))
                except Exception:
                    state_data = {}

                for change in reversed(snapshot.state_changes):
                    if change.op == "set":
                        # 回滚 = 还原 before 值（支持 nested key 如 "characters.林雷"）
                        if change.before is None:
                            _delete_nested(state_data, change.key)
                        else:
                            _set_nested(state_data, change.key, change.before)
                    elif change.op == "delete" and change.after is not None:
                        # 原已删除 → 还原 after（即恢复删除前的值）
                        _set_nested(state_data, change.key, change.after)
                    state_reverted += 1

                # 写回
                snapshot.state_file.write_text(
                    json.dumps(state_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info("B2 state rollback: %d changes reverted", state_reverted)

            # 2. 恢复章节文件
            restored = False
            if self.project is None:
                from novel2all.core.project import ProjectStructure

                self.project = ProjectStructure(root=self.project_root)
            prose_path = self.project.chapter_prose(snapshot.chapter_number)

            if snapshot.backup_path and snapshot.backup_path.exists():
                # 有备份 → 恢复原文件
                prose_path.write_bytes(snapshot.backup_path.read_bytes())
                # 删除 .bak 文件（标记已使用）
                snapshot.backup_path.unlink()
                restored = True
                logger.info("B2 chapter restored from backup: %s", snapshot.backup_path)
            elif prose_path.exists():
                # 无备份（新增场景）→ 删除新文件
                prose_path.unlink()
                logger.info("B2 chapter deleted (newly created): %s", prose_path)

            return RollbackResult(
                success=True,
                chapter_number=snapshot.chapter_number,
                restored_from_backup=restored,
                state_changes_reverted=state_reverted,
                backup_path=snapshot.backup_path,
                message=f"回滚成功：{'恢复' if restored else '删除新增'}章节 + {state_reverted} 条 state 变更",
            )

        except Exception as e:
            logger.exception("B2 rollback failed")
            return RollbackResult(
                success=False,
                chapter_number=snapshot.chapter_number,
                restored_from_backup=False,
                state_changes_reverted=0,
                backup_path=snapshot.backup_path,
                message=f"回滚失败: {e}",
            )

    @staticmethod
    def cleanup_old_backups(
        project_root: Path, max_age_seconds: int = BACKUP_MAX_AGE_SECONDS
    ) -> int:
        """V0.30.6 B2：清理过期 .bak 文件（默认 7 天前）。

        Returns:
            删除的文件数
        """
        prose_dir = Path(project_root) / "正文"
        if not prose_dir.exists():
            return 0

        now = time.time()
        deleted = 0
        for backup in prose_dir.glob(f"*{BACKUP_SUFFIX}.*"):
            try:
                # 文件名格式：xxx.md.bak.{ts}
                # ts 是最后一段数字
                parts = backup.name.split(".")
                ts_str = parts[-1]
                ts = int(ts_str)
                if now - ts > max_age_seconds:
                    backup.unlink()
                    deleted += 1
                    logger.info("B2 cleaned up old backup: %s", backup)
            except (ValueError, IndexError, OSError):
                # 跳过无法解析的 .bak 文件
                continue
        return deleted


# === Helper: snapshot 用于 review 集成 ===


def auto_rollback_on_critical(
    manager: RollbackManager,
    snapshot: WriteSnapshot,
    review_verdict: str,
) -> RollbackResult | None:
    """V0.30.6 B2：B1 review verdict=fail → 自动回滚。

    Returns:
        RollbackResult（已回滚）/ None（verdict ≠ fail，不回滚）

    集成到 /api/write/stream：
        snapshot = manager.snapshot(chapter)
        ... write chapter ...
        review = await b1_review(content)
        if review.overall_verdict == "fail":
            result = auto_rollback_on_critical(manager, snapshot, review.overall_verdict)
            yield sse_event("auto_rollback", result.model_dump(mode="json"))
    """
    if review_verdict != "fail":
        return None
    return manager.rollback(snapshot)
