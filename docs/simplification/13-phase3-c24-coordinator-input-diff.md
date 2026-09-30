# Phase 3 · C24 三个 ChapterRuntimeCoordinator 实例入参差异说明

> 前置调研文档，为 C24（3 实例 → 1 实例）合并提供决策依据。本文为**只读调研**，未改动任何代码。
> 依据 `docs/simplification/02-architecture-simplification-plan.md` §4.3（P2）与 §8.3 Q4 的 C24 项。

## 1. 类定义

- 文件：`server/src/services/novel/runtime/ChapterRuntimeCoordinator.ts`
- 类声明：`:65` `export class ChapterRuntimeCoordinator {`
- 构造函数：`:72` `constructor(deps: ChapterRuntimeCoordinatorDeps = {}) {`
  - **只有一个对象参数** `deps`，默认 `{}`
- 依赖接口 `ChapterRuntimeCoordinatorDeps`：`:40-63`，**共 15 个可选字段**（全部 `?`），构造体内逐个填充默认实现

| 参数 | 类型位置 | 构造体内默认实现 | 控制能力 |
|---|---|---|---|
| lifecycleService | :59-62 | `chapterLifecycleService` (:73) | 章节生命周期：存草稿/改状态/改生成态 |
| artifactSyncService | :44 | `new ChapterArtifactSyncService(lifecycleService)` (:74) | 草稿与产物落库/同步 |
| agentRuntime | :49 | `defaultChapterRuntimeAgent` (:75, :157-159) | 调用的 LLM Agent 运行时 |
| assembler | :41 | `new GenerationContextAssembler()` (:76) | 生成上下文装配 |
| preparationService | :42 | `createChapterExecutionPreparationService({ ensureChapterExecutionContract })` (:77-79) | 执行前准备 |
| chapterWritingGraph | :43 | `createDefaultChapterWritingGraph(artifactSyncService)` (:80, :161-186) | 写作图 |
| plannerService | :46 | `plannerService`（模块单例）(:81) | 重规划建议/触发判断 |
| auditService | :45 | `auditService`（模块单例）(:82) | 章节审计 |
| acceptanceAssessmentService | :47 | `new ChapterAcceptanceAssessmentService()` (:83) | 验收评估 |
| readinessService | :48 | `new ChapterRuntimeReadinessService()` (:102) | 就绪断言 |
| ensureNovelCharacters | :50 | `this.ensureNovelCharacters.bind(this)` (:84, :188-193) | 角色数量前置校验 |
| ensureChapterExecutionContract | :51-55 | 透传给 preparationService（无则 undefined）(:78) | 执行契约校验 |
| validateRequest | :56 | `(input) => chapterRuntimeRequestSchema.parse(input)` (:85) | 请求校验 |
| timelineFinalizer | :58 | `chapterTimelineFinalizationService`（模块单例）(:95) | 时间线定稿 |
| resolveAuditIssues | :57 | **无内部默认值**，原样透传 repair 路径 (:121) | 仅 repair 路径使用 |

**关键**：`resolveAuditIssues` 是唯一不带内部默认值的依赖，且仅被 `ChapterRepairStreamRuntime` 使用（`ChapterRuntimeCoordinator.ts:115-122`，`:121` 透传）。

## 2. 计划指定的三个目标实例

| 实例 | 位置 | 实参 |
|---|---|---|
| **A** | `application/NovelApplicationServices.ts:59` | `new ChapterRuntimeCoordinator()` |
| **B** | `application/NovelApplicationServices.ts:60-62` | `new ChapterRuntimeCoordinator({ resolveAuditIssues: (novelId, issueIds) => this.core.resolveAuditIssues(novelId, issueIds) })` |
| **C** | `novelCorePipelineService.ts:33` | `new ChapterRuntimeCoordinator()` |

逐参数对照（✓=使用默认，◆=显式传入）：

| 参数 | A (:59) | B (:60) | C (pipeline:33) |
|---|---|---|---|
| lifecycleService / artifactSyncService / agentRuntime / assembler / preparationService / chapterWritingGraph / plannerService / auditService / acceptanceAssessmentService / readinessService / ensureNovelCharacters / ensureChapterExecutionContract / validateRequest / timelineFinalizer | ✓ | ✓ | ✓ |
| **resolveAuditIssues** | ✓未传(undefined) | ◆`this.core.resolveAuditIssues` | ✓未传(undefined) |

**结论：A 与 C 构造实参逐字节相同；B 相对 A/C 唯一差异是 `resolveAuditIssues`。**

## 3. 语义差异结论

1. **B 确实专用于 quality repair**：注册到 `registerQualityRepairStageRunner`（`NovelApplicationServices.ts:72-75`，`getCoordinator: () => this.qualityRepairCoordinator`）；A 注册到 `registerChapterExecutionStageRunner`（`:65-68`）；C 注入 `NovelPipelineExecutor`（`:34`，由 `runPipelineChapter` 驱动，调用点 `NovelPipelineExecutor.ts:497`）。
2. **B 唯一的入参差异 `resolveAuditIssues` 去向后**：仅进入 `ChapterRepairStreamRuntime`，在 repair 完成且 `input.options.auditIssueIds?.length` 为真、`pass` 为真时调用（`:239-243`），并带 `?? auditService.resolveIssues` 回退：
   ```ts
   const resolveAuditIssues = this.deps.resolveAuditIssues
     ?? ((novelId, issueIds) => auditService.resolveIssues(novelId, issueIds));
   await resolveAuditIssues(input.novelId, input.options.auditIssueIds).catch(() => null);
   ```
3. **B 注入实现与 A/C 默认回退最终等价**：`this.core.resolveAuditIssues` → `reviewService.resolveAuditIssues` → `auditService.resolveIssues`（`NovelCoreService.ts:261-263`、`novelCoreReviewService.ts:178-180`），与 A/C 默认回退**完全相同**。`NovelCoreReviewService` 自身也以同样方式注入一次（`:54-56`），进一步印证该链路只是把 `auditService.resolveIssues` 又包了一层。

**语义差异结论**：三个实例在 14 个依赖上完全一致；唯一差异点 `resolveAuditIssues` 在 `:60` 被显式注入，但注入实现与 `:59`/`:33` 的默认回退实现最终都落到同一个 `auditService.resolveIssues` 模块单例。因此 **A 与 B 之间的入参差异并非语义必要——是冗余的间接层（历史巧合/防御式写法），不改变运行时行为。**

## 4. 合并风险判读

- **真正语义必要、必须保留为配置项的差异：无。** 三个目标实例目前没有任何会改变运行时行为的入参差异。
- **可统一的部分**：`:60` 的 `resolveAuditIssues` 注入与默认回退等价，可安全删除该注入，让 B 退化为与 A/C 相同的默认构造。
- **最小安全形态**：使用 1 个 `new ChapterRuntimeCoordinator()`（默认 deps）即可同时服务 A/B/C 三个场景。由于 `resolveAuditIssues` 在 repair 路径自带 `?? auditService.resolveIssues` 回退，**即便 repair 场景也照样正确**。
- **唯一保留注意点**：合并时务必保证 `ChapterRepairStreamRuntime.ts:240-241` 的 `??` 回退逻辑不被移除；若未来有人删掉该回退，则 repair 场景必须有 `resolveAuditIssues` 注入，届时需要把该能力作为配置项显式保留。

## 5. 范围外提示（供合并决策参考）

全仓实际共 **7 处** `new ChapterRuntimeCoordinator`：

- 默认构造（5 处）：`NovelApplicationServices.ts:59`、`:60`（仅 resolveAuditIssues）、`novelCorePipelineService.ts:33`、`NovelGenerationService.ts:15`、`NovelPipelineService.ts:15`、`NovelPipelineExecutor.ts:86`
- 带 `resolveAuditIssues` 注入（2 处）：`NovelApplicationServices.ts:60`、`novelCoreReviewService.ts:54-56`（后者注入 `this.resolveAuditIssues`，同样最终落到 `auditService.resolveIssues`）

即全仓只有「纯默认」与「等同于默认的 resolveAuditIssues 注入」两种形态，**没有任何实例存在真正不同的行为配置**。因此把 7 处收敛为 1 个共享默认单例，在语义上是安全的。

## 6. 合并实施建议（待 Phase 3 任务表确认）

1. 删除 `NovelApplicationServices.ts:60` 的 `resolveAuditIssues` 注入，B 退化为 `new ChapterRuntimeCoordinator()`。
2. 将 `NovelApplicationServices.ts:59/60`、`novelCorePipelineService.ts:33` 及范围外 4 处统一改为引用同一模块级单例（如 `sharedChapterRuntimeCoordinator`）。
3. 保留 `ChapterRepairStreamRuntime.ts:240-241` 的 `??` 回退作为安全网。
4. 验收：现有 `chapterRuntimeCoordinator.test.js` 中 11+ 处 `new` 与依赖桩需随构造形态收敛而改写（见 `15-phase3-director-test-impact.md`）。
