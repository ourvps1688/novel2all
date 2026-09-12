# novel2all 路线图

## v0.21 ✅ 检索 + 摘要 + LLM 真写 + Web SSE + UX 面板（已完成 2026-09-12）

**目标**: 解决"漏掉历史"问题，端到端跑通最小可用闭环

**完成报告**: [`docs/v0.21-summary.md`](v0.21-summary.md)（关键决策 / 16 commit 链路 / 架构图 / 技术经验）

**设计蓝图**: [`docs/v0.21-design.md`](v0.21-design.md)（Step 2/3 设计）

### 子版本

| 版本 | 内容 | commit |
|---|---|---|
| 0.21.1 | Step 1: L4 检索 + L3 早期压缩 + 50 章验证 | 8 个 |
| 0.21.2 | Step 2: 完整 skill pipeline + LLM 真写 + verifier 优化 | 6 个 |
| 0.21.3 | Step 3: Web SSE 流式写作 + UX 面板 | 2 个 |
| 0.21.4 | 归档 + 收官报告 | 1 个 |
| **合计** | | **16 个 ALL_GREEN** |

### 测试覆盖

- 单元测试 86 (核心) + 18 (Web) = 104
- e2e 50 章模拟 8 + smoke 4 = 12
- CI 状态查询 17
- 整合 22 (retriever + summarizer + memory)
- **合计 161 个全过** + 7 个沙箱 chromadb skip

### 关键能力

- CLI 真 LLM 写一章: DeepSeek 2900+ 字
- Web SSE: 1920 个 chunk 事件 / 30.8s 流完 2802 字
- 5 层 memory: 50 章模拟零丢失
- 角色 / 伏笔 / 章节详情 三个面板
- 远端 main = `56d8455`，CI + CodeQL ALL_GREEN

---

## v0.22 — 知识图谱 + 多模型路由

**目标**: 解决"一致性"问题

| 模块 | 工作量 |
|---|---|
| `core/memory/graph.py` (NetworkX 知识图谱) | 3 天 |
| 自动从章节提取图谱节点 / 边 | 3 天 |
| `core/provider/router.py` (按任务选模型) | 2 天 |
| 多模型对比实验 | 2 天 |
| **合计** | **~2 周** |

---

## v0.30 — Self-verification loop

**目标**: 解决"LLM 跑偏"问题

| 模块 | 工作量 |
|---|---|
| 写完后多 agent 审查 (4 role 并行) | 3 天 |
| critical 问题自动回滚 | 2 天 |
| Web UI 完整化 (实时进度条 / 角色面板 / 伏笔追踪) | 5 天 |
| 多用户支持 (团队版) | 3 天 |
| **合计** | **~2 周** |

---

## v1.0 — GA

- 完整测试覆盖 (unit + integration + e2e)
- 性能优化 (流式响应延迟 < 500ms)
- 文档完善 (用户指南 + API 参考)
- Docker 镜像发布
- 团队版部署工具

---

## 远期扩展 (v2.0+)

- **短剧** (基于 novel2all 的角色 + 剧情，扩展视觉创作)
- **互动游戏** (基于 novel2all 的设定 + 伏笔，扩展分支剧情)
- **有声书** (基于 novel2all 的正文 + 角色，扩展 TTS)
- **多语言** (基于 novel2all 的结构，扩展翻译)
- **多模型微调** (基于用户数据微调特定 skill)

> 项目名 novel2all 的暗示: **novel** 是起点, **2 all** 是终点。
