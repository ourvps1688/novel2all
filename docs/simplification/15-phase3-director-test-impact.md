# Phase 3 · 70+ director 测试影响面评估

> 前置调研文档，为 Phase 3「状态真相收敛」评估测试改写成本（对应计划 R-06 风险）。
> 本文为**只读调研**，未改动任何代码。依据 `02-architecture-simplification-plan.md` §4.3 R-06。

## 1. 分类计数总表（全部来自实际 glob/grep）

| 模式 | 文件数 | 说明 |
|---|---:|---|
| `director*` | 35 | 顶层 `directorXxx.test.js` |
| `novelDirector*` | 27 | 广义 director 子系统（runtime 编排 / 恢复 / 接管 / 重试 / 进度） |
| `autoDirector*` | 9 | 广义 director 子系统（跟进 / 审批 / 内存安全） |
| `chapter*` | 27 | 含 `novelProduction/` 子目录 2 个 |
| `character*` | 11 | — |
| `volume*` | 17 | — |
| `*Workflow*` | 15（2 个与 `director*` 重叠） | 含 `directorWorkflowStepCatalog/Modules` |
| `pipeline*`（前缀） | 2 | `novelProduction/pipelineExecutionLease`、`pipelineExecutorRecovery` |

**关键对照**：计划 R-06 警告的「70+ director 测试」= `director*`(35) + `novelDirector*`(27) + `autoDirector*`(9) = **71 个**，与实测完全吻合。匹配宇宙唯一文件总数约 **141 个**（含广义 director 子系统）。

## 2. (a) 断言枚举 / 翻译表 / `WORKFLOW_STEP_CATALOG` / `DirectorDisplayStageKey` 的测试

全仓 grep 证实：`server/tests/` 内只有 `directorWorkflowStepCatalog.test.js` 直接 import 这些目录/枚举符号，另有 2 个文件消费其派生产物：

| 文件 | 关键断言 file:line | 判读 |
|---|---|---|
| `server/tests/directorWorkflowStepCatalog.test.js` | import `WORKFLOW_STEP_CATALOG`/`WORKFLOW_DISPLAY_STAGES`/`WORKFLOW_CHECKPOINT_CATALOG`/`DIRECTOR_WORKFLOW_STEP_IDS`/`resolveWorkflowDisplayStage`（4-16）；断言 `entry.displayStage ∈ WORKFLOW_DISPLAY_STAGES`（35）；重复 `nodeKey` 须声明 aliases（64-67）；`resolveWorkflowDisplayStage` 映射 `book_contract_ready→story_planning`（180）、`story_macro→story_planning`（184） | **会改崩**：C21 合并展示枚举 + C22 去重 nodeKey + C19 展示阶段解析，全部失效 |
| `server/tests/directorWorkflowStepModules.test.js` | import `directorWorkflowStepModules`/`buildChapterPipelineWorkflowTemplate`/`buildDirectorPlanningWorkflowPlan`（7-33）；断言注册表同时含 `chapter.draft.repair` 与 `chapter.quality.repair` 且**两者 nodeKey 均为 `chapter_repair_node`**（46-47, 876-897） | **会改崩**：正是 C22 去重对象（重复 nodeKey） |
| `server/tests/directorDisplayStateBuilder.test.js` | import `buildDirectorDisplayState`（4-6）；断言 `stageKey`/`stageLabel`/`stepIndex` 由 factStepId/nodeKey/checkpoint/taskStage 解析（62-68, 115, 270-303）；**写死 display label `"节奏 / 拆章"`**（125，即 M5 标签不一致处） | **会改崩**：C21 合并枚举 + C19 标签统一直接命中 |

## 3. (b) 实例化或 mock `ChapterRuntimeCoordinator` 的测试

grep 确认仅 3 个文件引用该符号：

| 文件 | 关键 line | 判读 |
|---|---|---|
| `server/tests/chapterRuntimeCoordinator.test.js` | `require(.../ChapterRuntimeCoordinator.js)`（5）；`new ChapterRuntimeCoordinator({...})` **11+ 处**（274, 328, 472, 645, 785, 874, 914, 958, 992, 1034, 1088），并直接操控 `coordinator.streamOrchestrator`/`contentFinalizationService`/`buildRuntimePackage` | **会改崩**：C24（3→1，构造形态变化）使所有构造与依赖桩失效 |
| `server/tests/chapterRuntimeBoundary.test.js` | 读取 `ChapterRuntimeCoordinator.ts` 源码，断言其为 "thin facade"（<200 行、无动态 require）（24-28） | **脆弱但可保留**：合并若保持 facade 形态则成立 |
| `server/tests/novelServiceBoundary.test.js` | 断言 `novelCoreGenerationService.ts` **不含** `ChapterRuntimeCoordinator`（252-253） | **可保留**：与 C24 方向一致的反向断言 |

## 4. (c) 断言进度展示(R2/R3) / 质量债非阻断(R5) / 恢复行为(R4) 的测试

| 文件 | 关键断言 file:line | 判读 |
|---|---|---|
| `server/tests/directorDashboardViewBuilder.test.js` | 断言 `view.mode`(`running`/`waiting_user`/`failed`/`recovering`/`completed`) 与 `progressPercent` 与 `stageKey`（9, 98, 134, 160, 182, 224, 257, 266-267） | **会改崩**：R2/R3 主路径，C19/C21 改 stage→展示/进度映射 |
| `server/tests/directorRecoverySampleAudit.test.js` | **硬编码 `resumeTargetJson.stage` 值** `"basic"`(25,89)、`"chapter"`(43)、`"structured"`(58,74) | **会改崩**：统一 resumeTarget 契约会改变这些 stage key |
| `server/tests/directorChapterExecutionProgress.test.js` | `defer_and_continue`（R5 质量债非阻断，84-101）；`needs_repair as local recoverable state`（R4，17）；忽略已解决 stale `needs_repair`（140） | **脆弱，部分需改**：R5 被锁定不变，但依赖 stage/progress 计算 |
| `novelDirectorProgress.test.js` / `novelPipelineProgress.test.js` / `novelWorkflowStructuredOutlineProgress.test.js` | 命中 `progress` 关键词，断言进度展示(R2/R3) | **脆弱，大概率需改**（需确认是否 hardcode stage key） |
| `novelDirectorRecovery.test.js` / `novelWorkflowRecoveryNormalization.test.js` / `novelWorkflowCancellation.test.js` / `novelDirectorRetry.test.js` / `novelDirectorTakeover*` | 命中 `recovery/resume/replay` | **脆弱，需逐文件确认**：R4 行为锁定不变，但可能引用协调器/阶段名 |
| `server/tests/directorQualityRepairRisk.test.js` | `deferred quality debt as continuable regardless of count`（R5，8）；`replan notices blocking`（31）；`heavy repair notices as quality debt`（45） | **可保留**：直接断言 R5，Phase 3 锁定 R5 不变，未引用被删枚举 |

## 5. (d) 不相关 / Phase 3 不触动的测试

- `character*`(11) + `volume*`(17) = 28 个：全仓 grep 证实 `server/tests/` 内除 `directorWorkflowStepCatalog.test.js` 外无任何文件命中目录/枚举/协调器符号，**全部归入 (d)**。
- `chapter*` 绝大多数（除 `chapterRuntimeCoordinator`/`chapterRuntimeBoundary` 与个别 progress 断言外）为 (d)。
- `autoDirector*` 主体（跟进 / 审批 / 内存安全）为 (d)，grep 未命中协调器/目录符号。
- 多数 `novelDirector*` 非展示类 runtime 测试为 (d)。

## 6. 直接 import 将被收敛/删除模块的测试位置

- **被收敛/去重的目录与枚举（E5/E6/E9/E10/E11 + C21/C22）**
  - `server/tests/directorWorkflowStepCatalog.test.js:4-16` → `WORKFLOW_STEP_CATALOG` / `WORKFLOW_DISPLAY_STAGES` / `WORKFLOW_CHECKPOINT_CATALOG` / `DIRECTOR_WORKFLOW_STEP_IDS` / `resolveWorkflowDisplayStage`（来自 `shared/dist/types/directorWorkflowStepCatalog.js`）
  - `server/tests/directorWorkflowStepModules.test.js:7-33` → `directorWorkflowStepModules` / `buildChapterPipelineWorkflowTemplate` / `buildDirectorPlanningWorkflowPlan` / `DIRECTOR_EXECUTION_STEP_IDS`
  - `server/tests/directorDisplayStateBuilder.test.js:4-6` → `buildDirectorDisplayState`（内部消费 `DirectorDisplayStageKey` / `WORKFLOW_DISPLAY_STAGES`）
  - **`DirectorDisplayStageKey` 在 `server/tests/` 内无任何测试直接 import**（grep 证实）；它仅在 client + `DirectorDisplayStateBuilder.ts` 源内使用，C21 合并后导出位置迁移，属客户端改动风险。
- **`ChapterRuntimeCoordinator`（C24）**
  - `server/tests/chapterRuntimeCoordinator.test.js:5`（+ 11 处 `new`）
  - `server/tests/chapterRuntimeBoundary.test.js:25`
  - `server/tests/novelServiceBoundary.test.js:252-253`（反向断言"不含"）
- **统一 resumeTarget 契约（C19 产出 `NovelWorkflowResumeTarget`，`shared/types/novelWorkflow.ts:39-48`）**
  - `server/tests/directorRecoverySampleAudit.test.js:25,43,58,74,89`（硬编码 stage 值）
  - 另有 17 个文件命中 `resumeTarget` 关键词（如 `autoDirectorFollowUp*`、`novelDirectorRetry`、`novelWorkflowRuntime`、`novelWorkflowCancellation`、`shortStoryWorkflowContracts`、`p0bRealPrismaChain` 等），多为字段读取而非枚举断言，需逐文件甄别。

## 7. 结论

**预计需重写：约 10–16 个；可保留：约 85–90 个**（在 ~141 个匹配文件内，广义 director 子系统 71 个）。

- **确定需重写（强证据，必崩）— 6 个**：`directorWorkflowStepCatalog`、`directorWorkflowStepModules`、`directorDisplayStateBuilder`、`chapterRuntimeCoordinator`、`directorDashboardViewBuilder`、`directorRecoverySampleAudit`。
- **高风险需大改（progress 展示受 C19 牵连）— 约 4 个**：`directorChapterExecutionProgress`、`novelDirectorProgress`、`novelPipelineProgress`、`novelWorkflowStructuredOutlineProgress`。
- **需逐文件确认（recovery/takeover/retry，R4 锁定多数可保留）— 约 8 个**：`novelDirectorRecovery`、`novelWorkflowRecoveryNormalization`、`novelWorkflowCancellation`、`novelDirectorRetry`、`novelDirectorTakeover*`、`directorRuntimePolicy` 等。
- **可保留**：`character*`(11) + `volume*`(17) 全部 + `chapter*` 绝大多数 + `autoDirector*` 主体 + `novelServiceBoundary` + `directorQualityRepairRisk` + 多数 `novelDirector` 非展示类。

### Highest-risk Top 5（改动幅度 × 断言脆弱度）
1. `chapterRuntimeCoordinator.test.js` — 11+ 处 `new` 构造函数 + 直接操控内部依赖，C24 合并后几乎必然全文件重写。
2. `directorWorkflowStepCatalog.test.js` — 直接断言将被 C21/C22 收敛/去重的目录、`displayStage`、nodeKey 别名。
3. `directorWorkflowStepModules.test.js` — 直接断言 `chapter.draft.repair`/`chapter.quality.repair` 双 nodeKey 重复（C22 去重对象）。
4. `directorDisplayStateBuilder.test.js` — 断言 `stageKey`/`stepIndex` 与写死的 display label `"节奏 / 拆章"`，C21/C19 直接命中。
5. `directorDashboardViewBuilder.test.js` — 断言 `mode`/`progressPercent`/`stageKey` 展示映射（R2/R3 主路径，C19 触碰）。

（补充：`directorRecoverySampleAudit.test.js` 因硬编码 `resumeTarget` stage 值，属同等级风险，列第 6。）

## 8. 实施建议（待 Phase 3 任务表确认）

1. **先评估、后动手**：C19/C21/C22（枚举/翻译表收敛）与 C24（Coordinator 合并）是测试失效主因，应在对应代码改动**之前**先建立这些测试的「新期望基线」，避免一次性失效淹没真实回归。
2. **分阶段改写**：先改 6 个确定崩的，再处理 4 个 progress 高风险，最后逐文件确认 8 个 recovery 类。
3. **保留 R5/R4 锁定断言**：`directorQualityRepairRisk.test.js` 等直接断言质量债非阻断/恢复行为的测试应作为回归护栏，Phase 3 不得改动其语义（AGENTS.md 红线）。
