# Phase 3 任务分解表（T08+）

> 本表是 Phase 3「状态真相收敛」的实施分解，依据三份前置调研产出：
> - `13-phase3-c24-coordinator-input-diff.md`（C24 入参差异）
> - `14-phase3-resume-target-contract.md`（统一 resumeTarget 契约）
> - `15-phase3-director-test-impact.md`（70+ director 测试影响面）
>
> 上游计划：`02-architecture-simplification-plan.md` §4.3（P2 状态真相收敛）、§8.3 Q4。
> 本表为**计划文档，不含代码改动**。任务 ID 以 `T3-N` 为主键；「计划项」列映射原 P2 表的 C 编号（C19/C21/C22 编号源自 §4.3 P2，C20/C23/C24 为原文明示）。

## 1. 范围与边界

**Phase 3 是什么**：「让同一件事只有一套名字和一个执行器」——状态真相收敛。零数据动作（不动 Prisma schema / migration / 任何 DROP）。

**纳入**：
- 真相表 20 处字面定义 → ≤6；翻译表 6 处 → 0~1
- `ChapterRuntimeCoordinator` 实例 3→1（全仓 7 处 → 1 单例）
- `NovelWorkflowResumeTarget` 统一契约（`lane` 必填 + 单一 composer/merge + 消除 seedPayload 镜像）
- `stage` 展示词表统一、`nodeKey` 去重、进度展示（R2/R3）映射归一
- `shared/types` 巨文件（`directorRuntime.ts` 1277 行、`novel.ts` 1161 行）随枚举收敛自然瘦身

**明确不做（Phase 3 范围外）**：
- **C20 三条 lane 收敛** → 下一阶段（§8.3 Q4：PM 建议先做入口收敛，lane 收敛推迟）
- **C23 `workflow.takeover.execute` 删除** → 随 lane 收敛下一阶段，本轮不删
- **Phase 4 数据动作**（DROP 21 张 drama/comic 表 + 12 张零引用候选表）→ 永不纳入 Phase 3

## 2. 执行顺序与批次

```
Batch A（低风险、可逆、测试影响小，先收口）
  T3-1  Coordinator 3→1 合并            ── 依赖：入参差异文档(✓)
  T3-2  resumeTarget 契约（类型+composer）── 依赖：resumeTarget 文档(✓)

Batch B（真相表/翻译表收敛，中高，测试失效集中）
  T3-3  C21 展示枚举合并               ── 依赖：T3-2（统一 stage 归一器）
  T3-4  C22 nodeKey 去重               ── 依赖：T3-3
  T3-5  真相表20→≤6 / 翻译表6→0~1      ── 依赖：T3-3、T3-4

Batch C（进度展示映射，挨着主路径）
  T3-6  C19 进度展示 R2/R3 归一        ── 依赖：T3-3（统一 stage 词表）
  T3-7  R5/R4 护栏固化（贯穿全程）      ── 无依赖

终态校验：构建 + 启动 + 走通「灵感 → 第一章产出 → 书架可读」
```

> **测试失效处置纪律（来自 doc15）**：C19/C21/C22/C24 是测试失效主因。每个涉及测试失效的任务，**先建新期望基线、再改代码**，避免一次性失效淹没真实回归。确定的 6 个必崩文件 + 4 个高风险文件优先处理。

## 3. 任务分解主表

| ID | 标题 | 计划项 | 风险 | 测试影响（doc15） | 依赖 |
|---|---|---|---|---|---|
| T3-1 | ChapterRuntimeCoordinator 3→1 合并 | C24 | 低 | `chapterRuntimeCoordinator.test.js`（11+ 处 `new`，最高危 #1）；`chapterRuntimeBoundary` 可保留 | 入参差异文档 ✓ |
| T3-2 | resumeTarget 统一契约（类型+composer+merge+去镜像） | C19 产出物 | 中 | `directorRecoverySampleAudit.test.js`（硬编码 stage，#6）；客户端 7 处需回归 | resumeTarget 文档 ✓ |
| T3-3 | C21 展示枚举合并（displayStage / DirectorDisplayStageKey） | C21 | 中高 | `directorWorkflowStepCatalog.test.js`、`directorDisplayStateBuilder.test.js`（写死 label，#2/#4） | T3-2 |
| T3-4 | C22 nodeKey 去重（chapter.draft.repair / quality.repair） | C22 | 中 | `directorWorkflowStepModules.test.js`（#3） | T3-3 |
| T3-5 | 真相表 20→≤6 / 翻译表 6→0~1 + shared/types 瘦身 | — | 高 | 间接影响上述全部目录类测试；`directorWorkflowStepCatalog.test.js` 再触 | T3-3、T3-4 |
| T3-6 | C19 进度展示 R2/R3 归一 | C19 | 中高 | `directorDashboardViewBuilder.test.js`（#5，mode/progressPercent/stageKey） | T3-3 |
| T3-7 | R5/R4 护栏固化（质量债非阻断 + 恢复行为不变） | — | 低 | `directorQualityRepairRisk.test.js` 不得改语义（回归护栏） | 无 |

## 4. 逐任务详解

### T3-1 · ChapterRuntimeCoordinator 3→1 合并（C24）
- **范围**：删 `NovelApplicationServices.ts:60` 的 `resolveAuditIssues` 注入，B 退化为默认构造；将 A(:59)/B(:60)/C(`novelCorePipelineService.ts:33`) 及范围外 4 处（`NovelGenerationService.ts:15`、`NovelPipelineService.ts:15`、`NovelPipelineExecutor.ts:86`、`novelCoreReviewService.ts:54-56`）统一引用同一模块级默认单例。
- **必须保留**：`ChapterRepairStreamRuntime.ts:240-241` 的 `?? auditService.resolveIssues` 回退（安全网）。
- **风险**：低。三实例在 14 个依赖上完全一致，唯一差异 `resolveAuditIssues` 注入与默认回退最终同落 `auditService.resolveIssues` 单例（doc13 §3 已核实）。
- **验收**：`chapterRuntimeBoundary.test.js` 的 "thin facade" 断言仍成立；repair 场景 `auditIssueIds` 解析正确；全仓不再有 7 处分散 `new`。
- **测试影响**：`chapterRuntimeCoordinator.test.js` 11+ 处构造与依赖桩随形态收敛改写（doc15 最高危 #1）。

### T3-2 · resumeTarget 统一契约（C19 产出物）
- **范围**（来自 doc14 §4）：
  1. `shared/types/novelWorkflow.ts:39-48` 的 `lane` 由可选改**必填**；其余字段名不动。
  2. 新增 `composeResumeTarget(input)`（`novelWorkflow.shared.ts`），接受 `workspaceTaskId`/`directorTaskId`/`taskId` 别名与 `stage`/`currentStage`/`phase`/`currentItemKey` 别名，内部归一为规范形状。
  3. `mergeResumeTargets` 保留 `novelWorkflow.helpers.ts:105` 为唯一实现，删 `novelDirectorChapterTitleRepairRuntime.ts:25`、`:53`、`NovelWorkflowTaskAdapter.ts:110` 三份复制；`parseResumeTargetLike` 合并为单一导出。
  4. 删除 `resolveDirectorEditStage`（`novelDirectorContinueRuntime.ts:496-515`），并入单一 stage 归一器。
  5. 消除 `seedPayload.resumeTarget` 镜像写入（`:228`/`:126`/`:263`/`:315` 等），编排层只写 `resumeTargetJson` 一列。
  6. director 链路 15 个调用点（doc14 簇 C）补 `lane:"auto_director"` 或直接改调 `composeResumeTarget`。
- **红线**：归一规则复用既有 `NovelWorkflowLaneDescriptor.taskQueryKey`（`novelWorkflow.ts:56`）与 `mapStageToTab`/`mapTabToStage`，**不引入任何新字符串分支表**（AI-First）。
- **风险**：中。跨 director + core + 客户端 7 处消费方（`directorTaskNotice.ts:76-108` 等）。
- **验收**：`resumeTargetToRoute` 在 `lane` 归一后行为不变（director 仍走 `directorTaskId`）；客户端 7 处回归通过。
- **测试影响**：`directorRecoverySampleAudit.test.js` 硬编码 `resumeTargetJson.stage` 值（"basic"/"chapter"/"structured"）需随契约改写（doc15 #6）。

### T3-3 · C21 展示枚举合并
- **范围**：收敛 `WORKFLOW_DISPLAY_STAGES` / `displayStage` / `DirectorDisplayStageKey`（`directorWorkflowStepCatalog.ts` 与 `DirectorDisplayStateBuilder.ts`），统一到单一展示词表；消除 `mapStageToTab`/`mapTabToStage`/`resolveDirectorEditStage` 三套转换器为一份（与 T3-2 共用）。
- **风险**：中高。触碰 R2/R3 进度展示主路径（计划 §4.3）。
- **验收**：展示映射有唯一权威源；`directorDisplayStateBuilder.test.js` 写死的 `"节奏 / 拆章"` label 随统一词表更新。
- **测试影响**：`directorWorkflowStepCatalog.test.js`（#2）、`directorDisplayStateBuilder.test.js`（#4）。

### T3-4 · C22 nodeKey 去重
- **范围**：`chapter.draft.repair` 与 `chapter.quality.repair` 当前 `nodeKey` 均为 `chapter_repair_node`（`directorWorkflowStepModules.ts:46-47, 876-897`），按 C22 去重为单一规范 `nodeKey`（重复声明 aliases 机制已存在，见 `directorWorkflowStepCatalog.test.js:64-67`）。
- **风险**：中。涉及编排步骤注册表。
- **验收**：注册表不再有重复 `nodeKey`；22 步 → 21 步 + 真正有序的 `orchestrationOrder`。
- **测试影响**：`directorWorkflowStepModules.test.js`（#3）。

### T3-5 · 真相表 20→≤6 / 翻译表 6→0~1 + shared/types 瘦身
- **范围**：收敛 9 套并行阶段枚举（E1–E11）+ 6 处翻译表（M1–M11 中的 M1/M2/M3/M6/M8/M9/M10 手抄）到「1 份正式枚举 + 1 份 label 表 + 1 份 step catalog + 必要 zod 校验 + 1 份 M1 翻译（由标准取代 JobTracker）」；`shared/types/directorRuntime.ts`、`novel.ts` 随枚举收敛自然瘦身后删除重复定义。
- **风险**：高（R-04 AI-First 红线：禁止换汤不换药的字符串分支表）。
- **红线**：新增 resolver 必须消费编排层/AI 已结构化产出的字段，**仅允许输入校验与安全守卫类固定判断**。
- **依赖**：T3-3、T3-4 先产出统一词表/归一器，本任务才动手。
- **验收**：全仓「翻译/手工转换表数量」由 6 → 0~1；`directorWorkflowStepCatalog.test.js` 的目录断言更新到新结构。

### T3-6 · C19 进度展示 R2/R3 归一
- **范围**：`directorDashboardViewBuilder` 的 `view.mode`/`progressPercent`/`stageKey` 映射统一到经 T3-3 收敛后的单一 stage 词表；确保不改 R5 质量债非阻断、R4 恢复行为。
- **风险**：中高。主路径。
- **验收**：进度展示来源唯一；`directorDashboardViewBuilder.test.js` 更新到新 stage 映射（#5）。
- **测试影响**：`directorDashboardViewBuilder.test.js`（#5）+ 3 个 progress 文件（`novelDirectorProgress`/`novelPipelineProgress`/`novelWorkflowStructuredOutlineProgress`）大概率需改。

### T3-7 · R5/R4 护栏固化（贯穿全程）
- **范围**：锁死「质量债非阻断（R5）」「恢复行为（R4）」语义不变；`directorQualityRepairRisk.test.js`（R5 断言）、`novelDirectorRecovery`/`novelWorkflowRecoveryNormalization`/`novelWorkflowCancellation`/`novelDirectorRetry`（R4 相关）作为回归护栏，**Phase 3 不得改动其语义**。
- **风险**：低（纯护栏，无代码行为变更）。
- **验收**：上述测试在 Phase 3 全过程中保持绿；任何 C 项若使其转红，视为该 C 项违规，先回退。

## 5. 跨任务护栏（不可突破）

1. **零数据动作**：Phase 3 全程不碰 Prisma schema / migration / 任何 `DROP`/`reset`/`truncate`。孤儿表留到 Phase 4。
2. **AI-First 红线**：禁止用新增字符串分支表替换旧分支表；新 resolver 消费已结构化产出（`resumeTarget` / 编排层输出），仅允许输入校验与安全守卫类固定判断。
3. **行为锁定**：R5 质量债非阻断、R4 恢复行为不变（AGENTS.md 硬性规则）。
4. **每 C 结束可构建**：每个任务完成时系统必须可构建、可启动、可走通「灵感 → 第一章产出 → 书架可读」。
5. **测试先基线后改码**：涉及测试失效的任务，先建新期望基线再改实现（doc15 §8）。

## 6. 回滚与验证口径

- **回滚**：`git revert` 单任务提交；旧展示/翻译表保留 1–2 个迭代做影子对照（仅日志比对，不做分支）。
- **验证**：① `pnpm typecheck` 全绿 ② `pnpm build` 全绿 ③ `pnpm test` 与基线对比——Phase 3 允许目录类/协调器类测试随结构更新而改写，但**不允许新增无关失败**；R5/R4 护栏测试必须保持绿 ④ 手工走通主链。
- **客户端影响**：`directorTaskNotice.ts` 等 7 处因依赖 director 的 `lane` 隐式为 `null` 的逻辑需逐文件回归（doc14 §5）。

## 7. 与后续阶段接驳

- **C20 lane 收敛 / C23 takeover 删除** → 下一阶段，依赖本表产出的统一 `resumeTarget` 契约（doc14 已给出设计草图）。
- **Phase 4 数据层** → 独立提案，含具体备份路径、恢复校验证据、逐表 COUNT、用户批准记录，四者缺一不可（计划 §8.2）。
