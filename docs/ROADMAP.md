# novel2all 路线图

## v0.23 ✅ 数据驱动 LLM Provider 路由（已完成 2026-09-13）

**目标**: 从"行业经验推测"转为"一手文档 + 真实 benchmark"

**完成报告**: [`docs/v0.23-summary.md`](v0.23-summary.md)（9 项关键决策 / 4 commit 链路 / 路由架构图 / 50 章真实成本 / 数据驱动方法论）

**事实基础**: [`docs/llm-providers-truth.md`](llm-providers-truth.md)（一手文档原文 + 5 次错误反思）

**Benchmark 工具**: [`scripts/benchmark_llm.py`](../scripts/benchmark_llm.py) + [结果](../scripts/benchmark_results.md)

### 子版本

| 版本 | 内容 | commit |
|---|---|---|
| 0.23.0 | Truth 文档 + Benchmark 脚本 + 真实数据 | `9833af7` |
| 0.23.1 | DeepSeek 双模型路由 + 真实 CNY 价格 + thinking 控制 | `3d41034` |
| 0.23.2 | 现有模块接入 task=（pipeline/extractor/verifier） | `8e0a37e` |
| 0.23.3 | 收官报告（v0.23-summary.md） | `eb87db0` |
| **合计** | | **4 个 ALL_GREEN** |

### 关键决策（基于真实数据）

1. 三家全部支持双协议（OpenAI + Anthropic）
2. DeepSeek 价格是 CNY（不是 USD，便宜 7.2 倍）
3. DeepSeek 双模型覆盖全部 5 TaskType
4. WRITING 用 v4-pro（字数多 35%），其他用 flash（便宜 3.6 倍 + 快 2 倍）
5. flash/v4-pro 默认关 thinking（防止 reasoning 耗光 token）
6. 协议统一 OpenAI 兼容（零代码改动）
7. is_peak_hour() 自动判断时段（高峰 = off-peak ×2）

### 测试覆盖

- V0.22.5 基线：259 passed + 7 skipped
- V0.23.0 (Truth + Benchmark)：纯文档，未触发 pytest
- V0.23.1 (路由代码)：274 passed + 7 skipped（+15 router 新测试）
- V0.23.2 (task 接入)：**293 passed + 7 skipped**（+19 task 路由集成测试）

### 关键能力

- WRITING 路由到 `deepseek/deepseek-v4-pro`（字数多 35%）
- 其他 4 个 task 路由到 `deepseek/deepseek-flash`（便宜 3.6 倍）
- 双模型互为回退（高可用）
- 50 章小说真实成本：¥1.12（混合方案）/ ¥0.35（全 flash）
- 远端 main = `eb87db0`，CI + CodeQL ALL_GREEN

### V0.23 → V0.24 候选

- benchmark 加 minimax-M3 + 千问 qwen3.8-max 横向对比
- prompt cache 真实启用（验证 80% 命中假设，可降本 2-4 倍）
- CHANGELOG 拆 V0.23 子版本（已完成，0.23.0/0.23.1/0.23.2/0.23.3）

---

## v0.22 ✅ 知识图谱 + 模型路由基础（已完成 2026-09-12）

**目标**: 解决"一致性"问题

### 子版本

| 版本 | 内容 | commit |
|---|---|---|
| 0.22.1 | 设计文档（v0.22-design.md） | `cb1a952` |
| 0.22.2 | graph.py + 节点/边 Pydantic（36 tests） | `16da0bf` |
| 0.22.3 | Extractor 增量提取图谱（21 tests） | `18e6d32` |
| 0.22.4 | Manager.load_for_writing 集成 L5（20 tests） | `2c934dd` |
| 0.22.5 | ModelRouter + TaskType（40 tests） | `e268d70` |
| **合计** | | **5 个 ALL_GREEN** |

### 关键能力

- L5 知识图谱：5 类节点（Character/Location/Foreshadowing/Event/Item）+ 7 类边
- 5 TaskType + 双模型路由基础设施
- 远端 main = `e268d70`

---

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
