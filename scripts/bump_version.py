"""V1.0 GA：自动版本号管理。

读取 pyproject.toml 当前 version，递增指定分量（major/minor/patch），
写回 + 输出 git tag 命令。

用法：
    python scripts/bump_version.py patch         # 0.20.0 → 0.20.1
    python scripts/bump_version.py minor         # 0.20.0 → 0.21.0
    python scripts/bump_version.py major         # 0.20.0 → 1.0.0
    python scripts/bump_version.py minor --dry-run  # 只显示不写入
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

PYPROJECT_PATH = Path("pyproject.toml")
# V1.0.1：精确匹配 `[project]` 段下的 version（避免误匹配 `target-version`）
VERSION_RE = re.compile(
    r'^\[project\].*?^version\s*=\s*["\']([^"\']+)["\']',
    re.MULTILINE | re.DOTALL,
)


def get_current_version() -> str:
    """V1.0 GA：从 pyproject.toml 读 version。"""
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    m = VERSION_RE.search(text)
    if not m:
        raise ValueError("pyproject.toml 中找不到 version 字段")
    return m.group(1)


def bump(version: str, component: str) -> str:
    """V1.0 GA：递增版本分量。

    Args:
        version: 当前版本（如 "0.20.1"）
        component: "major" / "minor" / "patch"

    Returns:
        新版本号
    """
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}（需要 major.minor.patch）")

    major, minor, patch = (int(p) for p in parts)
    if component == "major":
        return f"{major + 1}.0.0"
    if component == "minor":
        return f"{major}.{minor + 1}.0"
    if component == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Invalid component: {component}")


def write_version(new_version: str) -> None:
    """V1.0 GA：写回 pyproject.toml（仅修改 [project] 段下 version）。"""
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    # V1.0.1：仅替换 [project] 段下的 version（避免误改 target-version）
    new_text = re.sub(
        r"(\[project\][^\[]*?version\s*=\s*)[\"'][^\"']+[\"']",
        rf'\1"{new_version}"',
        text,
        count=1,
        flags=re.DOTALL,
    )
    PYPROJECT_PATH.write_text(new_text, encoding="utf-8")


def git_commit(version: str) -> None:
    """V1.0 GA：commit 版本变更。"""
    subprocess.run(["git", "add", str(PYPROJECT_PATH)], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore(release): v{version}"],
        check=True,
    )


def git_tag(version: str) -> None:
    """V1.0 GA：创建 git tag。"""
    subprocess.run(["git", "tag", f"v{version}"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="V1.0 GA：版本号管理")
    parser.add_argument(
        "component",
        choices=["major", "minor", "patch"],
        help="要递增的版本分量",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示新版本，不写入",
    )
    args = parser.parse_args()

    current = get_current_version()
    new = bump(current, args.component)

    print(f"V1.0 GA: Current version: {current}")
    print(f"V1.0 GA: New version:     {new}")

    if args.dry_run:
        print("V1.0 GA: Dry run, not writing")
        print("\nNext steps:")
        print(f"  python scripts/bump_version.py {args.component}  # 实际写入")
        print("  git push origin main")
        print(f"  git push origin v{new}  # 触发 release workflow")
        return

    write_version(new)
    print(f"V1.0 GA: Written to {PYPROJECT_PATH}")

    git_commit(new)
    git_tag(new)
    print(f"V1.0 GA: Created tag v{new}")
    print("\nPush to trigger release:")
    print("  git push origin main")
    print(f"  git push origin v{new}")


if __name__ == "__main__":
    main()
