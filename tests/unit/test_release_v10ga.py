"""V1.0 GA Day 8-10：release 脚本测试（changelog + version bump）。"""

from __future__ import annotations

from pathlib import Path

import pytest

# === Test 1: generate_changelog ===


class TestGenerateChangelog:
    """V1.0 GA：CHANGELOG 自动生成。"""

    def test_parse_commit_feat(self) -> None:
        """V1.0 GA：解析 feat() commit。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import parse_commit

        ctype, scope, breaking, msg = parse_commit("feat(B1): add 4-agent review")
        assert ctype == "feat"
        assert scope == "B1"
        assert breaking is False
        assert msg == "add 4-agent review"

    def test_parse_commit_breaking(self) -> None:
        """V1.0 GA：解析 breaking change（feat! 前缀）。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import parse_commit

        ctype, scope, breaking, msg = parse_commit("feat(api)!: rename endpoint")
        assert ctype == "feat"
        assert scope == "api"
        assert breaking is True
        assert msg == "rename endpoint"

    def test_parse_commit_no_scope(self) -> None:
        """V1.0 GA：解析无 scope 的 commit。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import parse_commit

        ctype, scope, breaking, _msg = parse_commit("fix: typo in README")
        assert ctype == "fix"
        assert scope == ""
        assert breaking is False

    def test_parse_commit_unknown(self) -> None:
        """V1.0 GA：非 conventional commit → type=other。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import parse_commit

        ctype, _scope, _breaking, _msg = parse_commit("Random commit message")
        assert ctype == "other"

    def test_format_commit_with_scope(self) -> None:
        """V1.0 GA：format_commit 加粗 scope。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import format_commit

        c = {
            "sha": "abc1234",
            "type": "feat",
            "scope": "B1",
            "breaking": False,
            "message": "add review",
        }
        result = format_commit(c)
        assert "**B1**" in result
        assert "add review" in result
        assert "abc1234" in result

    def test_format_commit_breaking(self) -> None:
        """V1.0 GA：breaking change 加 ⚠️ 标记。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import format_commit

        c = {
            "sha": "def5678",
            "type": "feat",
            "scope": "api",
            "breaking": True,
            "message": "rename endpoint",
        }
        result = format_commit(c)
        assert "⚠️ **BREAKING**" in result

    def test_group_commits_by_type(self) -> None:
        """V1.0 GA：按 type 分组。"""
        import sys

        sys.path.insert(0, "scripts")
        from generate_changelog import group_commits

        commits = [
            {"sha": "a", "type": "feat", "scope": "", "breaking": False, "message": "feat1"},
            {"sha": "b", "type": "feat", "scope": "", "breaking": False, "message": "feat2"},
            {"sha": "c", "type": "fix", "scope": "", "breaking": False, "message": "fix1"},
            {"sha": "d", "type": "docs", "scope": "", "breaking": False, "message": "docs1"},
        ]
        groups = group_commits(commits)
        assert len(groups["feat"]) == 2
        assert len(groups["fix"]) == 1
        assert len(groups["docs"]) == 1


# === Test 2: bump_version ===


class TestBumpVersion:
    """V1.0 GA：版本号管理。"""

    def test_bump_patch(self) -> None:
        """V1.0 GA：patch 递增。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import bump

        assert bump("0.20.0", "patch") == "0.20.1"
        assert bump("1.9.9", "patch") == "1.9.10"

    def test_bump_minor(self) -> None:
        """V1.0 GA：minor 递增（patch 重置为 0）。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import bump

        assert bump("0.20.0", "minor") == "0.21.0"
        assert bump("0.99.99", "minor") == "0.100.0"

    def test_bump_major(self) -> None:
        """V1.0 GA：major 递增（minor+patch 重置为 0）。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import bump

        assert bump("0.20.0", "major") == "1.0.0"
        assert bump("1.2.3", "major") == "2.0.0"

    def test_bump_invalid_component(self) -> None:
        """V1.0 GA：无效 component → ValueError。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import bump

        with pytest.raises(ValueError):
            bump("0.20.0", "invalid")

    def test_bump_invalid_format(self) -> None:
        """V1.0 GA：无效 version 格式 → ValueError。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import bump

        with pytest.raises(ValueError):
            bump("invalid", "patch")
        with pytest.raises(ValueError):
            bump("1.0", "patch")  # 只有 2 段

    def test_get_current_version(self, tmp_path: Path) -> None:
        """V1.0 GA：从 pyproject.toml 读 version。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import PYPROJECT_PATH, get_current_version

        # Mock pyproject.toml
        original = PYPROJECT_PATH.read_text(encoding="utf-8")
        try:
            PYPROJECT_PATH.write_text(
                '[project]\nname = "test"\nversion = "1.2.3"\n',
                encoding="utf-8",
            )
            assert get_current_version() == "1.2.3"
        finally:
            PYPROJECT_PATH.write_text(original, encoding="utf-8")

    def test_write_version(self, tmp_path: Path) -> None:
        """V1.0 GA：写回 pyproject.toml。"""
        import sys

        sys.path.insert(0, "scripts")
        from bump_version import PYPROJECT_PATH, get_current_version, write_version

        original = PYPROJECT_PATH.read_text(encoding="utf-8")
        try:
            PYPROJECT_PATH.write_text(
                '[project]\nname = "test"\nversion = "1.0.0"\n',
                encoding="utf-8",
            )
            write_version("2.0.0")
            assert get_current_version() == "2.0.0"
        finally:
            PYPROJECT_PATH.write_text(original, encoding="utf-8")


# === Test 3: release.yml workflow 静态检查 ===


class TestReleaseWorkflow:
    """V1.0 GA：.github/workflows/release.yml 完整性。"""

    def test_release_workflow_exists(self) -> None:
        """V1.0 GA：release.yml 存在。"""
        path = Path(".github/workflows/release.yml")
        assert path.exists()

    def test_release_workflow_has_3_jobs(self) -> None:
        """V1.0 GA：3 个 jobs（pypi / docker / github-release）。"""
        path = Path(".github/workflows/release.yml")
        text = path.read_text(encoding="utf-8")
        assert "pypi:" in text
        assert "docker:" in text
        assert "github-release:" in text

    def test_release_workflow_multi_arch(self) -> None:
        """V1.0 GA：multi-arch matrix（amd64 + arm64）。"""
        path = Path(".github/workflows/release.yml")
        text = path.read_text(encoding="utf-8")
        assert "matrix:" in text
        assert "linux/amd64" in text
        assert "linux/arm64" in text

    def test_release_workflow_uses_pypi_trusted_publishing(self) -> None:
        """V1.0 GA：使用 PyPI trusted publishing（无需 API token）。"""
        path = Path(".github/workflows/release.yml")
        text = path.read_text(encoding="utf-8")
        assert "id-token: write" in text
        assert "pypa/gh-action-pypi-publish" in text

    def test_release_workflow_changelog_generation(self) -> None:
        """V1.0 GA：调用 generate_changelog.py 自动生成 release notes。"""
        path = Path(".github/workflows/release.yml")
        text = path.read_text(encoding="utf-8")
        assert "generate_changelog.py" in text


# === Test 4: scripts 目录结构 ===


class TestScriptsStructure:
    """V1.0 GA：scripts/ 目录完整性。"""

    def test_benchmark_scripts_exist(self) -> None:
        """V1.0 GA：3 个 benchmark 脚本。"""
        assert Path("scripts/benchmark_cache.py").exists()
        assert Path("scripts/benchmark_cache_rtt.py").exists()
        assert Path("scripts/benchmark_prompt_cache.py").exists()

    def test_release_scripts_exist(self) -> None:
        """V1.0 GA：2 个 release 脚本。"""
        assert Path("scripts/generate_changelog.py").exists()
        assert Path("scripts/bump_version.py").exists()
