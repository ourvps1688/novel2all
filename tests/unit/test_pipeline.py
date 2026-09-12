"""WritingPipeline 单元测试。

不依赖真实 LLM —— 用 mock provider 验证 pipeline 完整流程：
- pre-write check
- memory load
- skill prompt 组装
- LLM stream 调用
- 文件写入
- post-write check
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from novel2all.core import LLMConfig, LLMProvider
from novel2all.core.memory import MemoryConfig, MemoryManager, Tracker
from novel2all.core.pipeline import (
    OutlineNotFoundError,
    PipelineError,
    WritingPipeline,
)
from novel2all.core.project import ProjectStructure
from novel2all.core.skill import SkillRegistry

# === Mock LLM ===

class MockLLM(LLMProvider):
    """Mock LLM provider，stream 返回固定文本。"""

    def __init__(self, mock_content: str = "本章正文。" * 200, **kwargs: Any) -> None:
        super().__init__(LLMConfig())
        self.mock_content = mock_content
        self.stream_called = 0
        self.last_prompt = ""
        self.last_system = ""

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.mock_content

    async def complete_structured(
        self,
        prompt: str,
        *,
        response_model: Any,
        **kwargs: Any,
    ) -> Any:
        # pre/post-write check 可能调结构化输出
        # 统一返回空 / 空实例
        origin = getattr(response_model, "__origin__", None)
        if origin is list:
            return []
        if hasattr(response_model, "model_construct"):
            return response_model.model_construct()
        return None

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        self.stream_called += 1
        self.last_prompt = prompt
        self.last_system = kwargs.get("system", "")
        # 模拟流式输出：按字符切分
        for chunk_size in [10, 20, 30]:
            for i in range(0, len(self.mock_content), chunk_size):
                yield self.mock_content[i : i + chunk_size]
                if i > 100:  # 限制测试数据量
                    return


# === Fixtures ===

@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """创建测试用项目目录（已有 tracking state + 设定）。"""
    (tmp_path / "设定" / "世界观").mkdir(parents=True)
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    (tmp_path / "设定" / "文风.md").write_text("古风古韵，简洁有力", encoding="utf-8")
    tracker = Tracker(tmp_path / "_tracking-state.json")
    tracker.init(
        project_name="pipeline 测试",
        genre="玄幻",
        total_chapters_target=10,
    )
    # 写细纲
    (tmp_path / "大纲" / "细纲_第001章.md").write_text(
        "# 第 1 章细纲\n\n林雷在苍茫镇觉醒血脉之力。",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def skills_dir() -> Path:
    """用项目内置 skills 目录。"""
    return Path(__file__).parent.parent.parent / "src" / "novel2all" / "skills"


@pytest.fixture
def pipeline(
    project_root: Path,
    skills_dir: Path,
) -> tuple[WritingPipeline, MockLLM, SkillRegistry]:
    """装配完整 pipeline + 暴露 mock 供测试访问。"""
    llm = MockLLM(mock_content="这是第 N 章的正文。" * 200)  # ~1400 字
    project = ProjectStructure(root=project_root)
    manager = MemoryManager(
        project_root=project_root,
        config=MemoryConfig(),
        llm=llm,
    )
    skill_registry = SkillRegistry(skills_dir)
    skill_registry.discover()
    pipeline = WritingPipeline(
        manager=manager,
        skill_registry=skill_registry,
        llm=llm,
        project=project,
    )
    return pipeline, llm, skill_registry


# === Tests ===

class TestWriteChapter:
    def test_outline_not_found(self, project_root: Path, skills_dir: Path) -> None:
        """细纲不存在 → OutlineNotFoundError。"""
        llm = MockLLM()
        project = ProjectStructure(root=project_root)
        manager = MemoryManager(project_root=project_root, llm=llm)
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(manager, skill_registry, llm, project)

        with pytest.raises(OutlineNotFoundError):
            asyncio.run(
                pipeline.write_chapter(
                    chapter=99,
                    outline_path=project_root / "大纲" / "细纲_第099章.md",
                )
            )

    def test_skill_not_found(self, project_root: Path, skills_dir: Path) -> None:
        """skill 不存在 → PipelineError。"""
        llm = MockLLM()
        project = ProjectStructure(root=project_root)
        manager = MemoryManager(project_root=project_root, llm=llm)
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(manager, skill_registry, llm, project)

        with pytest.raises(PipelineError, match="未注册"):
            asyncio.run(
                pipeline.write_chapter(
                    chapter=1,
                    outline_path=project_root / "大纲" / "细纲_第001章.md",
                    skill_name="nonexistent-skill",
                )
            )

    def test_write_chapter_full_flow(
        self,
        project_root: Path,
        skills_dir: Path,
    ) -> None:
        """完整流程：mock LLM 写第 1 章，验证产出。"""
        llm = MockLLM(mock_content="这是精彩的章节正文。" * 100)  # ~1000 字
        project = ProjectStructure(root=project_root)
        manager = MemoryManager(project_root=project_root, llm=llm)
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(manager, skill_registry, llm, project)

        chunks: list[str] = []
        result = asyncio.run(
            pipeline.write_chapter(
                chapter=1,
                outline_path=project_root / "大纲" / "细纲_第001章.md",
                characters_involved=["林雷"],
                stream_callback=lambda c: chunks.append(c),
            )
        )

        # === 验证产出 ===
        assert result.chapter == 1
        assert result.content_chars > 0
        assert result.output_path.exists()
        # 文件内容包含 mock 的文本
        saved = result.output_path.read_text(encoding="utf-8")
        assert "这是精彩的章节正文" in saved
        # 流式回调被调用
        assert len(chunks) > 0
        # mock LLM stream 被调用
        assert llm.stream_called == 1
        # prompt 包含细纲 + skill 内容
        assert "苍茫镇" in llm.last_prompt or "血脉" in llm.last_prompt

    def test_stream_callback_exception_doesnt_break_generation(
        self,
        project_root: Path,
        skills_dir: Path,
    ) -> None:
        """stream_callback 抛异常不应中断 LLM 生成。"""

        def bad_callback(chunk: str) -> None:
            raise ValueError("callback error")

        llm = MockLLM()
        project = ProjectStructure(root=project_root)
        manager = MemoryManager(project_root=project_root, llm=llm)
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(manager, skill_registry, llm, project)

        # 不应抛异常
        result = asyncio.run(
            pipeline.write_chapter(
                chapter=1,
                outline_path=project_root / "大纲" / "细纲_第001章.md",
                stream_callback=bad_callback,
            )
        )
        assert result.content_chars > 0

    def test_infer_characters_from_tracker(
        self,
        project_root: Path,
        skills_dir: Path,
    ) -> None:
        """characters_involved=None 时，从 tracker 推断最近更新的角色。"""
        from novel2all.core.memory.tracker import CharacterState

        # 预置 3 个角色
        tracker = Tracker(project_root / "_tracking-state.json")
        state = tracker.read()
        state.characters["林雷"] = CharacterState(
            name="林雷", last_updated_chapter=3
        )
        state.characters["苏寒"] = CharacterState(
            name="苏寒", last_updated_chapter=2
        )
        state.characters["青云"] = CharacterState(
            name="青云", last_updated_chapter=1
        )
        tracker.write(state)

        llm = MockLLM()
        project = ProjectStructure(root=project_root)
        manager = MemoryManager(project_root=project_root, llm=llm)
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(manager, skill_registry, llm, project)

        result = asyncio.run(
            pipeline.write_chapter(
                chapter=4,
                outline_path=project_root / "大纲" / "细纲_第001章.md",
                characters_involved=None,  # 触发推断
            )
        )

        # 推断结果应包含最近更新的 3 个
        assert all(name in llm.last_prompt for name in ["林雷", "苏寒", "青云"])
        assert result is not None

    def test_post_write_updates_tracker(
        self,
        project_root: Path,
        skills_dir: Path,
    ) -> None:
        """写完后 tracker 应自动更新（recent_chapter_summaries）。"""
        llm = MockLLM(mock_content="精彩的章节。" * 200)
        project = ProjectStructure(root=project_root)
        manager = MemoryManager(project_root=project_root, llm=llm)
        skill_registry = SkillRegistry(skills_dir)
        skill_registry.discover()
        pipeline = WritingPipeline(manager, skill_registry, llm, project)

        result = asyncio.run(
            pipeline.write_chapter(
                chapter=1,
                outline_path=project_root / "大纲" / "细纲_第001章.md",
            )
        )

        # tracker 应有 chapter 1 的摘要（即使内容很短，extractor 也会尝试生成）
        tracker = Tracker(project_root / "_tracking-state.json")
        final_state = tracker.read()
        # mock LLM 的 extractor 会返回空 ExtractedChapterInfo（model_construct）
        # 所以 recent_chapter_summaries 可能没有 1
        # 但 last_updated_chapter 应被更新为 1
        assert final_state.last_updated_chapter == 1
        assert result is not None
