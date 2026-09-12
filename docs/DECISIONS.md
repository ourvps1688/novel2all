# novel2all 决策记录

## D1. 项目名 novel2all
**决策**：叫 `novel2all`，不叫 `DSH` 或 `novel-engine` 等。
**理由**：
- novel2all = novel + 2 + all = "novel to all"
- 暗示未来扩展（漫画 / 剧本 / 有声书）
- 摆脱 "DSH = DeepSeek Harness" 的命名限制
- 短、好念、好搜

## D2. Python 3.12 + uv
**决策**：Python 3.12+ 主语言，包管理用 uv。
**理由**：
- Agent 框架生态（LangChain / PydanticAI）是 Python 主场
- LLM SDK 成熟度（anthropic-python 是 reference 实现）
- 文本处理生态（jieba / spacy）
- 未来扩展（视频 / 短剧 / 游戏）需要 Python 重度
- uv 取代 poetry/pip，10-100x 快
**备选**：Node.js + TypeScript（claudecode 是 TS，但 Python 更适合本项目）

## D3. 不使用 LangGraph
**决策**：v0.20 用纯 Pydantic + 手写编排。
**理由**：
- novel2all 是创作工具，13 个 skill 是线性 pipeline，不是图
- LangGraph 解决的多 agent 编排问题 v0.20 用不上
- 学习曲线 / 调试 / vendor lock-in 都不利
- 升级路径开放（v0.21+ 真需要时引入）

## D4. 5 层 memory 系统
**决策**：L1 核心 + L2 角色 + L3 最近 + L4 检索 + L5 图谱。
**理由**：
- claudecode 单一 tracking 系统手工维护成本高、易漏
- novel2all 必须做到"自动化"——写完自动更新
- 5 层分解让每层职责清晰
- 18K token 预算远低于 200K 上限，安全

## D5. 自动 tracking 更新（关键创新）
**决策**：写完一章后自动用 LLM 提取 + merge 到 tracking。
**理由**：
- claudecode 的 tracking 依赖手工维护，是 v0.20 最大的 UX 痛点
- 自动提取 + merge 是 novel2all 的关键差异化能力
- instructor + Pydantic 保证结构化输出

## D6. pre-write blocking 检查
**决策**：写正文前 critical 问题必须先解决。
**理由**：
- claudecode 的 pre-write 只检查"细纲有没有"，不查一致性
- novel2all 必须查角色 / 伏笔 / 时间线的一致性
- critical 阻断是必须的（写作流卡住比写错更好）

## D7. 沿用 Claude Skill 格式（fork 13 skill）
**决策**：SKILL.md frontmatter 格式沿用 Claude Code 生态。
**理由**：
- claudecode 0.7.10 的 13 个 skill 直接可用
- 内容是 markdown，不绑语言
- 未来想跑 Claude Code 也能直接迁

## D8. 去掉 DSH-specific 段落
**决策**：fork 过来的 skill 删掉 DSH 桥接 XML、DSH override、自有重写。
**理由**：
- novel2all 是新 runtime，不需要 DSH 桥接
- L3 DSH bridge XML：告诉 LLM "DSH owns session"——不适用
- L4 override：告诉 LLM "别看 .claude/agents"——不适用
- L5 DSH native：claudecode 整套重写——novel2all 直接用即可

## D9. 不依赖任何上游 runtime
**决策**：novel2all 是自研 Python runtime，不嵌入 DSH / Claude Code / ZCode / LangGraph。
**理由**：
- 用户明确要脱离 DSH 命名
- 自研 runtime 解放力最强
- 升级路径不绑死

## D10. Web UI 用 FastAPI + Jinja2 SPA
**决策**：FastAPI 后端 + Jinja2 模板 + 简单 JS SPA。
**理由**：
- 用户最终形态是 Web UI 给团队用
- FastAPI 自动 OpenAPI 文档
- Jinja2 不引入前端构建步骤
- v0.20 SPA 是占位（status + skills + roles 列表）
- v0.30+ 升级为完整 React/Vue SPA

## D11. LiteLLM 作为 LLM 抽象
**决策**：底层用 LiteLLM 统一 100+ provider。
**理由**：
- 不用写 3 套 SDK 适配（Anthropic / OpenAI / DeepSeek）
- instructor 集成良好
- 切换 provider 不影响业务代码

## D12. License = MIT
**决策**：跟上游 claudecode 一致。
**理由**：
- claudecode 是 MIT
- 团队使用灵活
