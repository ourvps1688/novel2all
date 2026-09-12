# Changelog

## [0.23.0] - 2026-09-13

### V0.23.0 — 数据驱动 LLM Provider 路由（基于真实 benchmark + 一手文档）

**核心方法论**：从 V0.22.5 的"行业经验推测"转为"一手文档 + 真实 benchmark"。

#### [0.23.0] Truth 文档 + Benchmark 脚本（commit 9833af7）

- **docs/llm-providers-truth.md** (~6000 字符，10 节)
  - §1 三家协议支持矩阵 + 5 次错误反思（千问没 Anthropic、DeepSeek 单协议、minimax 单协议、Anthropic caching 杀手级、USD vs CNY）
  - §2 DeepSeek 完整价格表（CNY，off-peak/peak 时段，原文逐字抄录）
  - §3 千问 DashScope 价格表 + **千问是模型市场**（含 DeepSeek/GLM/Kimi/minimax）
  - §4 minimax Token Plan（¥119/月 = 18 亿 token）+ 按量计费
  - §5 横向价格对比 + 全市场最低价格点
  - §6 novel2all 路由策略推荐（DeepSeek 双模型覆盖 5 TaskType）
  - §7 当前代码状态 + V0.23 待做
  - §8 **不要做的事**（防止重蹈覆辙）
  - §9 数据快照 + 核实命令
  - §10 引用
- **scripts/benchmark_llm.py** (~400 行)
  - 横向对比 4 个候选模型 × 5 TaskType = 20 次调用
  - 真实调 litellm.acompletion + 真实 usage 数据
  - 自动应用模型特殊配置（v4-pro 显式 `thinking:disabled` 防 reasoning 耗光 token）
  - 支持 dry-run / 单 task / 模型筛选
- **scripts/benchmark_results.md + .json** 10 次真实调用结果（2 模型 × 5 task）

#### [0.23.1] DeepSeek 双模型路由（commit 3d41034）

- **core/provider_router.py** 重写（+186 行）
  - `DEFAULT_TASK_ROUTES`: WRITING → v4-pro（字数多 35%），其他 → flash（便宜 3.6 倍）
  - `DEFAULT_TASK_FALLBACKS`: 双模型互为回退（v4-pro ↔ flash）
  - `MODEL_PRICING`: DeepSeek 真实 CNY 价格表（off-peak/peak × cache_hit/miss = 12 字段）
  - 新增 `THINKING_CONTROL` 字典（v4-pro + flash 都禁用 thinking）
  - 新增 `is_peak_hour()` 函数（zoneinfo + UTC+8 fallback）
  - 新增 `get_thinking_control(model)` 辅助
  - `ModelRouter.cost_estimate` 加 `cache_hit` 参数 + 自动选 off-peak/peak
- **core/provider.py** 扩展（+54/-9 行）
  - `LLMProvider.complete / complete_structured / stream` 自动应用模型 thinking 控制
  - 新增 `_get_extra_body(model_name)` 私有方法（lazy import router 避免循环）
- **tests/unit/test_provider_router.py** 重写（+347/-132 行）
  - 55 个测试（V0.22.5 是 40，+15 新增）
  - TestDefaultRoutesV023 / TestModelPricingV023 / TestCostEstimateV023 / TestIsPeakHour / TestThinkingControl / TestLLMProviderGetExtraBody

#### [0.23.2] 现有模块接入 task=（commit 8e0a37e）

- **core/pipeline.py**（+3/-1）：WritingPipeline._stream_chapter 加 `task=TaskType.WRITING`
- **core/memory/extractor.py**（+3/-1）：Extractor.extract 加 `task=TaskType.EXTRACTION`
- **core/memory/verifier.py**（+6/-2）：pre_write_check + post_write_check 加 `task=TaskType.CONSISTENCY`
- **tests/unit/test_task_routing_integration.py**（+318 行，19 个测试）
  - MockLLM 记录 kwargs 验证 task= 参数
  - WRITING → v4-pro，其他 → flash
  - thinking 自动应用
  - 源码扫描验证 3 模块都 import + 使用 TaskType

#### [0.23.3] 收官报告（commit eb87db0）

- **docs/v0.23-summary.md** 12 节完整收官
  - 目标 / 9 项关键决策 / 4 commit 链路 / 路由架构图 / 50 章真实成本 / 关键技术细节 / 限制与未来工作 / 测试演进 / CI 状态
  - 致谢：5 次错误反思 + 数据驱动方法论

#### Metrics

- **测试**：259 (V0.22.5) → 274 (路由代码) → **293 (task 接入)** passed + 7 skipped
- **远端 main 演进**：`e268d70` → `9833af7` → `3d41034` → `8e0a37e` → `eb87db0`
- **4 个 commit 全部 ALL_GREEN**（3 个 code commit 跑 12 个 CI job）
- **50 章小说真实成本**：
  - 全 flash：**¥0.35**
  - 混合（WRITING v4-pro + 其他 flash）：**¥1.12**
  - 全 v4-pro：¥1.25

#### Key Insights

1. **DeepSeek 价格是 CNY**（不是 USD，便宜 7.2 倍）
2. **三家全部支持双协议**（OpenAI + Anthropic）
3. **v4-pro 默认 thinking 模式会耗光 token**（实测 30.52s 输出 0 字），必须显式禁用
4. **DeepSeek flash cache hit ¥0.02/M** 是全市场最低
5. **当前代码已经是 OpenAI 兼容 messages 风格**，零代码改动即可迁移到其他家模型

#### Future Work (V0.24+)

- benchmark 加 minimax-M3 + 千问 qwen3.8-max 横向对比
- prompt cache 真实启用（验证 80% 命中假设，可降本 2-4 倍）
- CHANGELOG 拆 V0.23 子版本（与 v0.21-summary 对齐）

---

## [0.21.1] - 2026-09-12

### Step 1: L4 检索 + L3 早期压缩

#### Added

- **core/memory/retriever.py** MemoryRetriever
  - 主路径: chromadb 语义检索
  - 降级路径 1: TF-IDF (纯 Python, 无依赖)
  - 降级路径 2: keyword 匹配
  - API: add_event / add_events / query / delete_chapter / count / wipe_disk
  - 支持 chapter_range 与 event_type 过滤
  - 持久化到项目根 .chroma/
- **core/memory/summarizer.py** ChapterSummarizer
  - 滑动窗口压缩: 1-10 全量、11-30 每 5 章、31+ 每 10 章
  - extractive_summary 不依赖 LLM, 前 2 句 + 末 1 句 + 关键词句
  - compress_range 支持可选 LLM 滚动摘要 (llm=None 时降级 extractive)
  - tiktoken 精确 token 计数
- **manager.py** 升级:
  - search_relevant_events 真正接入 retriever
  - load_recent_chapters 按档位折叠早期章节
  - update_after_writing 自动入库本章事件到 retriever
  - 暴露 manager.retriever / manager.summarizer 属性

#### Tests

- tests/unit/test_retriever.py - 18 个测试 (chromadb 模式 7 个 skip 在沙箱, TF-IDF/keyword 11 个全过)
- tests/unit/test_summarizer.py - 22 个测试全过
- tests/unit/test_memory_integration.py - 10 个测试全过
- **全套 101 个测试通过 + 7 个 skip** (沙箱 chromadb DLL 缺失, Linux CI 跑)
- 单章摘要 token 下降 ≥ 50% (V0.21 工程目标达成)
- ruff: All checks passed

#### Fixed

- pyyaml 6.0.3 namespace package 在 uv 安装时的 __init__.py 缺失 (用 `uv pip install --force-reinstall --no-cache pyyaml` 修复)

---

## [0.21.2] - 2026-09-12

### Step 2: 完整 skill pipeline + LLM 真写 + verifier 优化

#### Added

- **core/pipeline.py** WritingPipeline
  - 编排: pre-write check → load memory → skill prompt → LLM stream → save → extract → merge → post-write check
  - stream_callback 让 CLI / Web SSE 实时接收 LLM chunk
  - 失败类型: OutlineNotFoundError / BlockingIssuesError / LLMAuthError
  - 不依赖真实 LLM (用 mock provider 也能跑完整流程)
- **core/provider.py** LLMProvider 升级
  - 默认 model 改 deepseek/deepseek-chat (litellm 1.100+ 要求前缀)
  - 模块加载时 _strip_proxy_env() 解决沙箱代理破坏 Bearer 问题

#### Changed

- **CLI write chapter** 接入 pipeline
  - 真实调用 DeepSeek 流式生成
  - min-chars 参数控制最低字数
  - --skip-pre-write flag 跳过 pre-write check
- **verifier PRE/POST prompt 重写**
  - 明确 critical 必须满足 4 类硬伤 (角色存在性 / 位置时间 / 伏笔设定 / 文风)
  - warning / info 适用场景明确定义
  - 强调宁缺毋滥: 判 critical 前必须有明确证据
  - _filter_issues() 后处理兜底非法 severity + 去重
  - _state_to_text 增强 (角色 last_updated_chapter、伏笔 status)

#### Fixed

- LLM 调用问题 (litellm 1.100.1 缺文件 → `uv pip install --force-reinstall --no-cache litellm`)
- Pre-write 过度报警: 之前 6 个 critical → 0 个 critical、4 个 warning (全部正确分类)
- .gitignore 字符类误伤 pipeline.py (删除短名模式 + 加 .gitattributes 强制 LF)

#### Tests

- tests/unit/test_pipeline.py: 6 个测试 (mock LLM 完整流程)
- tests/unit/test_verifier_severity.py: 21 个测试 (PRE/POST prompt 验证 + _filter_issues + 边界)
- 真实 LLM 端到端: DeepSeek 写第 1 章 2900+ 字, verifier 报 4 个正确分类 warning

---

## [0.21.3] - 2026-09-12

### Step 3: Web SSE 流式写作 + UX 面板

#### Added

- **web/app.py SSE 端点** GET /api/write/stream
  - 事件类型: started / chunk / progress / pre_write_check / post_write_check / done / error
  - asyncio.Queue 桥接 sync stream_callback → async generator
  - run_pipeline() 后台 task + finally put sentinel(None) 保证异常退出
  - FastAPI StreamingResponse(media_type="text/event-stream")
  - 错误事件含 code 字段供前端分类
- **新增 API 端点**:
  - GET /api/chapters: 列出已写章节 (章节号 / 字数 / 首句 / 文件名)
  - GET /api/outlines: 列出细纲
  - GET /api/chapter/{chapter}/content: 返回章节完整内容
- **前端 SPA 升级** (重写 INDEX_HTML 41K 字符):
  - 角色面板: 卡片网格, 按 last_updated_chapter 倒序, dead 状态红色边框
  - 伏笔面板: 4 个状态过滤按钮 (all/active/advanced/revealed/abandoned)
  - 章节详情弹窗: 点击列表项 → 模态弹窗 (ESC / 遮罩关闭)
  - 写章节 SSE 实时显示 + 进度日志 + 完成态
  - 章节列表加 hover + cursor pointer

#### Tests

- tests/unit/test_web_sse.py: 11 个测试 (sse_event 格式化 + 端点错误处理 + mock LLM 完整事件流)
- tests/unit/test_web_api.py: 7 个测试 (章节内容端点 + 现有端点回归)
- 真实 LLM 端到端: DeepSeek 1920 个 chunk 事件 / 30.8s 流完 2802 字 / 章节文件 8153 bytes

#### Fixed

- TestClient 死锁: 异常时 sentinel 没 put 导致 event_stream 阻塞 → finally 块确保
- pipeline_task.exception() 提取: error 事件显示真实异常类型 + 消息

---

## [0.21.4] - 2026-09-12

### V0.21 归档 + 收官

#### Added

- **docs/v0.21-summary.md** V0.21 完整收官报告
  - 目标 / 关键决策 (8 项) / 16 commit 链路 / 架构总览
  - 5 层 memory + 端到端写作流 + UX 面板
  - 161 个测试 + 12 个 CI job 覆盖
  - 关键技术经验 (GitHub Actions / chromadb / litellm / ruff / TestClient / .gitignore)
  - V0.22 路线
- **docs/v0.21-design.md** (已存在, Step 2/3 设计蓝图)
- **CHANGELOG.md** 拆分 v0.21 为 0.21.1 / 0.21.2 / 0.21.3 / 0.21.4 四个子版本
- **ROADMAP.md** V0.21 标题标 ✅ + 引用 summary 文档
- **README.md** 反映 V0.21 完整能力 (CLI / Web SSE / 5 层 memory / 角色/伏笔面板 / 章节详情弹窗)

#### Metrics

- 测试: 101 (Step 1) → 115 (Step 2) → 136 (verifier) → 154 (SSE) → 161 (UX)
- 远端 main 演进: cb968af → 06d0455 → ... → 56d8455
- 16 个 commit 全部 ALL_GREEN

---

## [0.20.0] - 2026-09-12

### 首发

novel2all 0.20 — novel-to-all 创作工具集。

从 oh-story-claudecode 0.7.10 fork 13 个 skill + 7 个 role，自研 Python runtime + 5 层长记忆系统。

### Added

- **5 层长记忆系统**: L1 核心设定 / L2 角色状态 / L3 最近章节 / L4 事件检索 / L5 知识图谱
- **自动 tracking 更新**: 写完一章后 Extractor 自动提取 + merge 到 _tracking-state.json
- **pre-write 一致性检查**: critical 级问题阻断写作流
- **post-write 质量检查**: 4 维度 (一致性 / 文风 / 角色 / 结构)
- **13 个 Skill** (从 claudecode 0.7.10 fork): story / story-setup / story-long-write / story-long-analyze / story-long-scan / story-short-write / story-short-analyze / story-short-scan / story-deslop / story-import / story-review / story-cover / browser-cdp
- **7 个 Role**: story-architect / character-designer / narrative-writer / consistency-checker / story-researcher / story-explorer / chapter-extractor
- **CLI** (Typer): setup / status / skills list / roles list / write chapter / web
- **Web UI** (FastAPI + Jinja2 SPA): 项目状态 / skill 列表 / role 列表 / tracking 详情
- **项目模板**: 玄幻 / 言情 / 短篇 3 个模板
- **LiteLLM 抽象**: 支持 Anthropic / OpenAI / DeepSeek 等 100+ provider
- **instructor + Pydantic**: 结构化输出，自动 merge tracking
- **GitHub Actions workflows**: CI (3 OS × 2 Python) / Release / CodeQL / Dependabot
- **Docker 镜像支持**: docker/Dockerfile + release workflow 自动 build
- **完整文档**: README / ARCHITECTURE / ROADMAP / DECISIONS / CHANGELOG / DEPLOY
- **Makefile**: make install / test / lint / format / build / serve / verify-ci
- **LICENSE**: MIT

### Tests

- 36 unit tests + 4 e2e tests = 40 tests passing
- ruff lint: All checks passed
- Test matrix: 3 OS × 2 Python versions

### Notes

- 上游已冻结 (详见 vendor/oh-story-dsh-0.1.9/oh-story-dsh-0.1.9/docs/FORK-DECISION.md)
- novel2all 不依赖任何上游 runtime (自研 Python 引擎)
- 完整写作流程在 v0.21 接入 (v0.20 仅占位)

### License

MIT — 与上游 oh-story-claudecode 0.7.10 一致
