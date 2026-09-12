# novel2all

**novel-to-all 创作工具集** —— 长篇小说 / 短篇小说自动化创作工具，针对**长篇一致性**问题设计。

[![CI](https://github.com/YOUR_ORG/novel2all/workflows/CI/badge.svg)](https://github.com/YOUR_ORG/novel2all/actions)
[![CodeQL](https://github.com/YOUR_ORG/novel2all/workflows/CodeQL/badge.svg)](https://github.com/YOUR_ORG/novel2all/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-40_passing-brightgreen.svg)](tests/)

> 部署指南：[docs/DEPLOY.md](docs/DEPLOY.md)

## 核心特性

### 🧠 5 层长记忆系统（核心技术）

novel2all 的差异化竞争点是**自动化的长篇一致性**：

```
L1: 核心设定（永远加载）       ~3K tokens
L2: 角色状态（按需加载）       ~4K tokens
L3: 最近章节摘要（滑动窗口）   ~6K tokens
L4: 事件检索（向量检索）       ~5K tokens
L5: 知识图谱（tool call 查询）  按需
```

加上：

- **pre-write 一致性检查**（blocking 严重冲突）
- **post-write 自动提取 + 更新 tracking**
- **写中流式校验**

参考 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) § 长记忆系统。

### 📚 13 个 Skill + 7 个 Role

从 [oh-story-claudecode 0.7.10](https://github.com/zenstory-ai/oh-story-claudecode) fork 并适配 novel2all runtime：

| Skill | 用途 |
|---|---|
| `story` | 工具箱路由入口 |
| `story-setup` | 项目初始化 |
| `story-long-write` | 长篇写作 |
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
| `consistency-checker` | 一致性检查 |
| `story-researcher` | 资料研究 |
| `story-explorer` | 故事查询 |
| `chapter-extractor` | 章节提取 |

## 安装

```bash
# 需要 Python 3.12+
# 推荐用 uv 安装（10-100x 快于 pip）

# 1. 装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 装依赖
cd novel2all
uv sync

# 3. 配置 LLM API Key
export ANTHROPIC_API_KEY=sk-...        # 推荐 Claude Sonnet
# 或
export OPENAI_API_KEY=sk-...
export DEEPSEEK_API_KEY=sk-...

# 4. 验证
uv run novel2all version
```

## 3 分钟启动

```bash
# 1. 初始化项目
cd ~/my-novels/my-novel
novel2all setup --name "我的小说" --genre "玄幻" --style "古风古韵"

# 2. 编辑 创作设定.md + 设定/角色/*.md

# 3. 写细纲
# 编辑 大纲/细纲_第001章.md

# 4. 启动 CLI
novel2all write chapter 1

# 5. 启动 Web UI
novel2all web
# -> http://127.0.0.1:8765
```

## 技术栈

- **Python 3.12+** + uv（包管理）
- **Pydantic v2** + instructor（结构化输出 / 类型验证）
- **LiteLLM**（统一 LLM API，Anthropic / OpenAI / DeepSeek / ...）
- **NetworkX**（知识图谱，v0.22）
- **chromadb**（向量检索，v0.21）
- **FastAPI** + Jinja2 SPA（Web UI）
- **Typer**（CLI）
- **Rich**（终端美化）

## 项目结构

```
novel2all/
├── src/novel2all/
│   ├── core/             # 核心引擎
│   │   ├── memory/       # 5 层长记忆系统
│   │   ├── skill.py      # Skill 注册
│   │   ├── role.py       # Role 注册
│   │   ├── project.py    # 项目结构
│   │   └── provider.py   # LLM 抽象
│   ├── skills/           # 13 个 skill（fork 自 claudecode）
│   ├── roles/            # 7 个 role
│   ├── templates/        # 项目模板
│   ├── cli/              # CLI 入口
│   └── web/              # Web UI
├── tests/
├── docs/
└── pyproject.toml
```

## 路线图

- **v0.20** (当前) — 13 skill + 7 role + 5 层 memory 基础
- **v0.21** — 向量检索（chromadb）+ 智能摘要压缩
- **v0.22** — 知识图谱（NetworkX）+ 多模型路由
- **v0.30** — 多 agent 自我验证 + 完整 Web UI

详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## License

MIT — 与 oh-story-claudecode 0.7.10 一致。

## 与上游的关系

- 起点：从 [oh-story-claudecode 0.7.10](https://github.com/zenstory-ai/oh-story-claudecode) fork skill 内容（MIT）
- **不依赖任何上游 runtime**：novel2all 是自研 Python 引擎
- skill 内容是 markdown，移植过来后改写 DSH-specific 部分
- 上游变更不再自动同步（详见 [docs/FORK-DECISION.md](docs/FORK-DECISION.md)）
