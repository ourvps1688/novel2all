# Phase 3 · 统一 resumeTarget 契约

> 前置调研文档，为 Phase 3「状态真相收敛」产出统一的 `NovelWorkflowResumeTarget` 契约提供设计依据。
> 本文为**只读调研**，未改动任何代码。依据 `02-architecture-simplification-plan.md` §4.3（P2）与 §8.3 Q4。

## 1. 类型定义（`shared/types/novelWorkflow.ts:39-48`）

```ts
export interface NovelWorkflowResumeTarget {
  route: "/create" | "/novels/create" | "/novels/:id/edit" | "/novels/:id/simple" | "/novels/:id/story";
  novelId?: string | null;
  taskId?: string | null;
  lane?: NovelWorkflowLane | null;
  stage?: "basic" | "story_macro" | "world" | "character" | "outline" | "structured" | "chapter" | "pipeline";
  chapterId?: string | null;
  volumeId?: string | null;
  mode?: "director" | null;
}
```

关键观察：
- **`lane` 可空可选**（`NovelWorkflowLane | null`），这是后续「分裂」的根因——是否填 `lane` 完全取决于调用方。
- **`stage` 是 tab 词表（8 值）**，与内部 `NovelWorkflowStage`（13 值，`novelWorkflow.ts:3-16`）不是同一套，靠 `mapStageToTab`/`mapTabToStage` 桥接。
- `NovelWorkflowLane` 仅三值：`"manual_create" | "auto_director" | "creation_studio"`（`novelWorkflow.ts:1`）。

## 2. 字段 × 产出点矩阵（真实分裂是「两簇」而非「三 lane」）

所有产出最终汇聚到 `novelWorkflow.shared.ts` 的四个 builder，但**谁调用、传不传 `lane` 各不相同**。

### 簇 A：共享 builder（`novelWorkflow.shared.ts`）

| Builder | 行 | route | novelId | taskId | lane | stage | chapterId | volumeId | mode |
|---|---|---|---|---|---|---|---|---|---|
| buildNovelCreateResumeTarget | :59-65 | `/novels/create` | — | ✓ | 不填(→null) | — | — | — | ✓(=director?) |
| buildCreationStudioResumeTarget | :67-73 | `/create` | — | ✓ | ✓`creation_studio` | — | — | — | — |
| buildShortStoryResumeTarget | :75-82 | `/novels/:id/story` | ✓ | ✓ | ✓`creation_studio` | — | — | — | — |
| buildNovelEditResumeTarget(params) | :84-101 | `/novels/:id/edit` | ✓ | ✓ | `params.lane ?? null` | ✓必填 | `?? null` | `?? null` | — |

### 簇 B：核心生产链路（经 `NovelWorkflowStoreService.buildResumeTarget` 中转）

`NovelWorkflowStoreService.buildResumeTarget`（`:232-256`）是唯一会**显式写入 `lane`** 的编辑类产出点：
- `creation_studio` + novelId → `buildShortStoryResumeTarget`；无 novelId → `buildCreationStudioResumeTarget`
- 无 novelId → `buildNovelCreateResumeTarget`（lane 自动 null）
- 其余 → `buildNovelEditResumeTarget({ lane: input.lane, stage: mapStageToTab(stage), chapterId, volumeId })`（**:251 写入 lane**）

调用方 `NovelWorkflowApplicationService.ts`：`:111`/`:206`/`:257`/`:300`/`:525`/`:560` 都传 `lane: existing.lane`。
检查点恢复：`novelWorkflowCheckpoint.ts:41-94` 的 `buildRestoreTaskToCheckpointResult`，候选选择走 `buildNovelCreateResumeTarget(_,"director")`，否则 `parseResumeTarget ?? buildResumeTarget({ lane: existing.lane ?? "auto_director" })`（**:67**）。

→ **核心链路产出的 `lane` 是真实值**（manual_create / auto_director / creation_studio）。

### 簇 C：director 链路（`server/src/services/novel/director/**`）

这些点**全部直接调 `buildNovelEditResumeTarget` 且不传 `lane`** → 存库后 `lane === null`（15 个调用点，含 `automation/novelDirectorAutoExecutionCheckpointRuntime.ts:85/131/160/208`、`phases/novelDirectorChapterTitleRepair.ts:81/113`、`phases/novelDirectorPipelinePhases.ts:93/263`、`phases/novelDirectorStructuredOutlinePhase.ts:216/596`、`runtime/novelDirectorConfirmRuntime.ts:304/404`、`runtime/novelDirectorContinueRuntime.ts:363/444`、`runtime/novelDirectorTakeoverExecution.ts:223` 等）。

→ **同一 `auto_director` 任务，director 链路写入时 `lane=null`，核心链路写入时 `lane="auto_director"`——同一字段两种取值。**

## 3. 现状问题盘点

1. **`lane` 两簇赋值不一致**：核心链路强制写 `lane`（`NovelWorkflowStoreService.ts:251`），director 链路从不写（默认 null，`novelWorkflow.shared.ts:96` + 簇 C 全部调用点）。消费侧 `resumeTargetToRoute` 用 `lane === "manual_create"` 决定 query 参数名（`:143-147`）；director 产出 `lane=null` 走 `else`→`directorTaskId`，结果「碰巧」正确，但存储值自相矛盾。
2. **同一合并函数复制 4 份**：`mergeResumeTargets` 出现于 `novelWorkflow.helpers.ts:105`（规范版）、`novelDirectorChapterTitleRepairRuntime.ts:25`、`:53`、`NovelWorkflowTaskAdapter.ts:110`；`parseResumeTargetLike` 复制 2 份（`:15`/`:74`）。
3. **seedPayload 镜像**：director 运行时把 resumeTarget 同时写进 `resumeTargetJson` 列与 `seedPayloadJson.resumeTarget`（如 `novelDirectorStructuredOutlinePhase.ts:228`、`novelDirectorChapterTitleRepairRuntime.ts:126`、`novelDirectorTakeoverExecution.ts:263`、`novelDirectorConfirmRuntime.ts:315`），读取时靠「读时 merge」补救（`:77-80`/`:440-442`/`:229-235`）。
4. **同义不同名 / 多套词汇表**：`stage` 转换器有 3 个（`mapStageToTab` `novelWorkflow.helpers.ts:193-202`、`mapTabToStage` `novelDirectorAutoDirectorInitialState.ts:18`、`resolveDirectorEditStage` `novelDirectorContinueRuntime.ts:496-515`）；`taskId` 别名有 `workspaceTaskId`/`directorTaskId`/`taskId`（`novelWorkflow.ts:56` 的 `taskQueryKey`）；「当前位置」有三套表示：`resumeTarget.stage` / `task.currentItemKey` / `NovelWorkflowStage`。
5. **`mode` 仅 pre-novel 使用**：只有 `buildNovelCreateResumeTarget(_, "director")`（`:59-64`）设 `mode:"director"`，其余永远 null。

## 4. 统一契约设计草图（单一「下一步 + 去哪里」，不引入新字符串分支表）

### 4.1 目标类型形状
```ts
export type ResumeRoute =
  | "/create" | "/novels/create" | "/novels/:id/edit"
  | "/novels/:id/simple" | "/novels/:id/story";
export type ResumeStage =
  | "basic" | "story_macro" | "world" | "character"
  | "outline" | "structured" | "chapter" | "pipeline";

export interface NovelWorkflowResumeTarget {
  route: ResumeRoute;        // 「去哪里」——前端路由（唯一权威）
  lane: NovelWorkflowLane;   // 「谁产出」——【改为必填】，产出时归一，消除 null/auto_director 双值
  novelId: string | null;
  taskId: string | null;     // 「下一步任务」——唯一规范键；别名统一收敛到此
  stage: ResumeStage;        // 「停在哪一步」——唯一规范 tab 词表
  chapterId: string | null;
  volumeId: string | null;
  mode: "director" | null;   // 仅候选选择(pre-novel)使用，其余一律 null
}
```
变更要点：**`lane` 由可选改为必填**；其余字段名不动（保护所有现消费方）。

### 4.2 单一 composer（替代散落调用）
新增 `composeResumeTarget(input)`（放 `novelWorkflow.shared.ts`），**接受别名、内部归一为规范形状**，所有产出点只调它：
```ts
composeResumeTarget({
  lane,                                  // 必填：调用方显式给出（director 传 "auto_director"）
  route?, novelId?, taskId?,
  workspaceTaskId?, directorTaskId?,     // 别名 → 归一为 taskId（按 getNovelWorkflowLaneDescriptor(lane).taskQueryKey）
  stage?, currentStage?, phase?,        // 别名 → 归一为 ResumeStage（复用 mapStageToTab / resolveDirectorEditStage 合并后的单一函数）
  currentItemKey?,
  chapterId?, volumeId?, mode?,
})
```
归一规则**复用既有结构化描述符**，不新增字符串分支表（符合 AI-First 红线）：`taskId` 别名用 `NovelWorkflowLaneDescriptor.taskQueryKey`（`novelWorkflow.ts:56`）；`stage` 归一用既有 `mapStageToTab`/`mapTabToStage`，**删除** `resolveDirectorEditStage`（`novelDirectorContinueRuntime.ts:496`）。

### 4.3 单一 merge
保留 `novelWorkflow.helpers.ts:105` 的 `mergeResumeTargets` 为唯一实现；删除另外 3 份（`:25`/`:53`/`:110`）；`parseResumeTargetLike` 合并为 `novelWorkflow.shared.ts` 单一导出。

### 4.4 收敛 seedPayload 镜像
统一契约下 `seedPayload.resumeTarget` 不再是独立产出物：编排层**只写 `resumeTargetJson`** 一列；需要恢复上下文时统一走 `composeResumeTarget(parseResumeTarget(resumeTargetJson), fallbackSeed)`。这是消除「各填一部分」的关键一步。

## 5. 受影响消费方清单（统一后需跟着改）

**产出侧（必须改）**
- director 链路 15 个调用点（簇 C）——补 `lane:"auto_director"`，或直接改调 `composeResumeTarget`。
- 3 份重复 `mergeResumeTargets`（`novelDirectorChapterTitleRepairRuntime.ts:25`、`:53`、`NovelWorkflowTaskAdapter.ts:110`）——删除，改 import 规范版。
- 2 份 `parseResumeTargetLike`（`:15`/`:74`）——删除，改 import。
- `resolveDirectorEditStage`（`novelDirectorContinueRuntime.ts:496-515`）——并入单一 stage 归一器。
- seedPayload.resumeTarget 镜像写入（`:228`/`:126`/`:263`/`:315` 等）——改为只写 `resumeTargetJson`。

**消费侧（需回归验证）**
- `resumeTargetToRoute`（`novelWorkflow.shared.ts:103`）——`lane==="manual_create"` 分支在 lane 归一后行为不变；director(`auto_director`) 仍走 `directorTaskId`，确认无误。
- `NovelWorkflowTaskAdapter.normalizeWorkflowResumeTargetForCandidateSelection`（`:221-245`）——不再 merge 两份，改调统一 composer。
- `autoDirectorMemorySafety.ts:79`、`:152-165`；`NovelWorkflowHealingService.ts:390`、`:581`；`directorRecoverySampleAudit.ts:246`、`:250`——读取 stage/volumeId/chapterId，字段名不变，仅需回归。
- **客户端消费方**（字段值语义不变，主要风险是「依赖 director 的 lane 为 null/未定义」的隐式逻辑）：`client/src/lib/directorTaskNotice.ts:76-108`、`client/src/pages/novels/autoDirector/AutoDirectorCreatePage.tsx`、`StageCandidates.tsx`、`components/NovelAutoDirectorProgressPanel.tsx`、`NovelEdit.tsx`、`pages/tasks/components/TaskCenterDetailSummary.tsx`、`tasks/taskCenterUtils.ts`。

## 6. 修正（对任务描述的澄清）

`server/src/services/novel/NovelPipelineExecutor.ts` **不直接产出 resumeTarget**（grep 无 `resumeTarget/buildNovelEdit/buildResumeTarget` 命中）。所谓 pipeline 产出实际落在 `director/phases/novelDirectorPipelinePhases.ts` 与 `novelDirectorStructuredOutlinePhase.ts`（已计入簇 C）。因此真实分裂是 **「director 运行时簇（不填 lane）」 vs 「workflow 核心簇（填 lane）」两方**，而非三条独立 lane。统一契约只需对齐这两方。

## 7. 实施建议（待 Phase 3 任务表确认）

1. 将 `lane` 改为必填，所有产出点显式传值（director 传 `"auto_director"`）。
2. 引入 `composeResumeTarget`，替换 4 个 builder 的散落调用与 4 份 merge 复制。
3. 删除 `resolveDirectorEditStage` 与 seedPayload 镜像写入。
4. 客户端消费方逐文件回归（重点：`directorTaskNotice.ts` 等依赖 lane 隐式为 null 的逻辑）。
