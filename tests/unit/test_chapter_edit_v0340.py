"""V0.34 章节编辑器测试。

覆盖：
1. POST /api/chapter/{n}/save 保存手动编辑内容
2. 同步 _tracking-state.json 的 last_updated_chapter
3. POST /api/chapter/{n}/expand 返回扩写元数据（form params for /api/write/stream/model）
4. /page/chapter-edit 端点返回 HTML
5. 错误路径：项目未初始化 / 章节不存在

不依赖真实 LLM（用 sync TestClient）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel2all.web.app import create_app

# === Fixtures ===


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """构造测试用项目目录（含 tracking state + 设定 + 已有第 1 章）。"""
    (tmp_path / "设定" / "世界观").mkdir(parents=True)
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    (tmp_path / "设定" / "文风.md").write_text("古风古韵", encoding="utf-8")
    from novel2all.core.memory import Tracker

    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(project_name="edit 测试", genre="玄幻", total_chapters_target=10)
    # 写第 1 章
    (tmp_path / "正文" / "第001章.md").write_text(
        "这是第 1 章原始内容。\n林雷在苍茫镇觉醒血脉。",
        encoding="utf-8",
    )
    (tmp_path / "大纲" / "细纲_第001章.md").write_text(
        "# 第 1 章细纲\n\n林雷觉醒血脉。",
        encoding="utf-8",
    )
    return tmp_path


# === Test 1: /page/chapter-edit 端点返回 HTML ===


def test_chapter_edit_page_endpoint_exists() -> None:
    """V0.34：/page/chapter-edit 端点返回 HTML 200。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/page/chapter-edit")
        assert response.status_code == 200
        # 返回 chapter_edit.html 模板
        assert "chapter-edit" in response.text or "章节编辑器" in response.text


# === Test 2: POST /api/chapter/{n}/save 保存内容 ===


def test_save_chapter_content_writes_file(project_root: Path) -> None:
    """V0.34：POST /api/chapter/1/save 写入 chapter_prose(1) 文件。"""
    app = create_app()
    new_content = "V0.34 手动编辑后的内容。\n林雷在苍茫镇获得了新能力。"

    with TestClient(app) as client:
        response = client.post(
            "/api/chapter/1/save",
            data={
                "content": new_content,
                "project_root": str(project_root).replace("\\", "/"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chapter"] == 1
        assert data["char_count"] == len(new_content)
        assert "第001章.md" in data["output_path"]

    # 验证文件被覆盖
    actual = (project_root / "正文" / "第001章.md").read_text(encoding="utf-8")
    assert actual == new_content


def test_save_chapter_creates_new_file(project_root: Path) -> None:
    """V0.34：保存到不存在的章节（新建）应创建文件。"""
    app = create_app()
    new_content = "新建章节内容。"

    with TestClient(app) as client:
        response = client.post(
            "/api/chapter/5/save",
            data={
                "content": new_content,
                "project_root": str(project_root).replace("\\", "/"),
            },
        )
        assert response.status_code == 200

    # 验证文件被创建
    chapter_file = project_root / "正文" / "第005章.md"
    assert chapter_file.exists()
    assert chapter_file.read_text(encoding="utf-8") == new_content


def test_save_chapter_updates_tracking_state(project_root: Path) -> None:
    """V0.34：保存章节时同步 _tracking-state.json 的 last_updated_chapter。"""
    from novel2all.core.memory import Tracker

    app = create_app()
    new_content = "新内容。"

    with TestClient(app) as client:
        # 保存第 3 章（之前 last_updated_chapter 应为 0）
        response = client.post(
            "/api/chapter/3/save",
            data={
                "content": new_content,
                "project_root": str(project_root).replace("\\", "/"),
            },
        )
        assert response.status_code == 200

    # 验证 tracking state 已更新
    tracker = Tracker(project_root / "_tracking-state.json")
    state = tracker.read()
    assert state.last_updated_chapter == 3


def test_save_chapter_does_not_lower_tracking_state(project_root: Path) -> None:
    """V0.34：保存较低章节号不应降低 last_updated_chapter（只增不减）。"""
    from novel2all.core.memory import Tracker

    # 先把 tracking state 设为 last_updated_chapter=5
    tracker = Tracker(project_root / "_tracking-state.json")
    state = tracker.read()
    state.last_updated_chapter = 5
    tracker.write(state)

    app = create_app()
    with TestClient(app) as client:
        # 保存第 1 章（比 5 小）
        response = client.post(
            "/api/chapter/1/save",
            data={
                "content": "旧章节",
                "project_root": str(project_root).replace("\\", "/"),
            },
        )
        assert response.status_code == 200

    # last_updated_chapter 应仍为 5（没被 1 覆盖）
    state = tracker.read()
    assert state.last_updated_chapter == 5


def test_save_chapter_returns_404_when_project_not_init(tmp_path: Path) -> None:
    """V0.34：项目未初始化时，save 端点返回 404。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/chapter/1/save",
            data={
                "content": "test",
                "project_root": str(tmp_path).replace("\\", "/"),
            },
        )
        assert response.status_code == 404
        assert "未初始化" in response.text or "not" in response.text.lower()


# === Test 3: POST /api/chapter/{n}/expand 返回扩写元数据 ===


def test_expand_chapter_returns_metadata(project_root: Path) -> None:
    """V0.34：POST /api/chapter/1/expand 返回 form_params for V0.32 resume。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/chapter/1/expand",
            data={
                "project_root": str(project_root).replace("\\", "/"),
                "skill": "story-long-write",
                "min_chars": "1000",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chapter"] == 1
        assert data["current_chars"] > 0
        assert data["expand_endpoint"] == "/api/write/stream/model"
        # form_params 应含 resume_from_chars = current_chars
        assert "resume_from_chars" in data["form_params"]
        assert data["form_params"]["resume_from_chars"] == data["current_chars"]
        assert data["form_params"]["chapter"] == 1


def test_expand_chapter_returns_404_when_chapter_not_exist(project_root: Path) -> None:
    """V0.34：expand 对不存在的章节返回 404（提示先写）。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/chapter/99/expand",  # 不存在
            data={"project_root": str(project_root).replace("\\", "/")},
        )
        assert response.status_code == 404


# === Test 4: GET /api/chapter/{n}/content 仍然工作（V0.30.3 已存在）===


def test_get_chapter_content_still_works(project_root: Path) -> None:
    """V0.34：get_chapter_content 端点保持向后兼容。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            f"/api/chapter/1/content?project_root={str(project_root).replace(chr(92), '/')}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chapter"] == 1
        assert "林雷" in data["content"]


# === Test 5: 模板渲染验证（V0.34 chapter_edit.html 存在 + 含 Alpine.js）===


def test_chapter_edit_template_has_alpine_state() -> None:
    """V0.34：chapter_edit.html 含 V0.34 7 态状态机 + textarea 编辑器。"""
    template_path = Path("src/novel2all/web/templates/chapter_edit.html")
    assert template_path.exists()

    content = template_path.read_text(encoding="utf-8")

    # Alpine.js 状态机
    assert "status: 'idle'" in content
    assert "loading" in content
    assert "loaded" in content
    assert "saving" in content
    assert "saved" in content
    assert "expanding" in content
    assert "error" in content

    # Alpine.js 字段
    assert "chapter" in content
    assert "content" in content
    assert "originalContent" in content
    assert "charCount" in content
    assert "modified" in content

    # 关键方法
    assert "loadChapter" in content
    assert "saveChapter" in content
    assert "expandChapter" in content
    assert "discardChanges" in content

    # 按钮
    assert "加载章节" in content
    assert "保存修改" in content
    assert "撤销修改" in content
    assert "AI 扩写" in content

    # textarea 编辑器
    assert "<textarea" in content
    assert 'x-model="content"' in content


def test_chapter_edit_template_calls_v034_endpoints() -> None:
    """V0.34：chapter_edit.html 调用 /api/chapter/{n}/save 和 /expand。"""
    template_path = Path("src/novel2all/web/templates/chapter_edit.html")
    content = template_path.read_text(encoding="utf-8")

    # 应含端点 URL
    assert "/api/chapter/" in content
    assert "/save" in content
    assert "/expand" in content
    assert "/content" in content


def test_index_template_links_to_chapter_edit() -> None:
    """V0.34：index.html 含 chapter-edit div（让首页能看到编辑器）。"""
    index_path = Path("src/novel2all/web/templates/index.html")
    content = index_path.read_text(encoding="utf-8")
    assert "/page/chapter-edit" in content
    assert 'id="chapter-edit"' in content
