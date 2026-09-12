# novel2all

**novel-to-all 创作工具集** —— 长篇 / 短篇小说自动化创作工具，针对**长篇一致性**问题设计。

[![CI](https://github.com/ourvps1688/novel2all/workflows/CI/badge.svg)](https://github.com/ourvps1688/novel2all/actions)
[![CodeQL](https://github.com/ourvps1688/novel2all/workflows/CodeQL/badge.svg)](https://github.com/ourvps1688/novel2all/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-161_passing-brightgreen.svg)](tests/)
[![v0.21](https://img.shields.io/badge/version-0.21-blue.svg)](docs/v0.21-summary.md)

> 部署指南: [docs/DEPLOY.md](docs/DEPLOY.md)
> V0.21 收官报告: [docs/v0.21-summary.md](docs/v0.21-summary.md)

## 核心特性

### 🧠 5 层长记忆系统 (核心技术)

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

加上:
- **pre-write 一致性检查** (critical / warning / info 三级)
- **post-write 自动提取** + merge tracking
- **verifier 智能分级**: 软问题 (节奏/文风) 不再误报为 critical

参考 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) § 长记忆系统。

### 🚀 端到端写作流 (V0.21 新增)

`WritingPipeline` 编排完整流程:

```
pre-write check → load memory → skill prompt → LLM stream → save
                → extract → merge → post-write check
```

- `stream_callback` 让调用方实时接收每个 LLM chunk
- 失败类型清晰: `OutlineNotFoundError` / `BlockingIssuesError` / `LLMAuthError`
- 不依赖真实 LLM (mock provider 也能跑完整流程)

### 🌐 Web UI + SSE 实时流 (V0.21 新增)

启动 `novel2all web` 后:
- **项目状态** dashboard (项目名/题材/文风/章节数/角色/伏笔/时间线)
- **角色面板** 卡片网格 (按最近更新排序，dead 状态红框)
- **伏笔面板** 4 状态过滤 (all / active / advanced / revealed / abandoned)
- **章节详情弹窗** 点击章节列表项查看完整内容
- **SSE 流式写作** `/api/write/stream` 1920 个 chunk 事件实时拼接

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

## 安装

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
# 或
export ANTHROPIC_API_KEY=sk-...       # Claude Sonnet
export OPENAI_API_KEY=sk-...          # GPT-4o
# 并设置默认模型
export NOVEL2ALL_MODEL=deepseek/deepseek-chat

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

# 5. 启动 Web UI (含 SSE 实时写作)
novel2all web
# -> http://127.0.0.1:8000
# -> 打开后: 角色面板 + 伏笔面板 + 点击章节看详情
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
# 161 passed + 7 skipped (沙箱 chromadb DLL 缺失)

# ruff
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 一键验证
make verify-ci   # ruff + pytest + tsc 等价
```

GitHub Actions (12 个 job):
- **Lint** (ruff check + format)
- **Type check** (mypy)
- **Test matrix** (6 个: windows / macos / linux × py3.12 / 3.13)
- **Build package** (uv build + twine check)
- **License headers / Skills+Roles manifest / CI integration scripts**
- **CodeQL** (Python analysis)

详见 [docs/CI-INTEGRATION.md](docs/CI-INTEGRATION.md) 和 [`.github/workflows/`](.github/workflows/)。

## 路线图

- **v0.21** ✅ (2026-09-12) — 检索 + 摘要 + LLM 真写 + Web SSE + UX 面板 (16 commit, 161 tests)
- **v0.22** — 知识图谱 (NetworkX) + 多模型路由 (~2 周)
- **v0.30** — Self-verification loop (多 agent 审查 + 自动回滚) + 完整 Web UI (~2 周)
- **v1.0** — GA (性能优化 / 文档 / Docker / 团队版)

详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## License

MIT — 与上游 oh-story-claudecode 0.7.10 一致
