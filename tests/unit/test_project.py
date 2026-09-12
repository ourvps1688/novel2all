"""项目结构测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novel2all.core.project import ProjectStructure


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


def test_init(project_root: Path) -> None:
    """测试初始化目录结构。"""
    project = ProjectStructure(root=project_root)
    project.init()

    assert project.tracking_state_file.parent.exists()
    assert project.setup_md.parent.exists()
    assert project.worldview_dir.exists()
    assert project.characters_dir.exists()
    assert project.outline_dir.exists()
    assert project.prose_dir.exists()
    assert project.reference_lib_dir.exists()
    assert project.metadata_dir.exists()


def test_paths(project_root: Path) -> None:
    """测试路径生成。"""
    project = ProjectStructure(root=project_root)

    assert project.chapter_outline(5).name == "细纲_第005章.md"
    assert project.chapter_prose(5).name == "第005章.md"
    assert str(project.root) == str(project_root.resolve())


def test_exists(project_root: Path) -> None:
    """测试 exists。"""
    project = ProjectStructure(root=project_root)
    assert not project.exists()

    project.init()
    project.tracking_state_file.write_text("{}", encoding="utf-8")
    assert project.exists()
