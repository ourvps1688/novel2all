"""写作 pipeline。

编排完整写作流程：pre-write check → load memory → skill prompt → LLM stream → save → post-write check。

设计原则：
- stream_callback 让调用方（CLI / Web SSE）能实时拿到 LLM 输出片段
- 失败清晰：BlockingIssuesError / OutlineNotFoundError / LLMAuthError 让上层能针对性处理
- 不依赖真实 LLM（用 mock LLM provider 也能跑完整流程，便于测试）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novel2all.core.memory import MemoryManager
from novel2all.core.memory.tracker import TrackingState
from novel2all.core.memory.verifier import (
    ConsistencyIssue,
    Verifier,
)
from novel2all.core.project import ProjectStructure
from novel2all.core.provider import LLMProvider
from novel2all.core.provider_router import TaskType
from novel2all.core.skill import SkillDefinition, SkillRegistry

# === 错误类型 ===


class PipelineError(Exception):
    """Pipeline 基础错误。"""


class OutlineNotFoundError(PipelineError):
    """细纲文件不存在。"""


class BlockingIssuesError(PipelineError):
    """pre-write check 发现了 critical 问题，必须先解决。"""

    def __init__(self, issues: list[ConsistencyIssue]) -> None:
        super().__init__(f"发现 {len(issues)} 个 critical 问题")
        self.issues = issues


class LLMAuthError(PipelineError):
    """LLM 鉴权失败（key 缺失或无效）。"""


# === 结果类型 ===


@dataclass
class WriteResult:
    """一次写作的完整结果。"""

    chapter: int
    output_path: Path
    content: str
    content_chars: int
    state: TrackingState
    post_write_issues: list[ConsistencyIssue] = field(default_factory=list)
    pre_write_issues: list[ConsistencyIssue] = field(default_factory=list)


# === Pipeline ===


class WritingPipeline:
    """写作 pipeline。

    用法：
        pipeline = WritingPipeline(manager, skill_registry, llm, project)
        result = await pipeline.write_chapter(
            chapter=5,
            outline_path=project.chapter_outline(5),
            characters_involved=["林雷"],
            skill_name="story-long-write",
            stream_callback=lambda c: print(c, end=""),
        )
    """

    def __init__(
        self,
        manager: MemoryManager,
        skill_registry: SkillRegistry,
        llm: LLMProvider,
        project: ProjectStructure,
    ):
        self.manager = manager
        self.skill_registry = skill_registry
        self.llm = llm
        self.project = project

    async def write_chapter(
        self,
        *,
        chapter: int,
        outline_path: Path,
        characters_involved: list[str] | None = None,
        skill_name: str = "story-long-write",
        stream_callback: Callable[[str], None] | None = None,
        min_chars: int = 2000,
        skip_pre_write_check: bool = False,
    ) -> WriteResult:
        """写第 N 章，完整流程。

        Args:
            chapter: 章节号
            outline_path: 细纲文件路径
            characters_involved: 本章涉及的角色列表（None = 从 tracking state 推断）
            skill_name: 使用的 skill 名称（默认 story-long-write）
            stream_callback: 流式回调（每次 LLM 输出 chunk 时触发）
            min_chars: 最低字数要求（用于 post-write check）
            skip_pre_write_check: 跳过 pre-write check（默认 False）

        Returns:
            WriteResult

        Raises:
            OutlineNotFoundError: 细纲文件不存在
            BlockingIssuesError: pre-write check 有 critical 问题（除非 skip_pre_write_check=True）
        """
        # 1. 校验细纲
        if not outline_path.exists():
            raise OutlineNotFoundError(f"细纲文件不存在: {outline_path}。请先写细纲。")
        outline_text = outline_path.read_text(encoding="utf-8")

        # 2. pre-write check（可跳过）
        pre_issues: list[ConsistencyIssue] = []
        if not skip_pre_write_check:
            pre_issues = await self.manager.pre_write_check(chapter, outline_text)
            if Verifier.has_blocking_issues(pre_issues):
                raise BlockingIssuesError(pre_issues)

        # 3. 加载 memory context
        characters = characters_involved or self._infer_characters(chapter)
        ctx = await self.manager.load_for_writing(
            chapter=chapter,
            chapter_outline=outline_text,
            characters_involved=characters,
        )

        # 4. 取 skill 并组装 prompt
        skill = self.skill_registry.get(skill_name)
        if skill is None:
            raise PipelineError(f"skill '{skill_name}' 未注册。可用：{self.skill_registry.names()}")

        prompt = self._build_prompt(
            skill=skill,
            outline=outline_text,
            memory_context=ctx,
            characters=characters,
            chapter=chapter,
        )

        # 5. 流式调用 LLM（V0.23+：自动应用 DeepSeek 双模型路由 + thinking 控制）
        content_chunks: list[str] = []
        try:
            async for chunk in self.llm.stream(
                prompt=prompt,
                system=self._build_system_prompt(skill),
                temperature=0.7,
                task=TaskType.WRITING,
            ):
                content_chunks.append(chunk)
                if stream_callback is not None:
                    try:
                        stream_callback(chunk)
                    except Exception as e:
                        # stream_callback 异常不应中断生成
                        import sys

                        print(f"stream_callback error: {e}", file=sys.stderr)
        except Exception as e:
            error_msg = str(e).lower()
            if "auth" in error_msg or "key" in error_msg or "401" in error_msg:
                raise LLMAuthError(f"LLM 鉴权失败: {e}") from e
            raise PipelineError(f"LLM 调用失败: {e}") from e

        content = "".join(content_chunks)

        # 6. 字数校验（低于阈值则警告但不阻断）
        if len(content) < min_chars:
            import sys

            print(
                f"⚠ 第 {chapter} 章仅 {len(content)} 字，少于预期 {min_chars}",
                file=sys.stderr,
            )

        # 7. 写文件
        output_path = self.project.chapter_prose(chapter)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

        # 8. update memory + post-write check
        state, post_issues = await self.manager.update_after_writing(
            chapter=chapter, content=content
        )

        return WriteResult(
            chapter=chapter,
            output_path=output_path,
            content=content,
            content_chars=len(content),
            state=state,
            post_write_issues=post_issues,
            pre_write_issues=pre_issues,
        )

    def _infer_characters(self, chapter: int) -> list[str]:
        """从 tracker 推断本章可能涉及的角色（取最近更新的 N 个）。"""
        if not self.manager.tracker.exists():
            return []
        state = self.manager.tracker.read()
        # 按 last_updated_chapter 倒序，取前 3 个
        chars = sorted(
            state.characters.values(),
            key=lambda c: c.last_updated_chapter or 0,
            reverse=True,
        )
        return [c.name for c in chars[:3]]

    def _build_prompt(
        self,
        *,
        skill: SkillDefinition,
        outline: str,
        memory_context: Any,
        characters: list[str],
        chapter: int,
    ) -> str:
        """组装写作 prompt：细纲 + memory context + skill body。"""
        sections: list[str] = [
            f"# 当前任务：写第 {chapter} 章",
            "",
            "## 本章细纲",
            outline,
            "",
            "## 涉及的已知角色",
            ", ".join(characters) if characters else "（自动推断）",
            "",
        ]

        # 嵌入 memory context（4 层）
        sys_sections = memory_context.to_system_sections()
        if sys_sections:
            sections.append("## 历史记忆（请勿违反）")
            sections.extend(sys_sections)
            sections.append("")

        # skill 正文作为 prompt 的指令
        sections.append("## 写作要求（skill instructions）")
        sections.append(skill.content)

        return "\n".join(sections)

    @staticmethod
    def _build_system_prompt(skill: SkillDefinition) -> str:
        """从 skill description 派生 system prompt。"""
        return (
            f"你是一个小说写作助手。"
            f"你的任务是执行 skill '{skill.name}'。"
            f"\n\nskill 描述：{skill.description}"
        )
