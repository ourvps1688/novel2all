# Changelog

## [0.21.0] - 2026-09-12

### 🚧 v0.21 — Step 1：L4 检索 + L3 早期压缩

#### Added

- **`core/memory/retriever.py`** —— MemoryRetriever
  - 主路径：chromadb 语义检索
  - 降级路径 1：TF-IDF（纯 Python，无依赖）
  - 降级路径 2：keyword 匹配
  - API：`add_event` / `add_events` / `query` / `delete_chapter` / `count` / `wipe_disk`
  - 支持 chapter_range 与 event_type 过滤
  - 持久化到项目根 `.chroma/`
- **`core/memory/summarizer.py`** —— ChapterSummarizer
  - 滑动窗口压缩：1-10 全量、11-30 每 5 章、31+ 每 10 章
  - `extractive_summary` 不依赖 LLM，前 2 句 + 末 1 句 + 关键词句
  - `compress_range` 支持可选 LLM 滚动摘要（llm=None 时降级 extractive）
  - tiktoken 精确 token 计数
- **`manager.py` 升级**：
  - `search_relevant_events` 真正接入 retriever
  - `load_recent_chapters` 按档位折叠早期章节
  - `update_after_writing` 自动入库本章事件到 retriever
  - 暴露 `manager.retriever` / `manager.summarizer` 属性

#### Tests

- `tests/unit/test_retriever.py` —— 18 个测试（chromadb 模式 7 个 skip 在沙箱，TF-IDF/keyword 11 个全过）
- `tests/unit/test_summarizer.py` —— 22 个测试全过
- `tests/unit/test_memory_integration.py` —— 10 个测试全过
- **全套 101 个测试通过 + 7 个 skip**（沙箱 chromadb DLL 缺失，Linux CI 跑）
- 单章摘要 token 下降 ≥ 50%（V0.21 工程目标达成）
- ruff: All checks passed

#### Fixed

- pyyaml 6.0.3 namespace package 在 uv 安装时的 `__init__.py` 缺失（用 `uv pip install --force-reinstall --no-cache pyyaml` 修复）

## [0.20.0] - 2026-09-12

### 🎉 首发

novel2all 0.20 — novel-to-all 创作工具集。

从 oh-story-claudecode 0.7.10 fork 13 个 skill + 7 个 role，自研 Python runtime + 5 层长记忆系统。

### Added

- **5 层长记忆系统**：L1 核心设定 / L2 角色状态 / L3 最近章节 / L4 事件检索 / L5 知识图谱
- **自动 tracking 更新**：写完一章后 Extractor 自动提取 + merge 到 `_tracking-state.json`
- **pre-write 一致性检查**：critical 级问题阻断写作流
- **post-write 质量检查**：4 维度（一致性 / 文风 / 角色 / 结构）
- **13 个 Skill**（从 claudecode 0.7.10 fork）：story / story-setup / story-long-write / story-long-analyze / story-long-scan / story-short-write / story-short-analyze / story-short-scan / story-deslop / story-import / story-review / story-cover / browser-cdp
- **7 个 Role**：story-architect / character-designer / narrative-writer / consistency-checker / story-researcher / story-explorer / chapter-extractor
- **CLI**（Typer）：`setup` / `status` / `skills list` / `roles list` / `write chapter` / `web`
- **Web UI**（FastAPI + Jinja2 SPA）：项目状态 / skill 列表 / role 列表 / tracking 详情
- **项目模板**：玄幻 / 言情 / 短篇 3 个模板
- **LiteLLM 抽象**：支持 Anthropic / OpenAI / DeepSeek 等 100+ provider
- **instructor + Pydantic**：结构化输出，自动 merge tracking
- **GitHub Actions workflows**：CI（3 OS × 2 Python）/ Release / CodeQL / Dependabot
- **Docker 镜像支持**：docker/Dockerfile + release workflow 自动 build
- **完整文档**：README / ARCHITECTURE / ROADMAP / DECISIONS / CHANGELOG / DEPLOY
- **Makefile**：make install / test / lint / format / build / serve / verify-ci
- **LICENSE**：MIT

### Tests

- 36 unit tests + 4 e2e tests = 40 tests passing
- ruff lint: All checks passed
- Test matrix: 3 OS × 2 Python versions

### Notes

- 上游已冻结（详见 [vendor/oh-story-dsh-0.1.9/docs/FORK-DECISION.md](../vendor/oh-story-dsh-0.1.9/oh-story-dsh-0.1.9/docs/FORK-DECISION.md)）
- novel2all 不依赖任何上游 runtime（自研 Python 引擎）
- 完整写作流程在 v0.21 接入（v0.20 仅占位）

### License

MIT — 与上游 oh-story-claudecode 0.7.10 一致
