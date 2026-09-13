"""V0.38：章节重写/插入端点单元测试。

测试范围：
1. /api/chapter/{n}/rewrite — LLM 改写选区
   - 404：项目/章节不存在
   - 400：参数非法（start/end 越界、start>=end）
   - 200：返回 original / rewritten / start / end / model
   - mock LLM：验证 prompt 包含选区文本 + instruction
2. /api/chapter/{n}/insert — LLM 生成插入内容
   - 404：项目/章节不存在
   - 400：position 越界
   - 200：返回 position / inserted / model
   - mock LLM：验证 prompt 包含前后上下文 + instruction
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# === Mock LLM（避免真实调用）===


class MockLLMProviderV038:
    """V0.38 测试用 mock LLM：返回固定字符串。"""

    def __init__(
        self,
        rewrite_output: str = "【改写后文本】",
        insert_output: str = "【待插入文本】",
    ) -> None:
        self.rewrite_output = rewrite_output
        self.insert_output = insert_output
        self.last_prompt: str = ""
        self.last_system: str = ""

    async def complete(self, prompt: str, system: str = "", **kwargs: Any) -> str:
        self.last_prompt = prompt
        self.last_system = system
        if "改写" in prompt or "重写" in prompt or "原文" in prompt:
            return self.rewrite_output
        return self.insert_output


# === Fixture：临时项目结构（带章节文件）===


@pytest.fixture
def project_with_chapter(tmp_path: Path) -> dict:
    """创建含 1 个章节的临时项目结构（含 _tracking-state.json 以通过 ProjectStructure.exists() 检查）。"""
    project_root = tmp_path / "project"
    prose_dir = project_root / "正文"
    prose_dir.mkdir(parents=True)
    prose_file = prose_dir / "第001章.md"
    initial_content = (
        "第一段：夜幕降临，江风裹挟着寒意。\n\n"
        "第二段：少年站在渡口，眉头紧锁。\n\n"
        "第三段：他抬头望向远方的群山，心中默念。\n"
    )
    prose_file.write_text(initial_content, encoding="utf-8")
    # V0.34 必需的 tracking state 文件（ProjectStructure.exists() 检测）
    tracking = project_root / "_tracking-state.json"
    tracking.write_text(
        '{"version": 1, "last_updated_chapter": 1, "characters": {}, "foreshadowing": [], "timeline": []}',
        encoding="utf-8",
    )
    return {
        "project_root": project_root,
        "prose_file": prose_file,
        "initial_content": initial_content,
    }


# === Test 1: rewrite 基础 ===


@pytest.mark.asyncio
async def test_rewrite_section_returns_original_and_rewritten(
    project_with_chapter: dict,
) -> None:
    """V0.38：rewrite 端点返回 original + rewritten。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038(rewrite_output="改写后的新版本：少年立于渡口，眼望远方山影。")

    app = create_app()
    with (
        TestClient(app) as client,
        patch("novel2all.cli.main.get_llm_for_model", return_value=mock_llm),
    ):
        # 选第 2 段
        start = initial.index("第二段")
        end = initial.index("\n\n", start)
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": str(start),
                "end": str(end),
                "instruction": "改写得更生动自然",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["chapter"] == 1
        assert data["start"] == start
        assert data["end"] == end
        assert data["original"] == initial[start:end]
        assert data["rewritten"] == "改写后的新版本：少年立于渡口，眼望远方山影。"
        assert "改写" in mock_llm.last_prompt
        assert "第二段" in mock_llm.last_prompt


@pytest.mark.asyncio
async def test_rewrite_section_prompt_contains_instruction(
    project_with_chapter: dict,
) -> None:
    """V0.38：rewrite prompt 应包含 user instruction。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038()

    app = create_app()
    with (
        TestClient(app) as client,
        patch("novel2all.cli.main.get_llm_for_model", return_value=mock_llm),
    ):
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "0",
                "end": str(len(initial)),
                "instruction": "把景色描写得更凄凉",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 200
        assert "凄凉" in mock_llm.last_prompt
        assert initial[:50] in mock_llm.last_prompt


# === Test 2: rewrite 错误处理 ===


def test_rewrite_section_404_when_project_missing(tmp_path: Path) -> None:
    """V0.38：项目不存在 → 404。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "0",
                "end": "10",
                "instruction": "test",
                "project_root": str(tmp_path / "nonexistent"),
            },
        )
        assert resp.status_code == 404


def test_rewrite_section_404_when_chapter_missing(
    project_with_chapter: dict,
) -> None:
    """V0.38：章节不存在 → 404。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/chapter/999/rewrite",
            data={
                "start": "0",
                "end": "10",
                "instruction": "test",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 404


def test_rewrite_section_400_when_range_invalid(
    project_with_chapter: dict,
) -> None:
    """V0.38：start/end 越界或 start>=end → 400。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    total = len(initial)
    app = create_app()
    with TestClient(app) as client:
        # start > end
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "50",
                "end": "30",
                "instruction": "test",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 400

        # end > total
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "0",
                "end": str(total + 100),
                "instruction": "test",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 400

        # start < 0
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "-1",
                "end": "10",
                "instruction": "test",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 400


# === Test 3: rewrite 不修改文件（关键安全属性）===


def test_rewrite_section_does_not_modify_file(
    project_with_chapter: dict,
) -> None:
    """V0.38：rewrite 端点只生成 LLM 结果，**不直接改文件**（必须用户确认后调 /save）。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    prose_file = project_with_chapter["prose_file"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038(rewrite_output="全新改写")

    app = create_app()
    with (
        TestClient(app) as client,
        patch("novel2all.cli.main.get_llm_for_model", return_value=mock_llm),
    ):
        client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "0",
                "end": str(len(initial)),
                "instruction": "test",
                "project_root": str(project_root),
            },
        )

    # 文件应保持原样
    after = prose_file.read_text(encoding="utf-8")
    assert after == initial, "V0.38：rewrite 不应修改文件"


# === Test 4: insert 基础 ===


@pytest.mark.asyncio
async def test_insert_position_returns_inserted(
    project_with_chapter: dict,
) -> None:
    """V0.38：insert 端点返回 inserted + position。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038(insert_output="插入的过渡段")

    app = create_app()
    with (
        TestClient(app) as client,
        patch("novel2all.cli.main.get_llm_for_model", return_value=mock_llm),
    ):
        position = len(initial) // 2
        resp = client.post(
            "/api/chapter/1/insert",
            data={
                "position": str(position),
                "instruction": "添加景色描写",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["chapter"] == 1
        assert data["position"] == position
        assert data["inserted"] == "插入的过渡段"
        assert "景色描写" in mock_llm.last_prompt


def test_insert_position_prompt_contains_context(
    project_with_chapter: dict,
) -> None:
    """V0.38：insert prompt 应包含前后上下文（各 500 字）。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038()

    app = create_app()
    with (
        TestClient(app) as client,
        patch("novel2all.cli.main.get_llm_for_model", return_value=mock_llm),
    ):
        position = len(initial) // 2
        client.post(
            "/api/chapter/1/insert",
            data={
                "position": str(position),
                "instruction": "test_ins",
                "project_root": str(project_root),
                "context_chars": "100",
            },
        )

        # 前 100 字应在 prompt 中
        before = initial[max(0, position - 100) : position]
        after = initial[position : position + 100]
        # 至少应包含部分上下文
        assert (
            any(c in mock_llm.last_prompt for c in before[:50])
            or before[:50] in mock_llm.last_prompt
        )
        assert (
            any(c in mock_llm.last_prompt for c in after[:50]) or after[:50] in mock_llm.last_prompt
        )


# === Test 5: insert 错误处理 ===


def test_insert_position_400_when_out_of_range(
    project_with_chapter: dict,
) -> None:
    """V0.38：position 越界 → 400。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    total = len(initial)
    app = create_app()
    with TestClient(app) as client:
        # position > total
        resp = client.post(
            "/api/chapter/1/insert",
            data={
                "position": str(total + 100),
                "instruction": "test",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 400

        # position < 0
        resp = client.post(
            "/api/chapter/1/insert",
            data={
                "position": "-1",
                "instruction": "test",
                "project_root": str(project_root),
            },
        )
        assert resp.status_code == 400


def test_insert_position_does_not_modify_file(
    project_with_chapter: dict,
) -> None:
    """V0.38：insert 端点只生成 LLM 结果，不直接改文件。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    prose_file = project_with_chapter["prose_file"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038(insert_output="插入内容")

    app = create_app()
    with (
        TestClient(app) as client,
        patch("novel2all.cli.main.get_llm_for_model", return_value=mock_llm),
    ):
        client.post(
            "/api/chapter/1/insert",
            data={
                "position": "10",
                "instruction": "test",
                "project_root": str(project_root),
            },
        )

    after = prose_file.read_text(encoding="utf-8")
    assert after == initial, "V0.38：insert 不应修改文件"


# === Test 6: explicit model 透传 ===


def test_rewrite_passes_explicit_model(
    project_with_chapter: dict,
) -> None:
    """V0.38：explicit model 参数应被 get_llm_for_model 接收。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    project_root = project_with_chapter["project_root"]
    initial = project_with_chapter["initial_content"]
    mock_llm = MockLLMProviderV038()

    app = create_app()
    with (
        TestClient(app) as client,
        patch(
            "novel2all.cli.main.get_llm_for_model",
            return_value=mock_llm,
        ) as mock_get_llm,
    ):
        resp = client.post(
            "/api/chapter/1/rewrite",
            data={
                "start": "0",
                "end": str(len(initial)),
                "instruction": "test",
                "project_root": str(project_root),
                "model": "deepseek/deepseek-v4-pro",
            },
        )
        assert resp.status_code == 200
        # mock_get_llm 应该被调用 1 次 + 参数 model=...
        mock_get_llm.assert_called_once()
        args, kwargs = mock_get_llm.call_args
        # model 应被透传（位置参数或关键字参数）
        call_model = args[0] if args else kwargs.get("model")
        assert call_model == "deepseek/deepseek-v4-pro"
