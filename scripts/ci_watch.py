#!/usr/bin/env python3
"""CI 状态守护进程：把 workflow 状态写到 .novel2all/ci-status.json。

让 WorkBuddy / AI 助手能通过读文件获取最新 CI 状态（无需联网）。

用法：
    # 前台运行（开发调试）
    python scripts/ci_watch.py

    # 后台运行（推荐）
    python scripts/ci_watch.py &
    $!  # 拿 PID

    # 写入指定路径
    python scripts/ci_watch.py --output /tmp/ci-status.json

    # 间隔 60 秒
    python scripts/ci_watch.py --interval 60

输出文件格式（ci-status.json）：
    {
      "last_updated": "2026-09-12T09:30:00Z",
      "repo": "zenstory-ai/novel2all",
      "summary": {
        "total": 10,
        "success": 8,
        "failure": 1,
        "in_progress": 1,
        "queued": 0
      },
      "latest_failure": {...} or null,
      "latest_in_progress": {...} or null,
      "runs": [...]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
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


def fetch_runs(repo: str, limit: int = 20) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "novel2all-ci-watch/0.20",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/actions/runs"
    params = {"per_page": limit}
    resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def format_run(run: dict) -> dict:
    """提取关键字段。"""
    return {
        "id": run["id"],
        "name": run["name"],
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "branch": run["head_branch"],
        "commit_sha": run["head_sha"],
        "commit_msg": (run.get("head_commit", {}).get("message") or "").split("\n")[0][:80],
        "author": run.get("head_commit", {}).get("author", {}).get("name"),
        "event": run["event"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "duration_seconds": _calc_duration(run),
        "url": run["html_url"],
        "conclusion_icon": _icon(run),
    }


def _calc_duration(run: dict) -> int | None:
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
    if run["status"] == "completed":
        return {
            "success": "✅",
            "failure": "❌",
            "cancelled": "🚫",
            "skipped": "⏭️",
            "neutral": "⚪",
        }.get(run.get("conclusion") or "", "❓")
    return {"queued": "🟡", "in_progress": "⏳", "waiting": "⏸️"}.get(run["status"], "❓")


def summarize(runs: list[dict]) -> dict:
    """统计 + 找出最新失败 + 最新 in_progress。"""
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


def watch(repo: str, output: Path, interval: int) -> None:
    """轮询 + 写文件。"""
    print(f"[watch] repo={repo} interval={interval}s output={output}")
    print("[watch] 按 Ctrl+C 停止")

    # 优雅退出
    running = True

    def handle_sigint(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    while running:
        try:
            data = fetch_runs(repo)
            runs = data.get("workflow_runs", [])
            formatted = [format_run(r) for r in runs]
            s = summarize(formatted)

            status = {
                "last_updated": datetime.now(tz=UTC).isoformat(),
                "repo": repo,
                **s,
                "runs": formatted[:10],  # 只保留最近 10 条
            }

            output.parent.mkdir(parents=True, exist_ok=True)
            tmp = output.with_suffix(output.suffix + ".tmp")
            tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(output)  # atomic rename

            # 输出简报
            latest = formatted[0] if formatted else None
            if latest:
                print(
                    f"[{status['last_updated']}] "
                    f"{latest['conclusion_icon']} {latest['name']} "
                    f"({latest['branch']} @ {latest['commit_sha'][:7]}) "
                    f"| s={s['summary']['success']} f={s['summary']['failure']} "
                    f"q={s['summary']['queued']} i={s['summary']['in_progress']}"
                )

        except httpx.HTTPStatusError as e:
            print(
                f"[watch] HTTP error: {e.response.status_code} {e.response.text[:100]}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[watch] Error: {e}", file=sys.stderr)

        # 间隔（用 sleep 切片以快速响应 SIGINT）
        for _ in range(interval * 10):
            if not running:
                break
            time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description="novel2all CI watch 守护进程")
    parser.add_argument("--repo", help="仓库（owner/repo）")
    parser.add_argument(
        "--output", type=Path, default=Path(".novel2all/ci-status.json"), help="输出文件路径"
    )
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔（秒）")
    args = parser.parse_args()

    repo = args.repo or get_repo()

    # 如果 GITHUB_TOKEN 未设置，警告一下
    if not os.environ.get("GITHUB_TOKEN"):
        print("[watch] ⚠️  未设置 GITHUB_TOKEN，public 仓库可访问，private 仓库会 401")

    watch(repo, args.output, args.interval)


if __name__ == "__main__":
    main()
