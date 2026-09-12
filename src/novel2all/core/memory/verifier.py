"""一致性检查器。

pre-write: 写正文前检查大纲是否与已建立的设定/角色/伏笔冲突
post-write: 写完后检查正文是否有跑偏、AI 味等问题

critical 级别的问题会阻断写作流，warning 仅提示。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from novel2all.core.memory.tracker import TrackingState


class ConsistencyIssue(BaseModel):
    """一个一致性问题。"""

    severity: str  # "critical" | "warning" | "info"
    category: str  # "character" | "foreshadowing" | "timeline" | "setting" | "style"
    description: str
    evidence: str = ""
    suggestion: str = ""


PRE_WRITE_PROMPT = """你是小说连续性预审员。检查本章大纲是否与已有设定/角色/伏笔/时间线冲突。

## 已有状态
{state}

## 本章大纲
{outline}

## 任务
列出所有连续性问题，分类如下：

- character: 角色状态/性格/位置是否冲突
- foreshadowing: 伏笔节奏是否合理（本章是否应该揭示某伏笔、或本章动作是否破坏已埋伏笔）
- timeline: 事件时间是否冲突
- setting: 是否违反已建立的世界观/力量体系
- style: 是否符合文风基线

每个问题给出：
- severity: "critical"（必须先解决）/ "warning"（建议检查）/ "info"（提示）
- category: 类型
- description: 问题描述
- evidence: 出处（来自 state 的具体哪条信息）
- suggestion: 修复建议

只返回 JSON 数组。如果没有发现问题，返回 []。
"""


POST_WRITE_PROMPT = """你是小说质检员。检查本章正文是否有连续性问题或质量问题。

## 已有状态
{state}

## 本章正文
{content}

## 任务
列出所有问题：

- critical:
  - 角色性格严重漂移（违反已建立的核心性格）
  - 设定明确冲突（违反力量体系 / 世界观规则）
  - 时间线硬伤
- warning:
  - 伏笔可能被遗忘（本章应交代但未交代）
  - AI 味明显（出现"在当今社会""综上所述""值得注意的是"等套话）
  - 文风漂移（偏离 {style_anchor}）
- info:
  - 字数偏离目标
  - 章节结尾钩子弱

返回 JSON 数组。
"""


class Verifier:
    """pre/post-write 一致性检查。"""

    def __init__(self, llm: Any):
        self.llm = llm

    async def pre_write_check(
        self,
        state: TrackingState,
        outline: str,
    ) -> list[ConsistencyIssue]:
        """写前检查。"""
        prompt = PRE_WRITE_PROMPT.format(
            state=self._state_to_text(state),
            outline=outline,
        )
        result = await self.llm.complete_structured(
            prompt=prompt,
            response_model=list[ConsistencyIssue],
        )
        return result

    async def post_write_check(
        self,
        state: TrackingState,
        content: str,
    ) -> list[ConsistencyIssue]:
        """写后检查。"""
        prompt = POST_WRITE_PROMPT.format(
            state=self._state_to_text(state),
            content=content,
            style_anchor=state.style_anchor or "未指定",
        )
        result = await self.llm.complete_structured(
            prompt=prompt,
            response_model=list[ConsistencyIssue],
        )
        return result

    @staticmethod
    def _state_to_text(state: TrackingState) -> str:
        """压缩 state 给 prompt 用。"""
        parts = [
            f"# 项目: {state.project_name}",
            f"# 文风: {state.style_anchor or '未指定'}",
            f"# 当前进度: 第 {state.last_updated_chapter} 章",
            "",
            "# 角色状态",
        ]
        for name, char in state.characters.items():
            parts.append(
                f"- {name}: 位置={char.location}, 情绪={char.emotional_state}, "
                f"动机={char.motivation}"
            )

        parts.append("")
        parts.append("# 活跃伏笔")
        for fs in state.foreshadowing.values():
            if fs.status == "active":
                parts.append(f"- {fs.id} (埋于第{fs.planted_chapter}章): {fs.description}")

        parts.append("")
        parts.append("# 最近章节摘要")
        for ch in sorted(state.recent_chapter_summaries.keys())[-5:]:
            parts.append(f"- 第{ch}章: {state.recent_chapter_summaries[ch]}")

        return "\n".join(parts)

    @staticmethod
    def has_blocking_issues(issues: list[ConsistencyIssue]) -> bool:
        """是否有 critical 级问题。"""
        return any(issue.severity == "critical" for issue in issues)
