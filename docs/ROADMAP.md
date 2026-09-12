# novel2all 路线图

## v0.21 — 检索 + 摘要 + LLM 真写（进行中）

**目标**：解决"漏掉历史"问题，端到端跑通最小可用闭环

详细设计见 [`docs/v0.21-design.md`](v0.21-design.md)

### Step 1 — L4 检索 + L3 早期压缩 + 50 章验证 ✅（已完成 2026-09-12）

- [x] `core/memory/retriever.py` —— MemoryRetriever（chromadb → TF-IDF → keyword 三层降级）
- [x] `core/memory/summarizer.py` —— ChapterSummarizer（1-10 全量、11-30 每5章、31+ 每10章）
- [x] `manager.py` 接入 retriever（`search_relevant_events` 真用向量检索）
- [x] `manager.py` `load_recent_chapters` 按档位压缩早期章节
- [x] `manager.py` `_index_chapter_events` 自动入库新事件
- [x] 单元测试 51 个 + 集成测试 10 个，全过（沙箱 chromadb 7 个 skip，Linux CI 跑）
- [x] **50 章 e2e 模拟测试 8 个**：5 角色零丢失、3 伏笔 lifecycle、timeline 累积、retriever 召回、token 预算控制（无需真实 LLM）
- [x] ruff check + ruff format 全过
- [x] 单章摘要 token 下降 ≥ 50%（V0.21 工程目标达成）
- [x] **CI + CodeQL 全绿**（远端 main = `7234c29`）
- [x] 本地 109 passed + 7 skipped

### Step 2 — 完整 skill pipeline + LLM 真写（待开始，~5-6 天）

- [ ] `core/pipeline.py` —— WritingPipeline 编排（pre-write check → load memory → skill prompt → LLM stream → save → post-write check）
- [ ] CLI `write chapter` 接入真实 LLM（DEEPSEEK 优先）
- [ ] pipeline mock 测试 + 真实 LLM 跑通 1 章
- [ ] 流式输出到 console + 自动 extract + 入库

### Step 3 — Web SSE 流式 + 真正端到端（待开始，~4-5 天）

- [ ] `web/app.py` `/api/write/stream` SSE 端点
- [ ] 前端 EventSource 实时显示 LLM 输出
- [ ] `tests/e2e/test_real_llm_50_chapters.py`（替换 Step 1 的 mock）
- [ ] 监控 token 消耗 + 章节耗时

---

## v0.20 — 基础架构（已完成）

**目标**：跑通核心引擎 + 5 层 memory 框架 + 13 skill + 7 role 全部到位

### 已完成 ✅

- [x] `pyproject.toml` + uv 配置
- [x] `core/memory/`（types/tracker/extractor/verifier/manager）
- [x] `core/skill.py`（Skill 注册中心）
- [x] `core/role.py`（Role 注册中心）
- [x] `core/project.py`（项目结构）
- [x] `core/provider.py`（LLM 抽象，LiteLLM + instructor）
- [x] 13 个 Skill markdown（从 claudecode 0.7.10 fork）
- [x] 7 个 Role markdown
- [x] CLI 基础命令（setup/status/skills/roles/write/web）
- [x] Web UI 基础 SPA（FastAPI + Jinja2）
- [x] 项目模板（玄幻 / 言情 / 短篇）
- [x] README + ARCHITECTURE + ROADMAP

### 占位 ⚠️

- [ ] 完整 skill 调用流程（v0.21 接入）
- [ ] LLM 实际写作（v0.21 接入）

---

## v0.22 — 知识图谱 + 多模型路由

**目标**：解决"一致性"问题

| 模块 | 工作量 |
|---|---|
| `core/memory/graph.py`（NetworkX 知识图谱） | 3 天 |
| 自动从章节提取图谱节点 / 边 | 3 天 |
| `core/provider/router.py`（按任务选模型） | 2 天 |
| 多模型对比实验 | 2 天 |
| **合计** | **~2 周** |

---

## v0.30 — Self-verification loop

**目标**：解决"LLM 跑偏"问题

| 模块 | 工作量 |
|---|---|
| 写完后多 agent 审查（4 role 并行） | 3 天 |
| critical 问题自动回滚 | 2 天 |
| Web UI 完整化（实时进度条 / 角色面板 / 伏笔追踪） | 5 天 |
| 多用户支持（团队版） | 3 天 |
| **合计** | **~2 周** |

---

## v1.0 — GA

- 完整测试覆盖（unit + integration + e2e）
- 性能优化（流式响应延迟 < 500ms）
- 文档完善（用户指南 + API 参考）
- Docker 镜像发布
- 团队版部署工具

---

## 远期扩展（v2.0+）

- **短剧**（基于 novel2all 的角色 + 剧情，扩展视觉创作）
- **互动游戏**（基于 novel2all 的设定 + 伏笔，扩展分支剧情）
- **有声书**（基于 novel2all 的正文 + 角色，扩展 TTS）
- **多语言**（基于 novel2all 的结构，扩展翻译）
- **多模型微调**（基于用户数据微调特定 skill）

> 项目名 novel2all 的暗示：**novel** 是起点，**2 all** 是终点。
