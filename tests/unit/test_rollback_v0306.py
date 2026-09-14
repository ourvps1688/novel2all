"""V0.30.6 B2：critical 自动回滚测试。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from novel2all.core.memory.rollback import (
    BACKUP_SUFFIX,
    RollbackManager,
    StateChange,
    auto_rollback_on_critical,
)

# === Fixtures ===


@pytest.fixture
def project_with_chapter(tmp_path: Path) -> Path:
    """V0.30.6 B2：含已存在章节 + state 的标准项目结构。"""
    (tmp_path / "_tracking-state.json").write_text(
        json.dumps(
            {
                "characters": {"林雷": {"description": "18岁剑客"}},
                "foreshadowing": [],
                "chapters_written": [1, 2],
            }
        ),
        encoding="utf-8",
    )
    prose_dir = tmp_path / "正文"
    prose_dir.mkdir()
    (prose_dir / "第005章.md").write_text(
        "# 第5章\n\n原内容：林雷在苍茫镇与萧炎对话。",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def project_empty(tmp_path: Path) -> Path:
    """V0.30.6 B2：空项目（无现有章节，用于测试新增场景）。"""
    (tmp_path / "_tracking-state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "正文").mkdir()
    return tmp_path


# === Test 1: snapshot 创建 ===


class TestSnapshot:
    """V0.30.6 B2：snapshot 创建备份文件 + 记录元数据。"""

    def test_snapshot_existing_chapter_creates_backup(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：snapshot 已存在章节 → 创建 .bak 备份。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        assert snapshot.chapter_number == 5
        assert snapshot.backup_path is not None
        assert snapshot.backup_path.exists()
        # 文件名含 .bak + timestamp（带时间戳 suffix）
        assert BACKUP_SUFFIX in str(snapshot.backup_path)
        # 备份文件名格式：xxx.md.bak.{ts}
        assert snapshot.backup_path.name.endswith(".bak") or ".bak." in snapshot.backup_path.name

    def test_snapshot_new_chapter_no_backup(self, project_empty: Path) -> None:
        """V0.30.6 B2：snapshot 不存在章节（新增场景）→ backup_path = None。"""
        manager = RollbackManager(project_root=project_empty)
        snapshot = manager.snapshot(chapter_number=10)

        assert snapshot.chapter_number == 10
        assert snapshot.backup_path is None  # 无备份（原文件不存在）

    def test_backup_content_matches_original(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：备份文件内容与原文件完全一致。"""
        manager = RollbackManager(project_root=project_with_chapter)
        original = (project_with_chapter / "正文" / "第005章.md").read_bytes()

        snapshot = manager.snapshot(chapter_number=5)
        backup_content = snapshot.backup_path.read_bytes()

        assert backup_content == original


# === Test 2: rollback 文件恢复 ===


class TestRollbackFile:
    """V0.30.6 B2：rollback 恢复章节文件。"""

    def test_rollback_existing_chapter_restores(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：rollback 已修改章节 → 恢复原内容。"""
        manager = RollbackManager(project_root=project_with_chapter)
        original = (project_with_chapter / "正文" / "第005章.md").read_text(encoding="utf-8")

        snapshot = manager.snapshot(chapter_number=5)

        # 模拟 LLM 写入新内容
        prose_path = project_with_chapter / "正文" / "第005章.md"
        prose_path.write_text(
            "# 第5章\n\nLLM 跑偏内容：林雷在火星跳舞。",
            encoding="utf-8",
        )

        # 触发回滚
        result = manager.rollback(snapshot)

        assert result.success is True
        assert result.restored_from_backup is True
        assert prose_path.read_text(encoding="utf-8") == original
        assert not snapshot.backup_path.exists()  # 备份被清理

    def test_rollback_new_chapter_deletes(self, project_empty: Path) -> None:
        """V0.30.6 B2：rollback 新增章节（无备份）→ 删除新文件。"""
        manager = RollbackManager(project_root=project_empty)
        snapshot = manager.snapshot(chapter_number=10)

        # 模拟 LLM 写入新章节
        prose_path = project_empty / "正文" / "第010章.md"
        prose_path.write_text(
            "# 第10章\n\n新章节内容（但触发了 critical 回滚）。",
            encoding="utf-8",
        )
        assert prose_path.exists()

        result = manager.rollback(snapshot)

        assert result.success is True
        assert result.restored_from_backup is False  # 没有备份 → 删除
        assert not prose_path.exists()

    def test_rollback_keeps_no_partial_state(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：rollback 不留半成品。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        prose_path = project_with_chapter / "正文" / "第005章.md"
        prose_path.write_text("CORRUPTED", encoding="utf-8")
        manager.rollback(snapshot)

        # 文件必须完全恢复，不能是中间态
        content = prose_path.read_text(encoding="utf-8")
        assert "CORRUPTED" not in content
        assert "原内容" in content


# === Test 3: state 回滚 ===


class TestRollbackState:
    """V0.30.6 B2：rollback 反向应用 state changes。"""

    def test_state_change_set_reverted(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：op=set → rollback 还原 before 值。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        # 模拟 pipeline 添加新角色
        manager.record_state_change(
            snapshot,
            StateChange(
                op="set",
                key="characters.萧炎",
                before=None,
                after={"description": "20岁配角"},
            ),
        )

        # 实际写入
        state_file = project_with_chapter / "_tracking-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["characters"]["萧炎"] = {"description": "20岁配角"}
        state_file.write_text(json.dumps(state), encoding="utf-8")

        # 回滚
        result = manager.rollback(snapshot)
        assert result.success is True

        state_after = json.loads(state_file.read_text(encoding="utf-8"))
        assert "萧炎" not in state_after["characters"]

    def test_state_change_modify_reverted(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：op=set 修改字段 → rollback 还原 before 值。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        # 修改已有角色
        manager.record_state_change(
            snapshot,
            StateChange(
                op="set",
                key="characters.林雷",
                before={"description": "18岁剑客"},
                after={"description": "200岁剑仙（错误）"},
            ),
        )

        # 实际修改
        state_file = project_with_chapter / "_tracking-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["characters"]["林雷"]["description"] = "200岁剑仙（错误）"
        state_file.write_text(json.dumps(state), encoding="utf-8")

        # 回滚
        manager.rollback(snapshot)

        state_after = json.loads(state_file.read_text(encoding="utf-8"))
        assert state_after["characters"]["林雷"]["description"] == "18岁剑客"

    def test_state_change_delete_reverted(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：op=delete → rollback 恢复 after 值（即恢复删除前的状态）。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        # 模拟删除已存在的伏笔
        state_file = project_with_chapter / "_tracking-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["foreshadowing"] = [{"id": "fs_001", "description": "神秘玉佩"}]
        state_file.write_text(json.dumps(state), encoding="utf-8")

        manager.record_state_change(
            snapshot,
            StateChange(
                op="delete",
                key="foreshadowing",
                before=None,
                after=[{"id": "fs_001", "description": "神秘玉佩"}],
            ),
        )

        # 删除
        state["foreshadowing"] = []
        state_file.write_text(json.dumps(state), encoding="utf-8")

        # 回滚 → 应恢复
        manager.rollback(snapshot)

        state_after = json.loads(state_file.read_text(encoding="utf-8"))
        assert state_after["foreshadowing"] == [{"id": "fs_001", "description": "神秘玉佩"}]

    def test_multiple_state_changes_all_reverted(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：多条 state changes 全部反向。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        # 记录 3 条 changes
        for i in range(3):
            manager.record_state_change(
                snapshot,
                StateChange(
                    op="set",
                    key=f"characters.char_{i}",
                    before=None,
                    after={"description": f"char {i}"},
                ),
            )

        state_file = project_with_chapter / "_tracking-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        for i in range(3):
            state["characters"][f"char_{i}"] = {"description": f"char {i}"}
        state_file.write_text(json.dumps(state), encoding="utf-8")

        result = manager.rollback(snapshot)
        assert result.state_changes_reverted == 3

        state_after = json.loads(state_file.read_text(encoding="utf-8"))
        for i in range(3):
            assert f"char_{i}" not in state_after["characters"]


# === Test 4: auto_rollback_on_critical 触发逻辑 ===


class TestAutoRollbackTrigger:
    """V0.30.6 B2：auto_rollback_on_critical() 触发逻辑。"""

    def test_verdict_fail_triggers_rollback(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：verdict=fail → 触发 rollback。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        # 修改文件模拟 LLM 写入
        (project_with_chapter / "正文" / "第005章.md").write_text("BAD", encoding="utf-8")

        result = auto_rollback_on_critical(manager, snapshot, "fail")
        assert result is not None
        assert result.success is True

    def test_verdict_pass_skips_rollback(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：verdict=pass → 不回滚（返回 None）。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        (project_with_chapter / "正文" / "第005章.md").write_text("GOOD", encoding="utf-8")

        result = auto_rollback_on_critical(manager, snapshot, "pass")
        assert result is None
        # 文件保持 GOOD
        assert (project_with_chapter / "正文" / "第005章.md").read_text() == "GOOD"

    def test_verdict_warn_skips_rollback(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：verdict=warn → 不回滚（warn 不算 critical）。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        result = auto_rollback_on_critical(manager, snapshot, "warn")
        assert result is None


# === Test 5: cleanup_old_backups ===


class TestCleanupOldBackups:
    """V0.30.6 B2：cleanup_old_backups 自动清理过期 .bak。"""

    def test_cleanup_removes_old_backups(self, tmp_path: Path) -> None:
        """V0.30.6 B2：超过 max_age_seconds 的 .bak 被删除。"""
        prose_dir = tmp_path / "正文"
        prose_dir.mkdir()

        # 创建 1 个新鲜 + 1 个 8 天前的 .bak
        ts_old = int(time.time()) - 8 * 24 * 3600  # 8 天前
        ts_new = int(time.time())

        old_backup = prose_dir / f"第1章.md{BACKUP_SUFFIX}.{ts_old}"
        new_backup = prose_dir / f"第1章.md{BACKUP_SUFFIX}.{ts_new}"
        old_backup.write_text("OLD", encoding="utf-8")
        new_backup.write_text("NEW", encoding="utf-8")

        deleted = RollbackManager.cleanup_old_backups(tmp_path)

        assert deleted == 1
        assert not old_backup.exists()
        assert new_backup.exists()

    def test_cleanup_no_old_backups(self, tmp_path: Path) -> None:
        """V0.30.6 B2：无过期 .bak → deleted=0。"""
        prose_dir = tmp_path / "正文"
        prose_dir.mkdir()

        ts_new = int(time.time())
        (prose_dir / f"ch.md{BACKUP_SUFFIX}.{ts_new}").write_text("X", encoding="utf-8")

        deleted = RollbackManager.cleanup_old_backups(tmp_path)
        assert deleted == 0

    def test_cleanup_no_prose_dir(self, tmp_path: Path) -> None:
        """V0.30.6 B2：无 正文/ 目录 → deleted=0（不报错）。"""
        deleted = RollbackManager.cleanup_old_backups(tmp_path)
        assert deleted == 0

    def test_cleanup_skips_invalid_filenames(self, tmp_path: Path) -> None:
        """V0.30.6 B2：无法解析的 .bak 文件名 → 跳过（不删、不报错）。"""
        prose_dir = tmp_path / "正文"
        prose_dir.mkdir()

        # 不符合 xxx.md.bak.{ts} 格式
        bad_backup = prose_dir / "corrupt.md.bak.notanumber"
        bad_backup.write_text("X", encoding="utf-8")

        deleted = RollbackManager.cleanup_old_backups(tmp_path)
        assert deleted == 0
        assert bad_backup.exists()  # 保留


# === Test 6: 集成到 write flow（snapshot + state change + rollback） ===


class TestWriteFlowIntegration:
    """V0.30.6 B2：完整 write flow 集成测试。"""

    def test_full_flow_critical_triggers_rollback(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：完整流程：snapshot → 写文件 → state change → review fail → rollback。

        模拟一次失败写作：内容写错 + 加了角色 + review verdict=fail。
        验证所有改动都被恢复。
        """
        manager = RollbackManager(project_root=project_with_chapter)
        original_prose = (project_with_chapter / "正文" / "第005章.md").read_text(encoding="utf-8")
        original_state = json.loads(
            (project_with_chapter / "_tracking-state.json").read_text(encoding="utf-8")
        )

        # 1. 写前快照
        snapshot = manager.snapshot(chapter_number=5)

        # 2. 模拟 LLM 写入错误内容 + state 更新
        (project_with_chapter / "正文" / "第005章.md").write_text(
            "BUG: 林雷已死却说话", encoding="utf-8"
        )
        manager.record_state_change(
            snapshot,
            StateChange(
                op="set",
                key="characters.萧炎",
                before=None,
                after={"description": "20岁配角"},
            ),
        )
        state_file = project_with_chapter / "_tracking-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["characters"]["萧炎"] = {"description": "20岁配角"}
        state_file.write_text(json.dumps(state), encoding="utf-8")

        # 3. 4-agent review → verdict=fail
        result = auto_rollback_on_critical(manager, snapshot, "fail")

        # 4. 验证：所有改动恢复
        assert result is not None
        assert result.success is True
        assert result.restored_from_backup is True
        assert result.state_changes_reverted == 1
        # 文件恢复
        assert (project_with_chapter / "正文" / "第005章.md").read_text(
            encoding="utf-8"
        ) == original_prose
        # state 恢复
        state_after = json.loads(state_file.read_text(encoding="utf-8"))
        assert state_after == original_state

    def test_full_flow_pass_keeps_changes(self, project_with_chapter: Path) -> None:
        """V0.30.6 B2：verdict=pass → 所有改动保留。"""
        manager = RollbackManager(project_root=project_with_chapter)
        snapshot = manager.snapshot(chapter_number=5)

        # 模拟成功写入
        (project_with_chapter / "正文" / "第005章.md").write_text(
            "NEW GOOD CONTENT", encoding="utf-8"
        )

        result = auto_rollback_on_critical(manager, snapshot, "pass")

        assert result is None
        # 文件保持新内容
        assert (project_with_chapter / "正文" / "第005章.md").read_text(
            encoding="utf-8"
        ) == "NEW GOOD CONTENT"
