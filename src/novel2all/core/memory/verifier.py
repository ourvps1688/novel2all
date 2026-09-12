"""一致性检查器。

pre-write: 写正文前检查大纲是否与已建立的设定/角色/伏笔冲突
post-write: 写完后检查正文是否有跑偏、AI 味等问题

severity 三级：
- critical：真"硬伤"，会阻断写作流（必须先解决）
- warning：建议性问题，提示但不阻断
- info：观察性，不阻断

关键设计：critical 必须严格满足"明确违反已有设定"的判定，
避免把"节奏建议""风格偏好"等软问题误判为 critical。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from novel2all.core.memory.tracker import TrackingState


class ConsistencyIssue(BaseModel):
    """一个一致性问题。"""

    severity: str  # "critical" | "warning" | "info"
    category: str  # "character" | "foreshadowing" | "timeline" | "setting" | "style" | "ai_smell"
    description: str
    evidence: str = ""
    suggestion: str = ""


# 共享：critical 判别标准（pre-write 和 post-write 都用）
_CRITICAL_CRITERIA = """\
**critical 必须严格满足以下条件之一**（缺一不可判为 warning/info）：

A. **角色存在性硬伤**
   - 角色已被设定为死亡（state.characters[name].death_chapter != None）或离开故事，
     本章却让他活着并参与情节
   - 角色年龄在设定中是 X 岁，本章让他做明显超越 X 岁认知/能力的行为
     （如 6 岁孩童主导宗门决策）

B. **位置/时间硬伤**
   - 角色上一章最后位置在 A 处，本章大纲/正文让他瞬间出现在地理上
     遥远且无任何过渡的 B 处（如上一章在苍茫镇、本章在海外仙岛）
   - 事件时间顺序违反因果（如先被杀、后又行动）

C. **伏笔/设定硬冲突**
   - 伏笔 state.foreshadowing[id].status == "revealed"，
     本章却把它当 active/未揭示来用
   - 章节内容直接违反已建立的世界观/力量体系硬规则
     （如筑基期能毁天灭地，但设定筑基期只是凡人级别）

D. **风格锚点完全不符**
   - style_anchor 是"古风古韵"，本章正文全是现代都市用语
   - 但这只是次要判定，需结合以上 A/B/C 才判 critical
"""

PRE_WRITE_PROMPT = (
    """你是小说连续性预审员。检查本章大纲是否与已有设定/角色/伏笔/时间线冲突。

## 已有状态
{state}

## 本章大纲
{outline}

## 任务
返回严格 JSON 数组，列出所有连续性问题。每个问题字段：
- severity: "critical" | "warning" | "info"
- category: "character" | "foreshadowing" | "timeline" | "setting" | "style"
- description: 一句话描述
- evidence: 出处（来自 state 的具体哪条信息）
- suggestion: 修复建议（如适用）

"""
    + _CRITICAL_CRITERIA
    + """

**warning 适用场景**（不应判为 critical）：
- 伏笔节奏建议（如"建议第 N 章揭示 fs_xxx"）
- 角色情绪变化建议（"林雷当前懵懂，本章跨度大"）
- 抽象的"可能不连贯"担忧（"建议补充过渡"）
- 任何可由作者决定、不直接违反已建立设定的问题

**info 适用场景**：观察性提示，无须修改。

## 严格性要求
**宁缺毋滥**：判 critical 前必须能在已有 state 中找到明确证据。
找不到明确证据就判 warning 或不要报。

如果没有任何问题，返回 []。
"""
)


POST_WRITE_PROMPT = (
    """你是小说质检员。检查本章正文是否有连续性问题或质量问题。

## 已有状态
{state}

## 本章正文
{content}

## 任务
返回严格 JSON 数组，列出所有问题。每个问题字段：
- severity: "critical" | "warning" | "info"
- category: "character" | "foreshadowing" | "timeline" | "setting" | "style" | "ai_smell"
- description: 一句话描述
- evidence: 引用正文片段（10-30 字）
- suggestion: 修复建议（如适用）

"""
    + _CRITICAL_CRITERIA
    + """

**warning 适用场景**（不应判为 critical）：
- 伏笔推进节奏（"fs_xxx 应在更后章节揭示"）
- AI 味（出现"在当今社会""综上所述""值得注意的是"等套话）
- 文风与 style_anchor ({style_anchor}) 有偏差
- 字数偏离目标
- 角色情绪/动机过渡不够平滑
- 任何可由作者决定、不直接违反已有设定的问题

**info 适用场景**：
- 章节结尾钩子弱
- 推进节奏观察
- 字数偏差

## 严格性要求
**宁缺毋滥**：判 critical 前必须能在已有 state 或正文中找到明确证据。
找不到明确证据就判 warning 或 info，不要制造焦虑。

如果没有任何问题，返回 []。
"""
)


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
        return self._filter_issues(result)

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
        return self._filter_issues(result)

    @staticmethod
    def _filter_issues(issues: list[ConsistencyIssue]) -> list[ConsistencyIssue]:
        """后处理：验证 severity 字段、去重。"""
        if not issues:
            return []
        valid_severities = {"critical", "warning", "info"}
        seen: set[tuple] = set()
        out: list[ConsistencyIssue] = []
        for issue in issues:
            # 验证 severity（兜底）
            sev = issue.severity if issue.severity in valid_severities else "warning"
            # 严重程度去重（同一类别同一描述只保留一条）
            key = (sev, issue.category, issue.description.strip())
            if key in seen:
                continue
            seen.add(key)
            out.append(
                ConsistencyIssue(
                    severity=sev,
                    category=issue.category,
                    description=issue.description,
                    evidence=issue.evidence,
                    suggestion=issue.suggestion,
                )
            )
        return out

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
                f"动机={char.motivation}, 最近更新={char.last_updated_chapter}"
            )

        parts.append("")
        parts.append("# 活跃伏笔")
        for fs in state.foreshadowing.values():
            parts.append(
                f"- {fs.id} (埋于第{fs.planted_chapter}章, status={fs.status}): {fs.description}"
            )

        parts.append("")
        parts.append("# 最近章节摘要")
        for ch in sorted(state.recent_chapter_summaries.keys())[-5:]:
            parts.append(f"- 第{ch}章: {state.recent_chapter_summaries[ch]}")

        return "\n".join(parts)

    @staticmethod
    def has_blocking_issues(issues: list[ConsistencyIssue]) -> bool:
        """是否有 critical 级问题。"""
        return any(issue.severity == "critical" for issue in issues)
