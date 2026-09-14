# novel2all

**novel-to-all 创作工具集** —— 长篇 / 短篇小说自动化创作工具，针对**长篇一致性**问题设计。

[![CI](https://github.com/ourvps1688/novel2all/workflows/CI/badge.svg)](https://github.com/ourvps1688/novel2all/actions)
[![CodeQL](https://github.com/ourvps1688/novel2all/workflows/CodeQL/badge.svg)](https://github.com/ourvps1688/novel2all/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-866_passing-brightgreen.svg)](tests/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

> 部署指南: [docs/DEPLOY.md](docs/DEPLOY.md)
> V1.0 GA 路线图: [docs/next-steps-roadmap.md](docs/next-steps-roadmap.md)
> V0.30.6 收官报告: [docs/v0.30.6-summary.md](docs/v0.30.6-summary.md)

## 核心特性

### 🧠 5 层长记忆系统 (V0.21 核心技术)

novel2all 的差异化竞争点是**自动化的长篇一致性**:

```
L1: 核心设定 (永远加载)       ~3K tokens
L2: 角色状态 (按需加载)       ~4K tokens
L3: 最近章节摘要 (滑动窗口)   ~6K tokens
L4: 事件检索 (向量检索)       ~5K tokens
L5: 知识图谱 (tool call 查询)  按需 (V0.22)
```

- **L4 实现**: `MemoryRetriever` 用 chromadb 语义检索，失败时降级到 TF-IDF → keyword 三层 fallback
- **L3 实现**: `ChapterSummarizer` 滑动窗口压缩，1-10 全量、11-30 每 5 章、31+ 每 10 章
- **L1/L2/L3 集成**: `MemoryManager.load_for_writing` 5 层合并 + token 预算控制
- **50 章零丢失**: 通过 `tests/e2e/test_50_chapters.py` 验证

### 🚀 端到端写作流 (V0.21)

`WritingPipeline` 编排完整流程:

```
pre-write check → load memory → skill prompt → LLM stream → save
                → extract → merge → post-write check
                → 4-agent 审查 (B1) → 自动回滚 (B2) → AdaptiveRouter 记录 (C3)
```

### 🌐 Web UI + SSE 实时流 (V0.21 + V0.30.6 B3)

启动 `novel2all web` 后:
- **项目状态** dashboard
- **角色面板** / **伏笔面板** / **章节列表**
- **SSE 流式写作** `/api/write/stream` 含 8 阶段进度条 + 实时字数/字秒/ETA
- **Cache 实时统计** `/api/cache/stats`（4 backend 选择）
- **Cache 智能推荐** `/api/cache/recommend`（V0.51 自动调优）
- **Prompt prefix cache** `/api/cache/prompt-stats`（V0.30.6 C1 实测节省 27%）
- **多用户登录** `/login`（V0.30.6 B5 Session + rate limit）

### 📚 13 个 Skill + 7 个 Role

从 [oh-story-claudecode 0.7.10](https://github.com/zenstory-ai/oh-story-claudecode) fork 并适配 novel2all runtime:

| Skill | 用途 |
|---|---|
| `story` | 工具箱路由入口 |
| `story-setup` | 项目初始化 |
| `story-long-write` | 长篇写作 (V0.21 默认 skill) |
| `story-long-analyze` | 长篇拆文 |
| `story-long-scan` | 长篇扫榜 |
| `story-short-write` | 短篇写作 |
| `story-short-analyze` | 短篇拆文 |
| `story-short-scan` | 短篇扫榜 |
| `story-deslop` | 去 AI 味 |
| `story-import` | 已有小说导入 |
| `story-review` | 多视角审查 |
| `story-cover` | 封面生成 |
| `browser-cdp` | 浏览器抓取 |

| Role | 用途 |
|---|---|
| `story-architect` | 故事架构 |
| `character-designer` | 角色设计 |
| `narrative-writer` | 叙事写手 |
| `consistency-checker` | 一致性检查 (V0.21 verifier 升级) |
| `story-researcher` | 资料研究 |
| `story-explorer` | 故事查询 |
| `chapter-extractor` | 章节提取 |

### 🛡️ V0.30.6 生产级特性

#### 4-agent 并行审查（V0.30.6 B1）

```
async.gather(
    Critical Auditor,    # 致命错误（事实/逻辑/设定/位置/跑题）
    Major Auditor,       # 中度问题（pacing/dialogue/consistency/OOC）
    Minor Auditor,       # 细节优化（writing/punctuation/ai_smell/format）
    Quality Judge,       # 5 维度评分（pacing/emotion/readability/immersion/ai_smell）
)
# 实测 ~100ms（vs 串行 ~400ms，4x 加速）
```

#### Critical 自动回滚（V0.30.6 B2）

```
manager.snapshot(chapter)            # 备份文件 + state
... pipeline 写章节 + 更新 state ...
if review.verdict == "fail":
    manager.rollback(snapshot)        # 恢复文件 + 反向 state 变更
```

#### Prompt prefix cache（V0.30.6 C1）

100 章 novel 写作实测：**95% hit rate，节省 27%**（input-only 90%+）。

#### 自适应路由（V0.30.6 C3）

按历史成功率/延迟/质量自动选模型（4 策略：best_avg / best_quality / best_speed / best_success）。

#### 多用户基础（V0.30.6 B5）

- Session HttpOnly + SameSite=Strict cookie（7 天）
- Rate limit 5 次/5 分钟防爆破
- PBKDF2-HMAC-SHA256 + 600K 迭代密码哈希
- ProjectMembership（owner / editor / viewer）

## 安装

### 方式 1：Docker（推荐 V1.0 GA）

```bash
# 1. 设置环境变量
export NOVEL2ALL_ADMIN_USER=admin
export NOVEL2ALL_ADMIN_PASS=<强密码>
export DEEPSEEK_API_KEY=sk-xxxxx

# 2. 启动
docker-compose up -d

# 3. 访问 http://localhost:8000
```

### 方式 2：源码安装（开发）

```bash
# 需要 Python 3.12+
# 推荐用 uv 安装 (10-100x 快于 pip)

# 1. 装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 装依赖
cd novel2all
uv sync --all-extras --dev

# 3. 配置 LLM API Key (写到 .env)
export DEEPSEEK_API_KEY=sk-...        # 推荐 (便宜 + 中文强)
export NOVEL2ALL_ADMIN_USER=admin
export NOVEL2ALL_ADMIN_PASS=secret
# 或
export ANTHROPIC_API_KEY=sk-...       # Claude Sonnet
export OPENAI_API_KEY=sk-...          # GPT-4o
export MINIMAX_API_KEY=xxxxx          # minimax

# 4. 验证
uv run novel2all version
```

## 3 分钟启动

```bash
# 1. 初始化项目
cd ~/my-novels/my-novel
novel2all setup --name "我的小说" --genre "玄幻" --style "古风古韵"

# 2. 编辑 创作设定.md + 设定/角色/*.md + 设定/文风.md

# 3. 写细纲
# 编辑 大纲/细纲_第001章.md

# 4. 启动 CLI 写第 1 章
novel2all write chapter 1
# -> 流式输出到 console，写完后自动 extract + merge tracking

# 5. 启动 Web UI (含 SSE 实时写作 + 多用户登录)
novel2all web
# -> http://127.0.0.1:8000
# -> 用 NOVEL2ALL_ADMIN_USER/PASS 登录
```

## 技术栈

- **Python 3.12+** + uv (包管理)
- **Pydantic v2** + instructor (结构化输出 / 类型验证)
- **LiteLLM 1.100+** (统一 LLM API, Anthropic / OpenAI / DeepSeek / ...)
- **chromadb** (向量检索, 三层降级到 TF-IDF)
- **FastAPI** + Jinja2 SPA (Web UI + SSE)
- **Typer** (CLI)
- **Rich** (终端美化)
- **tiktoken** (精确 token 计数)
- **networkx** (知识图谱, V0.22)

## 项目结构

```
novel2all/
├── src/novel2all/
│   ├── core/             # 核心引擎
│   │   ├── memory/       # 5 层长记忆系统 (types/tracker/extractor/verifier/manager)
│   │   │                 # + retriever (V0.21) + summarizer (V0.21)
│   │   ├── pipeline.py   # WritingPipeline (V0.21) 端到端编排
│   │   ├── skill.py      # Skill 注册
│   │   ├── role.py       # Role 注册
│   │   ├── project.py    # 项目结构
│   │   └── provider.py   # LLM 抽象 (LiteLLM)
│   ├── skills/           # 13 个 skill (fork 自 claudecode)
│   ├── roles/            # 7 个 role
│   ├── templates/        # 项目模板 (玄幻/言情/短篇)
│   ├── cli/              # CLI 入口
│   └── web/              # Web UI + SSE 端点 (V0.21)
├── tests/
│   ├── unit/             # 单元测试
│   ├── e2e/              # 端到端 (含 50 章长记忆)
│   └── smoke/            # smoke
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── v0.21-summary.md  # V0.21 收官报告
│   ├── v0.21-design.md   # V0.21 设计蓝图
│   ├── DEPLOY.md
│   ├── DECISIONS.md
│   └── CI-INTEGRATION.md
├── .github/workflows/    # CI / Release / CodeQL
├── docker/               # Docker 镜像
├── pyproject.toml
├── Makefile
└── README.md
```

## 测试与 CI

```bash
# 全套测试
uv run pytest tests/ -v
# 当前: 866 passed + 8 skipped (V1.0 GA 准备中)

# ruff
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 一键验证
make verify-ci   # ruff + pytest 等价

# 性能基准
uv run python scripts/benchmark_cache.py            # 4 backend benchmark
uv run python scripts/benchmark_cache_rtt.py        # Redis RTT 影响
uv run python scripts/benchmark_prompt_cache.py     # C1 prefix cache 收益
```

GitHub Actions (15 个 job):
- **Lint** (ruff check + format)
- **Type check** (mypy)
- **Test matrix** (6 个: windows / macos / linux × py3.12 / 3.13)
- **E2E** (playwright × 2 OS)
- **Build package** (uv build + twine check)
- **Cache benchmark** (advisory 模式，V0.52)
- **License headers / Skills+Roles manifest / CI integration scripts**
- **CodeQL** (Python analysis)

详见 [`.github/workflows/`](.github/workflows/)。

## 路线图

- **v0.21** ✅ (2026-09-12) — 检索 + 摘要 + LLM 真写 + Web SSE + UX 面板 (16 commits, 161 tests)
- **v0.22-v0.30** ✅ — 知识图谱 + 多模型路由 + LLM 路由优化
- **v0.33-v0.49** ✅ — Cache 工程化（17 commits，4 backend 跨 OS 跨进程）
- **v0.51-v0.52** ✅ — 智能推荐 + CI 性能守护（advisory 模式）
- **v0.30.6 B3-B6 + C1** ✅ — 实时进度条 + 章节导出 + Prompt Cache 节省 27%
- **v0.30.6 B1-B2 + B5 + C3** ✅ — 4-agent 审查 + 自动回滚 + 多用户 + 自适应路由
- **v1.0 GA** 🚧 (当前) — 完整测试 + 性能优化 + 文档完善 + Docker
- **v1.5** 📋 — WebUI 全面升级（React + Vite 替换 Jinja2）
- **v2.0** 📋 — 多模型扩展 + 商业化 + 市场发布

详见 [docs/next-steps-roadmap.md](docs/next-steps-roadmap.md)。

## License

MIT — 与上游 oh-story-claudecode 0.7.10 一致
