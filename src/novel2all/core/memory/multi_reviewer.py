"""V0.30.6 B1：4-agent 并行审查。

设计：解决 "LLM 跑偏"（单 agent 审查只关注一致性，漏掉风格/质量/可读性等维度）。

四个 agent 并行审查同一章节：
1. **Critical Auditor** — 严重错误（事实错误/逻辑断裂/角色崩塌/设定冲突/安全风险）
2. **Major Auditor** — 中度问题（情节拖沓/对话不自然/前后矛盾/角色 OOC）
3. **Minor Auditor** — 小问题（文笔/标点/格式/AI 痕迹）
4. **Quality Judge** — 整体评分（节奏/情感/可读性/沉浸感）0-10 + 通过判定

并行 = asyncio.gather（4 个 LLM 调用并发）。

成本控制：全部用 DeepSeek flash（最便宜），但用 4 个不同 prompt 引导关注点不同。

输出：ReviewReport
- 4 个 agent 各自的 issues + scores
- 总体 pass/warn/fail 状态（critical>0 → fail，major>2 → warn）
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from novel2all.core.memory.verifier import ConsistencyIssue


class ReviewIssue(ConsistencyIssue):
    """B1 单条审查问题（继承 ConsistencyIssue + 加 agent 来源）。

    ConsistencyIssue 已含 severity/category/description/evidence/suggestion，
    这里加一个 agent 字段标识是哪个 agent 找到的（用于聚合报告去重）。
    """

    agent: str = ""  # "critical" | "major" | "minor" | "quality"
    agent_label: str = ""  # 中文标签（用于 UI）


class QualityScore(BaseModel):
    """B1 Quality Judge 输出：多维度评分。

    每个维度 0-10 分（10 最佳）。
    overall_score 由其他维度加权平均。
    """

    overall_score: float = Field(..., ge=0, le=10, description="总评分 0-10")
    pacing: float = Field(..., ge=0, le=10, description="节奏")
    emotion: float = Field(..., ge=0, le=10, description="情感")
    readability: float = Field(..., ge=0, le=10, description="可读性")
    immersion: float = Field(..., ge=0, le=10, description="沉浸感")
    ai_smell: float = Field(..., ge=0, le=10, description="AI 痕迹（10=无痕迹）")
    verdict: str = Field(..., description="verdict: pass | warn | fail")
    summary: str = Field(..., description="一句话总结（≤80 字）")


class ReviewReport(BaseModel):
    """B1 4-agent 审查总报告。"""

    # 4 个 agent 各自输出
    critical_issues: list[ReviewIssue] = Field(default_factory=list)
    major_issues: list[ReviewIssue] = Field(default_factory=list)
    minor_issues: list[ReviewIssue] = Field(default_factory=list)
    quality_score: QualityScore | None = None

    # 聚合统计
    total_critical: int = 0
    total_major: int = 0
    total_minor: int = 0
    overall_verdict: str = ""  # pass | warn | fail
    elapsed_seconds: float = 0.0

    # 元数据
    content_chars: int = 0
    content_preview: str = ""  # 前 200 字（用于 Web UI 上下文）
    chapter_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """导出 dict（用于 API + Web UI）。"""
        return self.model_dump(mode="json")


# === 4 个 Agent 的 Prompt（每个关注点不同）===

CRITICAL_AUDIT_PROMPT = """你是小说【严重错误审查员】。你的唯一职责：找出本章正文的**致命问题**。

## 已有状态（角色/伏笔/时间线）
{state}

## 本章正文
{content}

## 你的关注点（仅这 5 类）
A. **事实硬伤**：与前文矛盾（角色性别/年龄/已死/已离场）
B. **逻辑断裂**：事件因果不通（如先死后逃）
C. **设定冲突**：违反已建立的世界观硬规则
D. **位置错误**：角色瞬移无过渡
E. **严重跑题**：完全偏离章节大纲

## 输出
返回 JSON 数组。每个问题：
- severity: "critical"
- category: "fact" | "logic" | "setting" | "location" | "topic"
- description: 一句话描述
- evidence: 出处（state 具体字段 or 正文原句）
- suggestion: 修复建议

**宁缺毋滥**：没有致命问题就返回 []。不要报"建议改一下节奏"这类 minor 问题。
"""

MAJOR_AUDIT_PROMPT = """你是小说【中度问题审查员】。你的唯一职责：找出本章的**中等质量问题**。

## 已有状态
{state}

## 本章正文
{content}

## 你的关注点（仅这 4 类）
A. **情节拖沓**：明显冗余场景、重复描写
B. **对话不自然**：角色语言不符合身份/性格
C. **前后矛盾**：伏笔埋了没收 / 角色情绪突变无铺垫
D. **角色 OOC**：行为严重偏离角色设定（不是小偏差）

## 输出
返回 JSON 数组。每个问题：
- severity: "warning"
- category: "pacing" | "dialogue" | "consistency" | "ooc"
- description: 一句话描述
- evidence: 出处
- suggestion: 修复建议

**不要**报风格/标点/格式问题（那是 minor 的活）。
**不要**报严重事实错误（那是 critical 的活）。
"""

MINOR_AUDIT_PROMPT = """你是小说【细节优化审查员】。你的唯一职责：找出本章的**小瑕疵**。

## 已有状态
{state}

## 本章正文
{content}

## 你的关注点（仅这 4 类）
A. **文笔问题**：病句/不通顺/语义模糊
B. **标点错误**：引号/逗号/句号错位
C. **AI 痕迹**："作为一个 X"、"不可否认"、"总而言之"、排比句堆砌
D. **格式问题**：段落过长/对话格式不规范

## 输出
返回 JSON 数组。每个问题：
- severity: "info"
- category: "writing" | "punctuation" | "ai_smell" | "format"
- description: 一句话描述
- evidence: 出处（原句）
- suggestion: 修复建议

**不要**报情节/角色/逻辑问题（那是 major/critical 的活）。
"""

QUALITY_JUDGE_PROMPT = """你是小说【质量评审员】。你的唯一职责：给本章打**整体分 + 各维度分**。

## 本章正文
{content}

## 评分维度（每项 0-10）
- pacing: 节奏（10=完美张弛 / 0=全程拖沓或全程紧绷）
- emotion: 情感（10=情感饱满 / 0=毫无波澜）
- readability: 可读性（10=流畅 / 0=晦涩）
- immersion: 沉浸感（10=完全沉浸 / 0=出戏）
- ai_smell: AI 痕迹（10=毫无痕迹 / 0=典型 AI 味）

## 输出
返回 JSON：
- overall_score: 总体分（各维度加权平均，pacing×0.3 + emotion×0.25 + readability×0.2 + immersion×0.15 + ai_smell×0.1）
- pacing: 节奏分
- emotion: 情感分
- readability: 可读性分
- immersion: 沉浸感分
- ai_smell: AI 痕迹分
- verdict: "pass"（≥7）/ "warn"（5-7）/ "fail"（<5）
- summary: 一句话总结本章（≤80 字），说最强项和最弱项

不要报具体问题（那是其他 agent 的活）。只打分。
"""


# === 4-Agent Multi-Reviewer ===


class MultiAgentReviewer:
    """V0.30.6 B1：4-agent 并行审查。

    用法：
        reviewer = MultiAgentReviewer(llm_provider)
        report = await reviewer.review(state=state, content=chapter_content)
        if report.overall_verdict == "fail":
            # ... 警告用户 / 自动回滚
    """

    # Agent 配置：name → (prompt_template, severity, agent_label)
    AGENTS: ClassVar[dict[str, tuple[str, str, str]]] = {
        "critical": (CRITICAL_AUDIT_PROMPT, "critical", "严重错误"),
        "major": (MAJOR_AUDIT_PROMPT, "warning", "中度问题"),
        "minor": (MINOR_AUDIT_PROMPT, "info", "细节优化"),
    }

    def __init__(self, llm: Any):
        """V0.30.6 B1：初始化。

        Args:
            llm: LLMProvider 实例（与 Verifier 一致）
        """
        self.llm = llm

    async def review(
        self,
        state: Any,
        content: str,
        chapter_number: int | None = None,
    ) -> ReviewReport:
        """V0.30.6 B1：4-agent 并行审查。

        Args:
            state: TrackingState（已存在的角色/伏笔/时间线）
            content: 章节正文
            chapter_number: 章节号（用于报告）

        Returns:
            ReviewReport 含 4 agent 各自输出 + 聚合状态
        """
        state_text = self._state_to_text(state)
        start = time.perf_counter()

        # 并行执行 4 个 agent
        # 3 个 ReviewIssue list + 1 个 QualityScore
        results = await asyncio.gather(
            self._run_issue_agent("critical", state_text, content),
            self._run_issue_agent("major", state_text, content),
            self._run_issue_agent("minor", state_text, content),
            self._run_quality_agent(content),
            return_exceptions=True,
        )

        # 处理结果（可能某个 agent 失败）
        critical_issues = self._safe_issues(results[0], "critical")
        major_issues = self._safe_issues(results[1], "major")
        minor_issues = self._safe_issues(results[2], "minor")
        quality_score = self._safe_quality(results[3])

        # 聚合 verdict
        total_critical = len(critical_issues)
        total_major = len(major_issues)
        total_minor = len(minor_issues)

        # 规则：
        # - 任何 critical → fail
        # - major > 2 → warn（太多中度问题）
        # - quality_score < 5 → fail
        # - 5 ≤ quality < 7 → warn
        # - 其他 → pass
        if total_critical > 0 or (quality_score and quality_score.overall_score < 5):
            verdict = "fail"
        elif total_major > 2 or (quality_score and quality_score.overall_score < 7):
            verdict = "warn"
        else:
            verdict = "pass"

        elapsed = time.perf_counter() - start

        return ReviewReport(
            critical_issues=critical_issues,
            major_issues=major_issues,
            minor_issues=minor_issues,
            quality_score=quality_score,
            total_critical=total_critical,
            total_major=total_major,
            total_minor=total_minor,
            overall_verdict=verdict,
            elapsed_seconds=round(elapsed, 3),
            content_chars=len(content),
            content_preview=content[:200],
            chapter_number=chapter_number,
        )

    async def _run_issue_agent(
        self,
        agent_name: str,
        state_text: str,
        content: str,
    ) -> list[ReviewIssue]:
        """运行一个 issue 检测 agent（critical/major/minor）。"""
        prompt_template, severity, agent_label = self.AGENTS[agent_name]
        prompt = prompt_template.format(state=state_text, content=content)

        # 注入 agent 字段：post-process（避免 Pydantic 校验失败）
        try:
            raw_issues = await self.llm.complete_structured(
                prompt=prompt,
                response_model=list[ConsistencyIssue],
            )
        except Exception:
            return []

        return [
            ReviewIssue(
                agent=agent_name,
                agent_label=agent_label,
                severity=issue.severity or severity,  # 兜底用预设 severity
                category=issue.category,
                description=issue.description,
                evidence=issue.evidence,
                suggestion=issue.suggestion,
            )
            for issue in raw_issues
        ]

    async def _run_quality_agent(self, content: str) -> QualityScore:
        """运行 Quality Judge agent。"""
        prompt = QUALITY_JUDGE_PROMPT.format(content=content)
        try:
            return await self.llm.complete_structured(
                prompt=prompt,
                response_model=QualityScore,
            )
        except Exception:
            # 失败时返回默认中性评分（避免阻塞整个 review）
            return QualityScore(
                overall_score=5.0,
                pacing=5.0,
                emotion=5.0,
                readability=5.0,
                immersion=5.0,
                ai_smell=5.0,
                verdict="warn",
                summary="质量评审失败（LLM 调用异常），使用默认中性评分",
            )

    def _safe_issues(self, result: Any, agent_name: str) -> list[ReviewIssue]:
        """处理 asyncio.gather 可能返回的 Exception。"""
        if isinstance(result, Exception):
            return []
        if not isinstance(result, list):
            return []
        return result

    def _safe_quality(self, result: Any) -> QualityScore | None:
        """处理 QualityScore 可能的 Exception。"""
        if isinstance(result, Exception):
            return None
        if not isinstance(result, QualityScore):
            return None
        return result

    @staticmethod
    def _state_to_text(state: Any) -> str:
        """复用 verifier 的状态序列化（简化版）。

        V0.30.6 B1：避免与 verifier 模块耦合 — 直接序列化必要字段。
        """
        if state is None:
            return "（无已有状态）"

        parts = []
        # 角色
        if hasattr(state, "characters") and state.characters:
            chars_str = "\n".join(
                f"  - {name}: {getattr(c, 'description', '')[:120]}"
                for name, c in list(state.characters.items())[:10]
            )
            parts.append(f"## 角色\n{chars_str}")

        # 伏笔
        if hasattr(state, "foreshadowing") and state.foreshadowing:
            fs_str = "\n".join(
                f"  - [{f.id}] {f.description[:100]} (status={f.status})"
                for f in list(state.foreshadowing)[:10]
            )
            parts.append(f"## 伏笔\n{fs_str}")

        # 风格锚点
        if hasattr(state, "style_anchor") and state.style_anchor:
            parts.append(f"## 风格\n{state.style_anchor}")

        return "\n\n".join(parts) if parts else "（无已有状态）"
