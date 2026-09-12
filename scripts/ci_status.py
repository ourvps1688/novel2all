#!/usr/bin/env python3
"""列出 novel2all GitHub Actions 的最新 workflow 状态。

让 WorkBuddy / 任何 AI 助手能自动获取 CI 状态。

用法：
    # 一次性查询
    export GITHUB_TOKEN=ghp_xxx        # private 仓库必需
    python scripts/ci_status.py

    # 指定仓库
    python scripts/ci_status.py --repo zenstory-ai/novel2all

    # 轮询模式（自动刷新）
    python scripts/ci_status.py --watch --interval 30

    # 输出 JSON（让 AI 助手解析）
    python scripts/ci_status.py --json | python -c "import json, sys; print(json.dumps(json.load(sys.stdin), indent=2))"

    # 单次 run 详情
    python scripts/ci_status.py --run-id 12345

环境变量：
    GITHUB_TOKEN     Personal Access Token（private 仓库必需）
    NOVEL2ALL_REPO   仓库名（默认 zenstory-ai/novel2all）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
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
    """获取目标仓库，优先级：参数 > 环境变量 > 默认值。"""
    return os.environ.get("NOVEL2ALL_REPO", "zenstory-ai/novel2all")


def fetch_runs(repo: str, limit: int = 10, run_id: int | None = None) -> dict:
    """调 GitHub API 获取 workflow runs。"""
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "novel2all-ci-status/0.20",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if run_id:
        url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    else:
        url = f"https://api.github.com/repos/{repo}/actions/runs"

    params = {"per_page": limit} if not run_id else {}
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
    except httpx.HTTPError as e:
        print(f"[ERR] HTTP error: {e}", file=sys.stderr)
        sys.exit(2)

    if resp.status_code == 401:
        print("[ERR] 401 Unauthorized — 需要 GITHUB_TOKEN（private 仓库）", file=sys.stderr)
        sys.exit(3)
    if resp.status_code == 404:
        print(f"[ERR] 404 Not Found — 仓库 {repo} 不存在或 workflow 未启用", file=sys.stderr)
        sys.exit(4)

    resp.raise_for_status()
    return resp.json()


def format_run(run: dict) -> dict:
    """提取关键字段供 AI 助手解析。"""
    return {
        "id": run["id"],
        "name": run["name"],
        "status": run["status"],  # queued / in_progress / completed / waiting / requested
        "conclusion": run.get("conclusion"),  # success / failure / cancelled / skipped / neutral
        "branch": run["head_branch"],
        "commit_sha": run["head_sha"],
        "commit_msg": (run.get("head_commit", {}).get("message") or "").split("\n")[0][:80],
        "author": run.get("head_commit", {}).get("author", {}).get("name"),
        "event": run["event"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "run_started_at": run.get("run_started_at"),
        "duration_seconds": _calc_duration(run),
        "url": run["html_url"],
        "conclusion_icon": _icon(run),
    }


def _calc_duration(run: dict) -> int | None:
    """计算 run 耗时（秒）。"""
    started = run.get("run_started_at")
    updated = run.get("updated_at")
    if not started or not updated:
        return None
    try:
        # Python 3.11+ fromisoformat 直接支持 "Z" 后缀
        s = datetime.fromisoformat(started)
        u = datetime.fromisoformat(updated)
        return int((u - s).total_seconds())
    except (ValueError, TypeError):
        return None


def _icon(run: dict) -> str:
    """返回状态图标。"""
    if run["status"] == "completed":
        return {
            "success": "✅",
            "failure": "❌",
            "cancelled": "🚫",
            "skipped": "⏭️",
            "neutral": "⚪",
        }.get(run.get("conclusion") or "", "❓")
    return {"queued": "🟡", "in_progress": "⏳", "waiting": "⏸️"}.get(run["status"], "❓")


def print_table(runs: list[dict]) -> None:
    """打印表格。"""
    print(
        f"\n{'STATUS':<8} {'NAME':<28} {'BRANCH':<15} {'COMMIT':<9} {'DURATION':<10} {'WHEN':<20}"
    )
    print("─" * 95)
    for r in runs:
        d = format_run(r)
        dur = f"{d['duration_seconds']}s" if d["duration_seconds"] else "-"
        when = d["created_at"][:19].replace("T", " ")
        print(
            f"{d['conclusion_icon']:<8} {d['name']:<28} {d['branch'] < 15} "
            f"{d['commit_sha'][:7]:<9} {dur:<10} {when:<20}"
        )


def summarize(runs: list[dict]) -> dict:
    """统计 runs + 找最新失败 + 最新 in_progress。"""
    summary = {
        "total": len(runs),
        "success": 0,
        "failure": 0,
        "in_progress": 0,
        "queued": 0,
        "cancelled": 0,
    }
    latest_failure = None
    latest_in_progress = None
    for r in runs:
        status = r["status"]
        conclusion = r.get("conclusion")
        if status == "completed":
            if conclusion == "success":
                summary["success"] += 1
            elif conclusion == "failure":
                summary["failure"] += 1
                if latest_failure is None:
                    latest_failure = r
            elif conclusion == "cancelled":
                summary["cancelled"] += 1
        elif status == "in_progress":
            summary["in_progress"] += 1
            if latest_in_progress is None:
                latest_in_progress = r
        elif status == "queued":
            summary["queued"] += 1
    return {
        "summary": summary,
        "latest_failure": latest_failure,
        "latest_in_progress": latest_in_progress,
    }


def print_detail(run: dict) -> None:
    """打印单次 run 详情。"""
    d = format_run(run)
    print(f"\n{'=' * 70}")
    print(f"  Run #{d['id']} — {d['name']}")
    print(f"{'=' * 70}")
    print(f"  Status      : {d['conclusion_icon']} {d['status']} / {d['conclusion']}")
    print(f"  Branch      : {d['branch']}")
    print(f"  Commit      : {d['commit_sha'][:7]} — {d['commit_msg']}")
    print(f"  Author      : {d['author']}")
    print(f"  Event       : {d['event']}")
    print(f"  Created     : {d['created_at']}")
    print(f"  Updated     : {d['updated_at']}")
    if d["duration_seconds"]:
        print(f"  Duration    : {d['duration_seconds']}s")
    print(f"  URL         : {d['url']}")


def watch_mode(repo: str, interval: int) -> None:
    """轮询模式：每 N 秒刷新。"""
    print(f"[watch] 轮询 {repo}，每 {interval}s 刷新一次，Ctrl+C 退出")
    try:
        while True:
            # 清屏（Windows + Unix）
            os.system("cls" if os.name == "nt" else "clear")
            data = fetch_runs(repo, limit=5)
            runs = data.get("workflow_runs", [])
            print_table(runs)
            print(f"\n[watch] 下次刷新：{interval}s 后")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[watch] 已停止")


def main() -> None:
    parser = argparse.ArgumentParser(description="novel2all CI 状态查询")
    parser.add_argument("--repo", help="仓库（owner/repo）")
    parser.add_argument("--limit", type=int, default=10, help="查询数量")
    parser.add_argument("--run-id", type=int, help="单次 run 详情")
    parser.add_argument("--watch", action="store_true", help="轮询模式")
    parser.add_argument("--interval", type=int, default=30, help="轮询间隔（秒）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（AI 友好）")
    args = parser.parse_args()

    repo = args.repo or get_repo()

    if args.run_id:
        data = fetch_runs(repo, run_id=args.run_id)
        if args.json:
            print(json.dumps(format_run(data), indent=2, ensure_ascii=False))
        else:
            print_detail(data)
        return

    data = fetch_runs(repo, limit=args.limit)
    runs = data.get("workflow_runs", [])

    if args.json:
        result = {
            "repo": repo,
            "total_count": data.get("total_count", len(runs)),
            "runs": [format_run(r) for r in runs],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.watch:
        watch_mode(repo, args.interval)
    else:
        print(f"\n📦 novel2all CI 状态 — {repo}")
        print_table(runs)
        print("\n[hint] 加 --watch 轮询；加 --json 让 AI 助手解析")


if __name__ == "__main__":
    main()
