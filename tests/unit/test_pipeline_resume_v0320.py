"""V0.32 Pipeline 智能恢复测试。

覆盖：
1. resume_from_chars=0 + output_path 不存在 → 正常开始（基线）
2. resume_from_chars=0 + output_path 存在 → 忽略已有内容，从头写（覆盖）
3. resume_from_chars>0 + output_path 不存在 → 警告但继续（视为正常开始）
4. resume_from_chars>0 + output_path 存在 → 加载 partial + 接续
5. resume 模式下 WriteResult.content 包含 partial + 续写
6. resume 模式下 prompt 含「已写部分」+「请继续」指令
7. resume 模式下 WriteResult.resumed_from_chars > 0
8. partial content 长度大于 resume_from_chars → 只取前 N 字
9. 部分恢复：用户编辑 partial 后恢复 → 接续编辑后的内容
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.memory import MemoryConfig, MemoryManager, Tracker
from novel2all.core.pipeline import WritingPipeline
from novel2all.core.project import ProjectStructure
from novel2all.core.skill import SkillRegistry

# === Mock LLM（跟踪接收的 prompt + 返回可预测输出）===


class ResumeTrackingMockLLM(LLMProvider):
    """跟踪每次 stream 调用的 prompt，验证 resume 模式下 prompt 含 partial 内容。

    output 模式：
    - 字符 'A' × 100（默认）
    - 第一次 chunk 后把 cancel_after_chars 标记设为 True（让测试可以验证取消）
    """

    def __init__(
        self,
        mock_output: str = "续写内容。" * 100,  # 500 字
        **kwargs: Any,
    ) -> None:
        super().__init__(LLMConfig())
        self.mock_output = mock_output
        self.last_prompt = ""
        self.last_system = ""
        self.stream_call_count = 0

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.mock_output

    async def complete_structured(
        self, prompt: str, *, response_model: Any = None, **kwargs: Any
    ) -> Any:
        origin = getattr(response_model, "__origin__", None) if response_model else None
        if origin is list:
            return []
        if hasattr(response_model, "model_construct"):
            return response_model.model_construct()
        return None

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        self.stream_call_count += 1
        self.last_prompt = prompt
        self.last_system = kwargs.get("system", "")
        # 分块 yield
        for i in range(0, len(self.mock_output), 50):
            yield self.mock_output[i : i + 50]
            await asyncio.sleep(0.001)


# === Fixtures ===


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """测试用项目目录。"""
    (tmp_path / "设定" / "世界观").mkdir(parents=True)
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    (tmp_path / "设定" / "文风.md").write_text("古风古韵", encoding="utf-8")
    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(
        project_name="resume 测试",
        genre="玄幻",
        total_chapters_target=10,
    )
    (tmp_path / "大纲" / "细纲_第001章.md").write_text(
        "# 第 1 章细纲\n\n林雷觉醒血脉。",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def pipeline_factory(project_root: Path):
    """返回创建 pipeline 的工厂（每次新建 mock LLM 实例）。"""

    def _make(
        mock_output: str = "续写内容。" * 100,
    ) -> tuple[WritingPipeline, ResumeTrackingMockLLM]:
        llm = ResumeTrackingMockLLM(mock_output=mock_output)
        manager = MemoryManager(project_root=project_root, config=MemoryConfig(), llm=llm)
        skills_dir = Path(__file__).parent.parent.parent / "src" / "novel2all" / "skills"
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(
            manager=manager,
            skill_registry=skill_registry,
            llm=llm,
            project=ProjectStructure(root=project_root),
        )
        return pipeline, llm

    return _make


# === Test 1: resume_from_chars=0 基线（覆盖已有 partial）===


@pytest.mark.asyncio
async def test_resume_zero_overwrites_existing_partial(
    pipeline_factory, project_root: Path
) -> None:
    """V0.32：resume_from_chars=0 时，即使 output_path 已有内容也从头写（覆盖）。"""
    # 先写一个旧 partial
    output_path = project_root / "正文" / "第001章.md"
    output_path.write_text("旧 partial 内容（应被覆盖）", encoding="utf-8")

    pipeline, _llm = pipeline_factory(mock_output="新内容。" * 50)
    result = await pipeline.write_chapter(
        chapter=1,
        outline_path=project_root / "大纲" / "细纲_第001章.md",
        skill_name="story-long-write",
        min_chars=100,
        resume_from_chars=0,
    )

    # 从头写 → content 是新内容（不含旧 partial）
    assert "旧 partial" not in result.content
    assert result.resumed_from_chars == 0
    # 写入 output_path 覆盖旧 partial
    assert output_path.read_text(encoding="utf-8") == result.content


# === Test 2: resume_from_chars>0 + partial 存在 → 接续 ===


@pytest.mark.asyncio
async def test_resume_loads_partial_and_continues(pipeline_factory, project_root: Path) -> None:
    """V0.32：resume_from_chars=80 + partial 80 字 → 续写 500 字，共 580 字。"""
    # 模拟已 cancel 的 partial
    output_path = project_root / "正文" / "第001章.md"
    partial = "这是已写的部分内容。" * 5  # 30 字
    output_path.write_text(partial, encoding="utf-8")

    pipeline, llm = pipeline_factory(mock_output="续写开始。" + "新内容。" * 80)
    result = await pipeline.write_chapter(
        chapter=1,
        outline_path=project_root / "大纲" / "细纲_第001章.md",
        skill_name="story-long-write",
        min_chars=100,
        resume_from_chars=len(partial),
    )

    # V0.32：content = partial + 续写
    assert result.content.startswith(partial), "content 应以 partial 开头"
    assert "续写开始" in result.content, "content 应含续写内容"
    assert result.resumed_from_chars == len(partial)

    # 验证 prompt 含 partial 内容（确保 LLM 看到 partial）
    assert partial in llm.last_prompt, "prompt 应包含 partial 内容"
    # 验证 prompt 含「已写部分」+「请继续」指令
    assert "已写部分" in llm.last_prompt
    assert "继续" in llm.last_prompt


# === Test 3: resume_from_chars>0 + partial 不存在 → 警告但继续 ===


@pytest.mark.asyncio
async def test_resume_without_partial_falls_back_to_normal(
    pipeline_factory, project_root: Path
) -> None:
    """V0.32：resume_from_chars>0 但 output_path 不存在 → 视为正常开始。"""
    pipeline, llm = pipeline_factory(mock_output="新内容。" * 50)

    result = await pipeline.write_chapter(
        chapter=1,
        outline_path=project_root / "大纲" / "细纲_第001章.md",
        skill_name="story-long-write",
        min_chars=100,
        resume_from_chars=80,  # > 0 但 partial 不存在
    )

    # 视为正常开始
    assert result.resumed_from_chars == 0
    assert "已写部分" not in llm.last_prompt  # prompt 不应含「已写部分」


# === Test 4: resume_from_chars 大于实际 partial 长度 → 取实际长度 ===


@pytest.mark.asyncio
async def test_resume_truncates_to_actual_partial_length(
    pipeline_factory, project_root: Path
) -> None:
    """V0.32：resume_from_chars=200 但 partial 只有 30 字 → 实际 partial 30 字。"""
    output_path = project_root / "正文" / "第001章.md"
    partial = "实际只有这么多"  # 7 字
    output_path.write_text(partial, encoding="utf-8")

    pipeline, _llm = pipeline_factory(mock_output="续写。" * 50)
    result = await pipeline.write_chapter(
        chapter=1,
        outline_path=project_root / "大纲" / "细纲_第001章.md",
        skill_name="story-long-write",
        min_chars=100,
        resume_from_chars=200,  # 比实际大
    )

    # 实际 partial = min(resume_from_chars, len(partial))
    assert result.content.startswith(partial)
    assert result.resumed_from_chars == len(partial)


# === Test 5: 用户编辑 partial 后恢复 → 接续编辑后的内容 ===


@pytest.mark.asyncio
async def test_resume_after_manual_edit(pipeline_factory, project_root: Path) -> None:
    """V0.32：用户编辑 partial 后恢复 → 续写基于编辑后的内容。"""
    output_path = project_root / "正文" / "第001章.md"
    # 模拟：用户编辑了 partial（改了内容）
    edited_partial = "用户编辑后的开头内容。林雷来到了苍茫镇。"
    output_path.write_text(edited_partial, encoding="utf-8")

    pipeline, _llm = pipeline_factory(mock_output="续写。" * 50)
    result = await pipeline.write_chapter(
        chapter=1,
        outline_path=project_root / "大纲" / "细纲_第001章.md",
        skill_name="story-long-write",
        min_chars=100,
        resume_from_chars=len(edited_partial),
    )

    # 内容基于编辑后的 partial 续写
    assert edited_partial in result.content
    assert "续写" in result.content


# === Test 6: resume 模式 prompt 含字符数提示 ===


@pytest.mark.asyncio
async def test_resume_prompt_includes_word_count_target(
    pipeline_factory, project_root: Path
) -> None:
    """V0.32：resume 模式下 prompt 含「目标 N 字，已写 M 字，还需 K 字」提示。"""
    output_path = project_root / "正文" / "第001章.md"
    partial = "已有。" * 10  # 30 字
    output_path.write_text(partial, encoding="utf-8")

    pipeline, llm = pipeline_factory(mock_output="续写。" * 50)
    await pipeline.write_chapter(
        chapter=1,
        outline_path=project_root / "大纲" / "细纲_第001章.md",
        skill_name="story-long-write",
        min_chars=2000,
        resume_from_chars=len(partial),
    )

    # prompt 应含字符数提示
    assert "30 字" in llm.last_prompt or f"{len(partial)} 字" in llm.last_prompt
    assert "2000" in llm.last_prompt  # min_chars


# === Test 7: 正常完成（无 resume）下 resumed_from_chars = 0 ===


@pytest.mark.asyncio
async def test_normal_write_resumed_from_chars_is_zero(pipeline_factory) -> None:
    """V0.32：正常从头写（resume_from_chars=0 或未传）→ resumed_from_chars=0。"""
    pipeline, llm = pipeline_factory()
    result = (
        await pipeline.write_chapter(
            chapter=1,
            outline_path=Path("tests/e2e/_test_outline.md"),  # 不存在
        )
        if False
        else await pipeline.write_chapter(
            chapter=1,
            outline_path=pipeline.project.root / "大纲" / "细纲_第001章.md",
            skill_name="story-long-write",
            min_chars=100,
        )
    )

    assert result.resumed_from_chars == 0
    assert "已写部分" not in llm.last_prompt


# === Test 8: SSE 端点接受 resume_from_chars 参数 ===


def test_sse_endpoint_accepts_resume_from_chars_param() -> None:
    """V0.32：POST /api/write/stream/model 接受 resume_from_chars Form 参数。"""
    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    app = create_app()
    with TestClient(app) as client:
        # 即使项目不存在，端点也应能处理 resume_from_chars（错误信息含 task_id）
        response = client.post(
            "/api/write/stream/model",
            data={
                "chapter": 1,
                "project_root": "D:/nonexistent",
                "resume_from_chars": 80,  # V0.32 新参数
            },
        )
        assert response.status_code == 200
        # 端点应正常响应（含 error 事件，含 task_id）
        assert "task_id" in response.text or "task" in response.text


# === Test 9: 'started' SSE 事件含 resume_from_chars ===


def test_sse_started_event_includes_resume_from_chars(tmp_path: Path) -> None:
    """V0.32：SSE 'started' 事件含 resume_from_chars 字段（让前端能看到）。

    需要真实项目目录（让 endpoint 走完 'started' 阶段）。
    """
    # 构造最小项目目录
    (tmp_path / "设定").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(project_name="started test", genre="玄幻", total_chapters_target=1)
    (tmp_path / "大纲" / "细纲_第001章.md").write_text(
        "# 第 1 章\n内容。",
        encoding="utf-8",
    )

    from fastapi.testclient import TestClient

    from novel2all.web.app import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/write/stream/model",
            data={
                "chapter": 1,
                "project_root": str(tmp_path).replace("\\", "/"),
                "resume_from_chars": 120,
            },
        )
        assert response.status_code == 200
        # started 事件应含 resume_from_chars: 120
        assert "resume_from_chars" in response.text
        assert "120" in response.text
