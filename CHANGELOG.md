# Changelog

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
