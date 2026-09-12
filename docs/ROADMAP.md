# novel2all 路线图

## v0.20 — 基础架构（当前）

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

## v0.21 — 向量检索 + 智能摘要

**目标**：解决"漏掉历史"问题

| 模块 | 工作量 |
|---|---|
| `core/memory/retriever.py`（chromadb 集成） | 3 天 |
| `core/memory/summarizer.py`（早期章节压缩摘要） | 2 天 |
| 完整 skill 调用 pipeline | 3 天 |
| 流式输出到 Web UI（SSE） | 2 天 |
| 端到端测试（跑通 50 章流程） | 3 天 |
| **合计** | **~2 周** |

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
