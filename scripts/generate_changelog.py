"""V1.0 GA：自动从 git log 生成 CHANGELOG。

按 conventional commits 格式分组：
- feat: 新功能
- fix: 修复
- docs: 文档
- refactor: 重构
- perf: 性能
- test: 测试
- chore: 构建 / CI / 依赖

用法：
    python scripts/generate_changelog.py v1.0.0 CHANGELOG_AUTO.md
    # 不传 tag → 生成全 history
    # 不传输出 → 输出到 stdout
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Conventional commit 解析
COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|refactor|perf|test|chore|build|ci|style|revert)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?:"
    r"\s+(?P<subject>.+)$",
    re.IGNORECASE,
)

# 其它 commit（merge / revert / unknown）单独列出
OTHER_TYPES = {"merge", "revert"}


def run_git(args: list[str]) -> str:
    """运行 git 命令并返回 stdout。"""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def parse_commit(subject: str) -> tuple[str, str, bool, str]:
    """解析一个 commit subject。

    Returns:
        (type, scope, breaking, message)
        type: "feat" / "fix" / "docs" / ... / "other"
    """
    m = COMMIT_RE.match(subject)
    if not m:
        return ("other", "", False, subject)
    return (
        m.group("type").lower(),
        m.group("scope") or "",
        m.group("breaking") == "!",
        m.group("subject").strip(),
    )


def get_commits_since(tag: str | None) -> list[dict]:
    """获取自 tag 以来的所有 commits（按时间倒序）。

    如果 tag 为 None，获取最近 50 个 commit。
    """
    if tag:
        range_ = f"{tag}..HEAD"
    else:
        range_ = "HEAD~50..HEAD"

    try:
        log = run_git(["log", range_, "--no-merges", "--pretty=format:%H|%ai|%s"])
    except RuntimeError:
        # tag 不存在 → fallback 到全 history
        log = run_git(["log", "--no-merges", "--pretty=format:%H|%ai|%s"])

    commits = []
    for line in log.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        sha, date, subject = parts
        commit_type, scope, breaking, message = parse_commit(subject)
        commits.append(
            {
                "sha": sha[:7],
                "date": date[:10],  # YYYY-MM-DD
                "type": commit_type,
                "scope": scope,
                "breaking": breaking,
                "message": message,
            }
        )
    return commits


def get_previous_tag() -> str | None:
    """获取上一个 tag。"""
    try:
        out = run_git(["describe", "--tags", "--abbrev=0", "HEAD^"])
        return out.strip()
    except RuntimeError:
        return None


def group_commits(commits: list[dict]) -> dict[str, list[dict]]:
    """按 type 分组 commits。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in commits:
        groups[c["type"]].append(c)
    return dict(groups)


# 类型中文标签
TYPE_LABELS = {
    "feat": "🚀 新功能 (Features)",
    "fix": "🐛 修复 (Bug Fixes)",
    "perf": "⚡ 性能优化 (Performance)",
    "refactor": "♻️ 重构 (Refactoring)",
    "docs": "📚 文档 (Documentation)",
    "test": "✅ 测试 (Tests)",
    "build": "🏗️ 构建 (Build)",
    "ci": "🔧 CI/CD",
    "chore": "🔨 其他 (Chores)",
    "style": "💄 代码风格 (Style)",
    "other": "📦 其他 (Other)",
}


def format_commit(c: dict) -> str:
    """格式化单条 commit 为 markdown。"""
    scope = f"**{c['scope']}**: " if c["scope"] else ""
    breaking = " ⚠️ **BREAKING**" if c["breaking"] else ""
    return f"- {scope}{c['message']}{breaking} ({c['sha']})"


def generate_changelog(tag: str, since_tag: str | None) -> str:
    """生成 CHANGELOG markdown。"""
    commits = get_commits_since(since_tag)
    if not commits:
        return f"# {tag}\n\n_No commits since {since_tag or 'last tag'}._\n"

    groups = group_commits(commits)
    lines = [
        f"# {tag}",
        "",
        f"_发布日期：{datetime.now(tz=UTC).strftime('%Y-%m-%d')}_",
        "",
        f"_共 {len(commits)} 个 commit（自 {since_tag or '项目起始'}）_",
        "",
    ]

    # 按预定义顺序输出
    for type_key in [
        "feat",
        "fix",
        "perf",
        "refactor",
        "docs",
        "test",
        "build",
        "ci",
        "chore",
        "style",
        "other",
    ]:
        if type_key in groups:
            lines.append(f"## {TYPE_LABELS.get(type_key, type_key)}")
            lines.append("")
            for c in groups[type_key]:
                lines.append(format_commit(c))
            lines.append("")

    # Breaking changes 单独列出
    breaking = [c for c in commits if c["breaking"]]
    if breaking:
        lines.insert(3, f"## ⚠️ Breaking Changes ({len(breaking)})")
        lines.insert(4, "")
        for c in breaking:
            lines.insert(5, format_commit(c))
        lines.insert(6, "")

    return "\n".join(lines)


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "Unreleased"
    output = sys.argv[2] if len(sys.argv) > 2 else None

    since_tag = get_previous_tag()
    changelog = generate_changelog(tag, since_tag)

    if output:
        Path(output).write_text(changelog, encoding="utf-8")
        print(f"V1.0 GA: Changelog written to {output}")
        print(f"  - Tag: {tag}")
        print(f"  - Since: {since_tag}")
    else:
        sys.stdout.write(changelog)


if __name__ == "__main__":
    main()
