"""Web API 端点单元测试。

覆盖 /api/chapter/{n}/content 等查询端点。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel2all.core.memory import Tracker
from novel2all.web.app import create_app


class TestChapterContent:
    """测试 /api/chapter/{chapter}/content 端点。"""

    @pytest.fixture
    def project_with_chapter(self, tmp_path: Path) -> Path:
        """创建带初始 tracking state + 章节正文的测试项目。"""
        tracker = Tracker(tmp_path / "_tracking-state.json")
        tracker.init(
            project_name="UI 测试",
            genre="玄幻",
            style_anchor="古风古韵",
            total_chapters_target=3,
        )
        # 写章节正文
        prose_dir = tmp_path / "正文"
        prose_dir.mkdir()
        (prose_dir / "第001章.md").write_text(
            "# 第 1 章：测试\n\n林雷觉醒血脉，苍茫镇为之震动。\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_get_chapter_content_success(self, project_with_chapter: Path) -> None:
        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/chapter/1/content",
            params={"project_root": str(project_with_chapter)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter"] == 1
        assert "林雷觉醒血脉" in data["content"]
        assert data["char_count"] > 0
        assert data["first_line"].startswith("# 第 1 章")

    def test_get_chapter_content_not_found(self, project_with_chapter: Path) -> None:
        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/chapter/999/content",
            params={"project_root": str(project_with_chapter)},
        )
        assert resp.status_code == 404

    def test_get_chapter_content_project_not_initialized(self, tmp_path: Path) -> None:
        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/chapter/1/content",
            params={"project_root": str(tmp_path)},
        )
        assert resp.status_code == 404


class TestExistingEndpoints:
    """回归测试：确保前面端点没被破坏。"""

    def test_status(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/status", params={"project_root": "."})
        assert resp.status_code == 200

    def test_skills(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_roles(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_outlines(self, tmp_path: Path) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/outlines", params={"project_root": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json() == []
