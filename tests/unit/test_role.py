"""Role 注册测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novel2all.core.role import RoleRegistry


@pytest.fixture
def roles_dir(tmp_path: Path) -> Path:
    """创建临时 roles 目录。"""
    roles = tmp_path / "roles"
    roles.mkdir()

    for name in ["test-role-1", "test-role-2"]:
        (roles / f"{name}.md").write_text(
            f"""---
name: {name}
description: 这是 {name}
model: claude-sonnet-4-20250514
---

# {name}

系统提示正文。
""",
            encoding="utf-8",
        )

    return roles


def test_discover(roles_dir: Path) -> None:
    """测试发现 role。"""
    registry = RoleRegistry(roles_dir)
    roles = registry.discover()
    assert len(roles) == 2
    names = {r.name for r in roles}
    assert names == {"test-role-1", "test-role-2"}


def test_get(roles_dir: Path) -> None:
    """测试按名获取。"""
    registry = RoleRegistry(roles_dir)
    registry.discover()
    role = registry.get("test-role-1")
    assert role is not None
    assert role.description == "这是 test-role-1"
    assert role.preferred_model == "claude-sonnet-4-20250514"
    assert "系统提示正文" in role.system_prompt


def test_role_no_frontmatter(tmp_path: Path) -> None:
    """测试无 frontmatter 的 role。"""
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "plain.md").write_text(
        "# plain\n\n纯文本 role。",
        encoding="utf-8",
    )
    registry = RoleRegistry(roles)
    registry.discover()
    role = registry.get("plain")
    assert role is not None
    assert role.description == ""
    assert "纯文本 role" in role.system_prompt
