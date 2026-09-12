"""Skill 注册测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novel2all.core.skill import SkillRegistry


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """创建临时 skills 目录。"""
    skills = tmp_path / "skills"
    skills.mkdir()

    # 创建 2 个测试 skill
    for name in ["test-skill-1", "test-skill-2"]:
        skill_dir = skills / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"""---
name: {name}
description: 这是 {name}
---

# {name}

正文内容。
""",
            encoding="utf-8",
        )

    return skills


def test_discover(skills_dir: Path) -> None:
    """测试发现 skill。"""
    registry = SkillRegistry(skills_dir)
    skills = registry.discover()
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"test-skill-1", "test-skill-2"}


def test_get(skills_dir: Path) -> None:
    """测试按名获取。"""
    registry = SkillRegistry(skills_dir)
    registry.discover()
    skill = registry.get("test-skill-1")
    assert skill is not None
    assert skill.description == "这是 test-skill-1"
    assert "正文内容" in skill.content


def test_get_nonexistent(skills_dir: Path) -> None:
    """测试获取不存在的 skill。"""
    registry = SkillRegistry(skills_dir)
    registry.discover()
    assert registry.get("nonexistent") is None


def test_user_invocable_default(skills_dir: Path) -> None:
    """测试 user-invocable 默认 True。"""
    registry = SkillRegistry(skills_dir)
    registry.discover()
    skill = registry.get("test-skill-1")
    assert skill is not None
    assert skill.user_invocable is True
    assert skill.model_invocable is True


def test_user_invocable_false(tmp_path: Path) -> None:
    """测试 user-invocable: false。"""
    skills = tmp_path / "skills"
    skills.mkdir()
    skill_dir = skills / "internal-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: internal-skill
description: 内部 skill
user-invocable: false
---

正文。
""",
        encoding="utf-8",
    )

    registry = SkillRegistry(skills)
    registry.discover()
    skill = registry.get("internal-skill")
    assert skill is not None
    assert skill.user_invocable is False


def test_discover_empty_dir(tmp_path: Path) -> None:
    """测试空目录。"""
    skills = tmp_path / "skills"
    skills.mkdir()
    registry = SkillRegistry(skills)
    skills_list = registry.discover()
    assert skills_list == []


def test_discover_no_dir(tmp_path: Path) -> None:
    """测试不存在的目录。"""
    registry = SkillRegistry(tmp_path / "nonexistent")
    skills_list = registry.discover()
    assert skills_list == []
