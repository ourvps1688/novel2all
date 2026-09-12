"""ci_status.py 单元测试（用 httpx mock）。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

# 把 scripts 加进 path
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ci_status


@pytest.fixture
def sample_run() -> dict:
    """GitHub Actions run API 返回样本。"""
    return {
        "id": 12345,
        "name": "CI",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "a3f2b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
        "head_commit": {
            "message": "feat: add new feature",
            "author": {"name": "Alice"},
        },
        "event": "push",
        "created_at": "2026-09-12T09:00:00Z",
        "updated_at": "2026-09-12T09:02:30Z",
        "run_started_at": "2026-09-12T09:00:05Z",
        "html_url": "https://github.com/test/repo/actions/runs/12345",
    }


@pytest.fixture
def sample_failure_run() -> dict:
    """失败的 run。"""
    return {
        "id": 67890,
        "name": "CI",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": "feat/broken",
        "head_sha": "1111111111111111111111111111111111111111",
        "head_commit": {
            "message": "WIP",
            "author": {"name": "Bob"},
        },
        "event": "push",
        "created_at": "2026-09-12T10:00:00Z",
        "updated_at": "2026-09-12T10:03:00Z",
        "run_started_at": "2026-09-12T10:00:10Z",
        "html_url": "https://github.com/test/repo/actions/runs/67890",
    }


def test_calc_duration(sample_run: dict) -> None:
    """测试 duration 计算。"""
    dur = ci_status._calc_duration(sample_run)
    assert dur == 145  # 09:00:05 → 09:02:30 = 145 秒


def test_calc_duration_missing() -> None:
    """缺失字段返回 None。"""
    assert ci_status._calc_duration({}) is None


def test_icon_success(sample_run: dict) -> None:
    """成功状态图标。"""
    assert ci_status._icon(sample_run) == "✅"


def test_icon_failure(sample_failure_run: dict) -> None:
    """失败状态图标。"""
    assert ci_status._icon(sample_failure_run) == "❌"


def test_icon_in_progress() -> None:
    """运行中状态图标。"""
    run = {"status": "in_progress", "conclusion": None}
    assert ci_status._icon(run) == "⏳"


def test_icon_queued() -> None:
    """排队状态图标。"""
    run = {"status": "queued", "conclusion": None}
    assert ci_status._icon(run) == "🟡"


def test_format_run(sample_run: dict) -> None:
    """测试 run 格式化。"""
    formatted = ci_status.format_run(sample_run)
    assert formatted["id"] == 12345
    assert formatted["name"] == "CI"
    assert formatted["status"] == "completed"
    assert formatted["conclusion"] == "success"
    assert formatted["branch"] == "main"
    assert formatted["commit_sha"] == "a3f2b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
    assert formatted["commit_msg"] == "feat: add new feature"
    assert formatted["author"] == "Alice"
    assert formatted["duration_seconds"] == 145
    assert formatted["conclusion_icon"] == "✅"


def test_format_run_truncates_long_msg() -> None:
    """长 commit message 被截断到 80 字符。"""
    run = {
        "id": 1,
        "name": "CI",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "abc1234",
        "head_commit": {"message": "x" * 200, "author": {"name": "X"}},
        "event": "push",
        "created_at": "2026-09-12T09:00:00Z",
        "updated_at": "2026-09-12T09:00:30Z",
        "html_url": "https://example.com",
    }
    formatted = ci_status.format_run(run)
    assert len(formatted["commit_msg"]) == 80


def test_get_repo_default() -> None:
    """测试默认 repo。"""
    import os

    os.environ.pop("NOVEL2ALL_REPO", None)
    assert ci_status.get_repo() == "zenstory-ai/novel2all"


def test_get_repo_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试从环境变量读。"""
    monkeypatch.setenv("NOVEL2ALL_REPO", "my-org/my-repo")
    assert ci_status.get_repo() == "my-org/my-repo"


def test_fetch_runs_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    """401 时优雅退出。"""

    def mock_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(401, json={"message": "Bad credentials"}, request=request)

    monkeypatch.setattr(ci_status.httpx, "get", mock_get)

    with pytest.raises(SystemExit) as exc:
        ci_status.fetch_runs("any/repo")
    assert exc.value.code == 3


def test_fetch_runs_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """404 时优雅退出。"""

    def mock_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(404, json={"message": "Not Found"}, request=request)

    monkeypatch.setattr(ci_status.httpx, "get", mock_get)

    with pytest.raises(SystemExit) as exc:
        ci_status.fetch_runs("any/repo")
    assert exc.value.code == 4


def test_fetch_runs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功响应。"""

    def mock_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={"workflow_runs": [{"id": 1, "status": "completed"}]},
            request=request,
        )

    monkeypatch.setattr(ci_status.httpx, "get", mock_get)

    data = ci_status.fetch_runs("any/repo")
    assert "workflow_runs" in data
    assert len(data["workflow_runs"]) == 1


def test_fetch_runs_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """传 token 时 header 正确。"""
    captured_headers = {}

    def mock_get(url, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"workflow_runs": []}, request=request)

    monkeypatch.setattr(ci_status.httpx, "get", mock_get)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_xxx")

    ci_status.fetch_runs("any/repo")
    assert captured_headers.get("Authorization") == "Bearer ghp_test_xxx"

    monkeypatch.delenv("GITHUB_TOKEN")


def test_summarize_empty() -> None:
    """空列表 summary。"""
    s = ci_status.summarize([])
    assert s["summary"] == {
        "total": 0,
        "success": 0,
        "failure": 0,
        "in_progress": 0,
        "queued": 0,
        "cancelled": 0,
    }
    assert s["latest_failure"] is None
    assert s["latest_in_progress"] is None


def test_summarize_mixed() -> None:
    """混合状态的 summary。"""
    runs = [
        {"status": "completed", "conclusion": "success", "id": 1},
        {"status": "completed", "conclusion": "failure", "id": 2},
        {"status": "in_progress", "conclusion": None, "id": 3},
        {"status": "queued", "conclusion": None, "id": 4},
        {"status": "completed", "conclusion": "cancelled", "id": 5},
    ]
    s = ci_status.summarize(runs)
    assert s["summary"]["total"] == 5
    assert s["summary"]["success"] == 1
    assert s["summary"]["failure"] == 1
    assert s["summary"]["in_progress"] == 1
    assert s["summary"]["queued"] == 1
    assert s["summary"]["cancelled"] == 1
    assert s["latest_failure"]["id"] == 2
    assert s["latest_in_progress"]["id"] == 3


def test_summarize_latest_failure_first() -> None:
    """最新的失败在前面。"""
    runs = [
        {"status": "completed", "conclusion": "failure", "id": 99},
        {"status": "completed", "conclusion": "failure", "id": 50},
    ]
    s = ci_status.summarize(runs)
    assert s["latest_failure"]["id"] == 99  # 列表第一个就是最新的
