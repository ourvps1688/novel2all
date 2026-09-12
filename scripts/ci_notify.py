#!/usr/bin/env python3
"""CI 失败通知器：发现新失败时，写到 .novel2all/ci-alerts.json。

AI 助手可以读这个文件来"主动获知"失败。

用法：
    python scripts/ci_notify.py

    # 配合 ci_watch.py 使用：
    # 在 ci_watch.py 的循环里，每 60 秒调一次 ci_notify.py

    # 手动触发：
    python scripts/ci_notify.py --last-state .novel2all/ci-status.json

输出：.novel2all/ci-alerts.json（未变化的失败不重复写）
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

# 自动从 .env 加载（如果有 python-dotenv）
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

import httpx


def get_repo() -> str:
    return os.environ.get("NOVEL2ALL_REPO", "zenstory-ai/novel2all")


def fetch_failures(repo: str) -> list[dict]:
    """获取最近 24 小时内失败 run。"""
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "novel2all-ci-notify/0.20",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/actions/runs"
    params = {"status": "completed", "conclusion": "failure", "per_page": 5}
    resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
    resp.raise_for_status()
    return resp.json().get("workflow_runs", [])


def format_failure(run: dict) -> dict:
    return {
        "id": run["id"],
        "name": run["name"],
        "branch": run["head_branch"],
        "commit_sha": run["head_sha"],
        "commit_msg": (run.get("head_commit", {}).get("message") or "").split("\n")[0][:80],
        "author": run.get("head_commit", {}).get("author", {}).get("name"),
        "failed_at": run["updated_at"],
        "url": run["html_url"],
        "logs_url": run["html_url"] + "#step-by-step",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="novel2all CI 失败通知器")
    parser.add_argument("--repo", help="仓库")
    parser.add_argument("--output", type=Path, default=Path(".novel2all/ci-alerts.json"))
    args = parser.parse_args()

    repo = args.repo or get_repo()
    failures = fetch_failures(repo)

    # 读已有 alerts（去重）
    existing_ids = set()
    if args.output.exists():
        try:
            existing = json.loads(args.output.read_text(encoding="utf-8"))
            existing_ids = {f["id"] for f in existing.get("failures", [])}
        except (OSError, json.JSONDecodeError):
            pass

    # 新失败
    new_failures = []
    for run in failures:
        f = format_failure(run)
        if f["id"] not in existing_ids:
            new_failures.append(f)

    # 写文件
    output = {
        "last_checked": datetime.now(tz=UTC).isoformat(),
        "repo": repo,
        "failures": [format_failure(r) for r in failures],
        "new_count": len(new_failures),
        "new_failures": new_failures,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(args.output)

    if new_failures:
        print(f"[notify] 🚨 {len(new_failures)} 新失败")
        for f in new_failures:
            print(f"  ❌ Run #{f['id']} {f['name']} ({f['branch']} @ {f['commit_sha'][:7]})")
            print(f"     {f['url']}")
    else:
        print(f"[notify] ✅ 没有新失败（{len(failures)} 历史失败）")


if __name__ == "__main__":
    main()
