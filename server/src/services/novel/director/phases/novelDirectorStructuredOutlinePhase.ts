import type { VolumePlanDocument } from "@ai-novel/shared/types/novel";
import type {
  DirectorConfirmRequest,
} from "@ai-novel/shared/types/novelDirector";
import {
  isDirectorAutoExecutionRunMode,
  isFullBookAutopilotRunMode,
} from "@ai-novel/shared/types/novelDirector";
import type { VolumeGenerationPhaseEvent } from "../../volume/volumeModels";
import { getChapterTitleDiversityIssue } from "../../volume/chapterTitleDiversity";
import { logMemoryUsage } from "../../../../runtime/memoryTelemetry";
import {
  buildDirectorSessionState,
  normalizeDirectorRunMode,
} from "../runtime/novelDirectorHelpers";
import {
  buildChapterDetailBundleLabel,
  buildChapterDetailBundleProgress,
  DIRECTOR_PROGRESS,
  type DirectorProgressItemKey,
} from "../projections/novelDirectorProgress";
import {
  buildDirectorAutoExecutionState,
  countDirectorAutoExecutionChapterRange,
  hasDirectorSyncedChapterExecutionContext,
  normalizeDirectorAutoExecutionPlan,
  resolveDirectorAutoExecutionPlanChapterRange,
} from "../automation/novelDirectorAutoExecution";
import {
  flattenPreparedOutlineChapters,
  resolveStructuredOutlineRecoveryCursor,
  type StructuredOutlineDetailMode,
  type StructuredOutlineRecoveryCursor,
} from "../recovery/novelDirectorStructuredOutlineRecovery";
import { runDirectorTrackedStep } from "../projections/directorProgressTracker";
import type { DirectorPhaseCallbacks, DirectorPhaseDependencies } from "./novelDirectorPhaseTypes";
import { resetDirectorDownstreamChapterState } from "../recovery/novelDirectorDownstreamReset";
import { DirectorProductionExperienceService } from "../commands/DirectorProductionExperienceService";

function buildChapterOrderRangeLabel(startOrder: number, endOrder: number): string {
  return startOrder === endOrder ? `第 ${startOrder} 章` : `第 ${startOrder}-${endOrder} 章`;
}

function buildFastStartPlanningGuidance(request: DirectorConfirmRequest): string | undefined {
  const preparation = request.startupPreparation;
  if (!preparation || preparation.strategy !== "fast_start") {
    return undefined;
  }
  return [
    "本次采用快速开篇：首个可执行节奏段只规划开篇路线，不提前锁死远期章节。",
    `首批路线必须覆盖 ${preparation.routeWindow.min}-${preparation.routeWindow.target} 章，优先形成可立即进入正文的因果链。`,
    `正文前只需要完整细化未来 ${preparation.routeWindow.detailAhead} 章，其余章节保留为简略路线。`,
  ].join("\n");
}

function findMissingSelectedChapterOrders(
  selectedOrders: number[],
  range: { startOrder: number; endOrder: number },
): number[] {
  const selected = new Set(selectedOrders);
  const missing: number[] = [];
  for (let order = range.startOrder; order <= range.endOrder; order += 1) {
    if (!selected.has(order)) {
      missing.push(order);
    }
  }
  return missing;
}

async function syncPreparedChapterExecutionContext(input: {
  novelId: string;
  workspace: VolumePlanDocument;
  targetVolumeId: string;
  targetChapterId: string;
  dependencies: DirectorPhaseDependencies;
}): Promise<void> {
  const targetVolume = input.workspace.volumes.find((volume) => volume.id === input.targetVolumeId);
  const targetChapter = targetVolume?.chapters.find((chapter) => chapter.id === input.targetChapterId);
  if (!targetChapter) {
    return;
  }
  if (!targetChapter.taskSheet?.trim() && !targetChapter.sceneCards?.trim()) {
    return;
  }

  await input.dependencies.volumeService.syncVolumeChaptersWithOptions(input.novelId, {
    volumes: input.workspace.volumes,
    preserveContent: true,
    applyDeletes: false,
    executionContractChapterRange: {
      startOrder: targetChapter.chapterOrder,
      endOrder: targetChapter.chapterOrder,
    },
  }, {
    emitEvent: false,
    syncPayoffLedger: false,
  });
}

function buildStructuredOutlinePhaseUpdate(event: VolumeGenerationPhaseEvent): {
  itemKey: DirectorProgressItemKey;
  itemLabel: string;
  progress: number;
} | null {
  if (event.scope === "beat_sheet") {
    return {
      itemKey: "beat_sheet",
      itemLabel: event.label.trim() || (event.phase === "load_context" ? "正在整理节奏板上下文" : "正在生成节奏板"),
      progress: DIRECTOR_PROGRESS.beatSheet,
    };
  }
  if (event.scope === "chapter_list") {
    return {
      itemKey: "chapter_list",
      itemLabel: event.label.trim() || (event.phase === "load_context" ? "正在整理拆章上下文" : "正在生成章节列表"),
      progress: DIRECTOR_PROGRESS.chapterList,
    };
  }
  if (event.scope === "rebalance") {
    return {
      itemKey: "chapter_list",
      itemLabel: event.label.trim() || "正在校准相邻卷衔接",
      progress: 0.8,
    };
  }
  return null;
}

function buildStructuredOutlineCursorKey(cursor: StructuredOutlineRecoveryCursor): string {
  return [
    cursor.step,
    cursor.volumeId ?? "",
    cursor.chapterId ?? "",
    cursor.detailMode ?? "",
    cursor.beatKey ?? "",
    cursor.preparedVolumeIds.length,
    cursor.selectedChapters.length,
    cursor.completedChapterCount,
    cursor.totalChapterCount,
    cursor.completedDetailSteps,
    cursor.totalDetailSteps,
  ].join("|");
}

async function persistStructuredOutlineVolumeSnapshot(input: {
  taskId: string;
  novelId: string;
  workspace: VolumePlanDocument;
  itemKey: "beat_sheet" | "chapter_list";
  scope: "beat_sheet" | "chapter_list";
  volumeId?: string | null;
  dependencies: Pick<DirectorPhaseDependencies, "volumeService">;
}): Promise<VolumePlanDocument> {
  return input.dependencies.volumeService.updateVolumesWithOptions(input.novelId, input.workspace, {
    emitEvent: false,
    syncPayoffLedger: false,
    memoryTelemetry: {
      taskId: input.taskId,
      stage: "structured_outline",
      itemKey: input.itemKey,
      scope: input.scope,
      entrypoint: "auto_director",
      volumeId: input.volumeId,
    },
  });
}

/**
 * 续写（extend_outline）场景下，计算「仅覆盖新增章节」的区间。
 * startOrder 来自续写前的最后一章序号 +1；endOrder 取续写后全书最大章序。
 * 历史章节（order <= 续写前最大序）一律排除，使质量门禁与同步只校验新增章节，
 * 不被历史章节的执行合同不完整（如早期数据缺字段）阻塞整次续写。
 */
export function resolveExtendOutlineChapterRange(
  preExtendWorkspace: VolumePlanDocument,
  postExtendWorkspace: VolumePlanDocument,
): { startOrder: number; endOrder: number } {
  const preExtendMaxChapterOrder = Math.max(
    0,
    ...preExtendWorkspace.volumes.flatMap((volume) => volume.chapters.map((chapter) => chapter.chapterOrder)),
  );
  const postExtendMaxChapterOrder = Math.max(
    preExtendMaxChapterOrder,
    ...postExtendWorkspace.volumes.flatMap((volume) => volume.chapters.map((chapter) => chapter.chapterOrder)),
  );
  return { startOrder: preExtendMaxChapterOrder + 1, endOrder: postExtendMaxChapterOrder };
}

export async function runDirectorStructuredOutlinePhase(input: {
  taskId: string;
  novelId: string;
  request: DirectorConfirmRequest;
  baseWorkspace: VolumePlanDocument;
  dependencies: DirectorPhaseDependencies;
  callbacks: DirectorPhaseCallbacks;
  /** 续写意图：在最后卷内追加新章节规划，而不是原地打转。 */
  intent?: "extend_outline";
}): Promise<void> {
  const { taskId, novelId, request, dependencies, callbacks } = input;
  let baseWorkspace = input.baseWorkspace;
  if (input.intent === "extend_outline") {
    // 卷规划已耗尽且卡在确认循环：直接在最后卷内续写主线，追加新节奏段与章节规划。
    // generateVolumes(scope: "extend") 会复用既有 beat sheet / chapter list prompt，
    // 从 max(chapterOrder)+1 继续编号，绝不改动已有卷与章节。
    baseWorkspace = await dependencies.volumeService.generateVolumes(novelId, {
      scope: "extend",
      taskId,
      provider: request.provider,
      model: request.model,
      temperature: request.temperature,
      entrypoint: "auto_director",
    });
  }

  // 续写场景：仅针对「续写新增的章节区间」做质量门禁与同步，不重新校验既有全书章节，
  // 避免历史章节的执行合同不完整（如早期生成数据缺字段）阻塞整次续写。
  const extendChapterRange = input.intent === "extend_outline"
    ? resolveExtendOutlineChapterRange(input.baseWorkspace, baseWorkspace)
    : null;

  logMemoryUsage({
    event: "start",
    component: "runDirectorStructuredOutlinePhase",
    taskId,
    novelId,
    stage: "structured_outline",
    scope: "structured_outline",
    entrypoint: "auto_director",
    volumeCount: baseWorkspace.volumes.length,
    chapterCount: baseWorkspace.volumes.reduce((sum, volume) => sum + volume.chapters.length, 0),
    beatSheetCount: baseWorkspace.beatSheets.length,
  });
  const firstVolume = baseWorkspace.volumes[0];
  if (!firstVolume) {
    throw new Error("自动导演未能生成可用卷骨架。");
  }
  const detailPlan = normalizeDirectorAutoExecutionPlan(
    isDirectorAutoExecutionRunMode(normalizeDirectorRunMode(request.runMode))
      ? request.autoExecutionPlan
      : undefined,
  );
  const fastStartGuidance = buildFastStartPlanningGuidance(request);
  const sortedVolumes = baseWorkspace.volumes
    .slice()
    .sort((left, right) => left.sortOrder - right.sortOrder);
  if (detailPlan.mode === "volume" && (detailPlan.volumeOrder ?? 1) > sortedVolumes.length) {
    throw new Error(`当前卷规划只有 ${sortedVolumes.length} 卷，不能直接自动执行第 ${detailPlan.volumeOrder} 卷。`);
  }

  const directorSession = buildDirectorSessionState({
    runMode: request.runMode,
    phase: "structured_outline",
    isBackgroundRunning: true,
  });
  const initialRecoveryCursor = resolveStructuredOutlineRecoveryCursor({
    workspace: baseWorkspace,
    plan: detailPlan,
    allowPartialChapterListReady: isDirectorAutoExecutionRunMode(normalizeDirectorRunMode(request.runMode)),
  });
  await dependencies.workflowService.bootstrapTask({
    workflowTaskId: taskId,
    novelId,
    lane: "auto_director",
    title: request.candidate.workingTitle,
    seedPayload: callbacks.buildDirectorSeedPayload(request, novelId, {
      directorSession,
    }),
  });

  let workspace = baseWorkspace;
  let previousCursorKey: string | null = null;
  // 节奏板覆盖不足时，自动/自动驾驶模式下自动补齐（重生成该卷节奏板后重试拆章），
  // 避免每次都挂起等人工。超过上限则放弃自动补，走原 gate 挂起交人工。
  const BEAT_SHEET_BACKFILL_CAP = 2;
  let beatSheetBackfillAttempts = 0;
  while (true) {
    const recoveryCursor = resolveStructuredOutlineRecoveryCursor({
      workspace,
      plan: detailPlan,
      allowPartialChapterListReady: isDirectorAutoExecutionRunMode(normalizeDirectorRunMode(request.runMode)),
    });
    const cursorKey = buildStructuredOutlineCursorKey(recoveryCursor);
    if (cursorKey === previousCursorKey) {
      throw new Error("自动导演结构化大纲恢复没有推进，请检查章节规划生成结果后重试。");
    }
    previousCursorKey = cursorKey;

    if (recoveryCursor.step === "beat_sheet") {
      const targetVolume = workspace.volumes.find((volume) => volume.id === recoveryCursor.volumeId);
      if (!targetVolume) {
        throw new Error("自动导演恢复时缺少待生成节奏板的目标卷。");
      }
      workspace = await runDirectorTrackedStep({
        taskId,
        stage: "structured_outline",
        itemKey: "beat_sheet",
        itemLabel: `正在生成第 ${targetVolume.sortOrder} 卷节奏板`,
        progress: DIRECTOR_PROGRESS.beatSheet,
        volumeId: targetVolume.id,
        callbacks,
        run: async ({ updateStatus, signal }) => dependencies.volumeService.generateVolumes(novelId, {
          provider: request.provider,
          model: request.model,
          temperature: request.temperature,
          scope: "beat_sheet",
          guidance: fastStartGuidance,
          targetVolumeId: targetVolume.id,
          draftWorkspace: workspace,
          taskId,
          entrypoint: "auto_director",
          signal,
          onPhaseStart: async (event) => {
            const update = buildStructuredOutlinePhaseUpdate(event);
            if (!update) {
              return;
            }
            await updateStatus(update);
          },
        }),
      });
      workspace = await persistStructuredOutlineVolumeSnapshot({
        taskId,
        novelId,
        workspace,
        itemKey: "beat_sheet",
        scope: "beat_sheet",
        volumeId: targetVolume.id,
        dependencies,
      });
      continue;
    }

    if (recoveryCursor.step === "chapter_list") {
      const targetVolume = workspace.volumes.find((volume) => volume.id === recoveryCursor.volumeId);
      if (!targetVolume) {
        throw new Error("自动导演恢复时缺少待拆章的目标卷。");
      }
      if (!recoveryCursor.beatKey) {
        throw new Error("自动导演恢复时缺少待生成章节的目标节奏段。");
      }
      const targetBeatKey = recoveryCursor.beatKey;
      const autoBackfillAllowed = isDirectorAutoExecutionRunMode(normalizeDirectorRunMode(request.runMode))
        || isFullBookAutopilotRunMode(request.runMode);
      try {
        workspace = await runDirectorTrackedStep({
          taskId,
          stage: "structured_outline",
          itemKey: "chapter_list",
          itemLabel: `正在生成第 ${targetVolume.sortOrder} 卷章节列表`,
          progress: DIRECTOR_PROGRESS.chapterList,
          volumeId: targetVolume.id,
          callbacks,
          run: async ({ updateStatus, signal }) => dependencies.volumeService.generateVolumes(novelId, {
            provider: request.provider,
            model: request.model,
            temperature: request.temperature,
            scope: "chapter_list",
            guidance: fastStartGuidance,
            targetVolumeId: targetVolume.id,
            generationMode: "single_beat",
            targetBeatKey,
            draftWorkspace: workspace,
            taskId,
            entrypoint: "auto_director",
            signal,
            persistIntermediateDocuments: true,
            onPhaseStart: async (event) => {
              const update = buildStructuredOutlinePhaseUpdate(event);
              if (!update) {
                return;
              }
              await updateStatus(update);
            },
            onIntermediateDocument: async (event) => {
              workspace = event.document;
            },
          }),
        });
      } catch (chapterListError) {
        const gateMessage = chapterListError instanceof Error ? chapterListError.message : String(chapterListError);
        // 节奏板覆盖不足触发的 gate：自动/自动驾驶模式下自动重生成该卷节奏板后重试拆章，
        // 避免每次都挂起等人工。超过 BEAT_SHEET_BACKFILL_CAP 仍不足则放弃自动补，按原 gate 挂起交人工。
        if (
          autoBackfillAllowed
          && /重生成节奏板/.test(gateMessage)
          && beatSheetBackfillAttempts < BEAT_SHEET_BACKFILL_CAP
        ) {
          beatSheetBackfillAttempts += 1;
          workspace = await runDirectorTrackedStep({
            taskId,
            stage: "structured_outline",
            itemKey: "beat_sheet",
            itemLabel: `自动补齐第 ${targetVolume.sortOrder} 卷节奏板（覆盖不足，第 ${beatSheetBackfillAttempts} 次）`,
            progress: DIRECTOR_PROGRESS.beatSheet,
            volumeId: targetVolume.id,
            callbacks,
            run: async ({ updateStatus, signal }) => dependencies.volumeService.generateVolumes(novelId, {
              provider: request.provider,
              model: request.model,
              temperature: request.temperature,
              scope: "beat_sheet",
              guidance: fastStartGuidance,
              targetVolumeId: targetVolume.id,
              draftWorkspace: workspace,
              taskId,
              entrypoint: "auto_director",
              signal,
              onPhaseStart: async (event) => {
                const update = buildStructuredOutlinePhaseUpdate(event);
                if (!update) {
                  return;
                }
                await updateStatus(update);
              },
            }),
          });
          workspace = await persistStructuredOutlineVolumeSnapshot({
            taskId,
            novelId,
            workspace,
            itemKey: "beat_sheet",
            scope: "beat_sheet",
            volumeId: targetVolume.id,
            dependencies,
          });
          // 重生成节奏板改变了工作区状态（覆盖不足已被补齐），重置进度游标避免被
          // “恢复没有推进”判定拦截；下一步会重试该卷的章节列表拆章。
          previousCursorKey = null;
          continue;
        }
        throw chapterListError;
      }
      const preparedVolume = workspace.volumes.find((item) => item.id === targetVolume.id);
      const titleDiversityIssue = preparedVolume
        ? getChapterTitleDiversityIssue(preparedVolume.chapters.map((chapter) => chapter.title))
        : null;
      if (titleDiversityIssue) {
        throw new Error(titleDiversityIssue);
      }
      workspace = await persistStructuredOutlineVolumeSnapshot({
        taskId,
        novelId,
        workspace,
        itemKey: "chapter_list",
        scope: "chapter_list",
        volumeId: targetVolume.id,
        dependencies,
      });
      await dependencies.workflowService.markTaskRunning(taskId, {
        stage: "structured_outline",
        itemKey: "chapter_list",
        itemLabel: `第 ${targetVolume.sortOrder} 卷章节列表已生成`,
        progress: DIRECTOR_PROGRESS.chapterList,
        volumeId: targetVolume.id,
        chapterId: initialRecoveryCursor.chapterId,
      });
      continue;
    }

    if (recoveryCursor.step === "chapter_detail_bundle") {
      // 懒规划模式（JIT）：全书自动执行时跳过预生成 task sheet，
      // 改为执行前即时生成（见 ChapterPlanJITService）。
      if (isFullBookAutopilotRunMode(request.runMode)) {
        break;
      }

      const targetDetailMode = recoveryCursor.detailMode as StructuredOutlineDetailMode | null;
      if (
        !recoveryCursor.chapterId
        || !recoveryCursor.volumeId
        || !targetDetailMode
        || recoveryCursor.nextChapterIndex == null
      ) {
        throw new Error("自动导演恢复时缺少章节细化所需游标。");
      }
      const targetVolumeId = recoveryCursor.volumeId;
      const targetChapterId = recoveryCursor.chapterId;
      const targetChapterIndex = recoveryCursor.nextChapterIndex;
      workspace = await runDirectorTrackedStep({
        taskId,
        stage: "structured_outline",
        itemKey: "chapter_detail_bundle",
        itemLabel: buildChapterDetailBundleLabel(
          targetChapterIndex + 1,
          recoveryCursor.totalChapterCount,
          targetDetailMode,
        ),
        progress: buildChapterDetailBundleProgress(
          recoveryCursor.completedDetailSteps,
          recoveryCursor.totalDetailSteps,
        ),
        chapterId: targetChapterId,
        volumeId: targetVolumeId,
        callbacks,
        run: async ({ signal }) => dependencies.volumeService.generateVolumes(novelId, {
          provider: request.provider,
          model: request.model,
          temperature: request.temperature,
          scope: "chapter_detail",
          targetVolumeId,
          targetChapterId,
          detailMode: targetDetailMode,
          chapterTaskSheetQualityMode: isFullBookAutopilotRunMode(request.runMode)
            ? "full_book_autopilot"
            : "ai_copilot",
          draftWorkspace: workspace,
          taskId,
          entrypoint: "auto_director",
          signal,
        }),
      });
      workspace = await dependencies.volumeService.updateVolumesWithOptions(novelId, workspace, {
        volumeUpdateReason: "chapter_execution_contract_refined",
        syncPayoffLedger: false,
        memoryTelemetry: {
          taskId,
          stage: "structured_outline",
          itemKey: "chapter_detail_bundle",
          scope: "chapter_detail",
          entrypoint: "auto_director",
          volumeId: recoveryCursor.volumeId,
          chapterId: recoveryCursor.chapterId,
        },
      });
      await syncPreparedChapterExecutionContext({
        novelId,
        workspace,
        targetVolumeId,
        targetChapterId,
        dependencies,
      });
      continue;
    }

    if (recoveryCursor.step === "chapter_sync" || recoveryCursor.step === "completed") {
      break;
    }
  }

  const preparedVolumeIds = resolveStructuredOutlineRecoveryCursor({
    workspace,
    plan: detailPlan,
    allowPartialChapterListReady: isDirectorAutoExecutionRunMode(normalizeDirectorRunMode(request.runMode)),
  }).preparedVolumeIds;
  const maxPreparedChapterOrder = Math.max(
    0,
    ...flattenPreparedOutlineChapters(workspace).map((chapter) => chapter.chapterOrder),
  );
  let targetChapterRange = resolveDirectorAutoExecutionPlanChapterRange(detailPlan);
  if (input.intent === "extend_outline" && extendChapterRange) {
    targetChapterRange = extendChapterRange;
  }
  const allowIncrementalExecutionWindow = isDirectorAutoExecutionRunMode(normalizeDirectorRunMode(request.runMode));
  if (targetChapterRange && maxPreparedChapterOrder < targetChapterRange.endOrder && !allowIncrementalExecutionWindow) {
    throw new Error(
      `当前已生成的章节规划最多只覆盖到第 ${maxPreparedChapterOrder} 章，不能直接自动执行${buildChapterOrderRangeLabel(targetChapterRange.startOrder, targetChapterRange.endOrder)}。`,
    );
  }

  await callbacks.markDirectorTaskRunning(
    taskId,
    "structured_outline",
    "chapter_sync",
    "正在同步已准备章节到执行区",
    DIRECTOR_PROGRESS.chapterSync,
  );
  logMemoryUsage({
    event: "before_sync_write",
    component: "runDirectorStructuredOutlinePhase",
    taskId,
    novelId,
    stage: "structured_outline",
    itemKey: "chapter_sync",
    scope: "structured_outline",
    entrypoint: "auto_director",
    volumeCount: workspace.volumes.length,
    chapterCount: workspace.volumes.reduce((sum, volume) => sum + volume.chapters.length, 0),
    beatSheetCount: workspace.beatSheets.length,
  });
  const persistedOutlineWorkspace = await dependencies.volumeService.updateVolumesWithOptions(novelId, workspace, {
    volumeUpdateReason: "chapter_execution_contract_refined",
    syncPayoffLedger: false,
    memoryTelemetry: {
      taskId,
      stage: "structured_outline",
      itemKey: "chapter_sync",
      scope: "structured_outline",
      entrypoint: "auto_director",
    },
  });
  await dependencies.volumeService.syncVolumeChaptersWithOptions(novelId, {
    volumes: persistedOutlineWorkspace.volumes,
    // Structured outline sync refreshes execution contracts; generated prose stays protected.
    preserveContent: true,
    applyDeletes: false,
    executionContractChapterRange: targetChapterRange ?? undefined,
  }, {
    emitEvent: false,
    syncPayoffLedger: false,
  });
  const syncCursor = resolveStructuredOutlineRecoveryCursor({
    workspace: persistedOutlineWorkspace,
    plan: detailPlan,
    allowPartialChapterListReady: allowIncrementalExecutionWindow,
  });
  let selectedChapters = syncCursor.selectedChapters;
  if (input.intent === "extend_outline" && extendChapterRange) {
    selectedChapters = selectedChapters.filter((chapter) => (
      chapter.chapterOrder >= extendChapterRange.startOrder
      && chapter.chapterOrder <= extendChapterRange.endOrder
    ));
  }
  if (selectedChapters.length === 0) {
    throw new Error("自动导演未能准备出可执行的章节范围。");
  }
  const selectedChapterOrders = selectedChapters.map((chapter) => chapter.chapterOrder).sort((left, right) => left - right);
  if (targetChapterRange && !allowIncrementalExecutionWindow) {
    const missingOrders = findMissingSelectedChapterOrders(selectedChapterOrders, targetChapterRange);
    if (missingOrders.length > 0) {
      throw new Error(
        `自动导演已准备的章节规划缺少第 ${missingOrders.slice(0, 5).join("、")} 章，不能直接自动执行${buildChapterOrderRangeLabel(targetChapterRange.startOrder, targetChapterRange.endOrder)}。`,
      );
    }
  }
  const autoExecutionScopeLabel = syncCursor.scopeLabel;
  const downstreamResetRange = {
    startOrder: selectedChapterOrders[0] ?? 1,
    endOrder: selectedChapterOrders[selectedChapterOrders.length - 1] ?? selectedChapterOrders[0] ?? 1,
  };
  await resetDirectorDownstreamChapterState(novelId, downstreamResetRange);

  await callbacks.markDirectorTaskRunning(
    taskId,
    "structured_outline",
    "chapter_detail_bundle",
    `${autoExecutionScopeLabel}细化已完成，正在同步章节执行资源`,
    DIRECTOR_PROGRESS.chapterDetailDone,
    {
      chapterId: selectedChapters[0]?.id ?? null,
      volumeId: selectedChapters[0]?.volumeId ?? null,
    },
  );
  let persistedChapters = await dependencies.novelContextService.listChapters(novelId);
  if (input.intent === "extend_outline" && extendChapterRange) {
    persistedChapters = persistedChapters.filter((chapter) => (
      chapter.order >= extendChapterRange.startOrder && chapter.order <= extendChapterRange.endOrder
    ));
  }
  if (persistedChapters.length === 0) {
    throw new Error("自动导演已生成拆章结果，但章节资源没有成功同步到执行区。");
  }
  const persistedChapterByOrder = new Map(persistedChapters.map((chapter) => [chapter.order, chapter] as const));
  // 懒规划（JIT）模式：task sheet 尚未预生成属预期状态，跳过执行上下文完整性检查。
  // 非 autopilot 路径仍做完整性检查，确保手动执行有完整 task sheet。
  if (!isFullBookAutopilotRunMode(request.runMode)) {
    const missingExecutionContextOrders = selectedChapterOrders.filter((order) => {
      const chapter = persistedChapterByOrder.get(order);
      return !chapter || !hasDirectorSyncedChapterExecutionContext(chapter);
    });
    if (missingExecutionContextOrders.length > 0) {
      throw new Error(
        `${autoExecutionScopeLabel}还有第 ${missingExecutionContextOrders.slice(0, 5).join("、")} 章缺少已同步的章节执行上下文，不能直接进入章节执行。请先补齐基础章节信息。`,
      );
    }
  }

  await dependencies.novelContextService.updateNovel(novelId, {
    projectStatus: "in_progress",
    storylineStatus: "in_progress",
    outlineStatus: "in_progress",
  });

  const autoExecutionState = buildDirectorAutoExecutionState({
    range: {
      startOrder: selectedChapterOrders[0] ?? 1,
      endOrder: selectedChapterOrders[selectedChapterOrders.length - 1] ?? selectedChapterOrders[0] ?? 1,
      totalChapterCount: targetChapterRange
        ? countDirectorAutoExecutionChapterRange(targetChapterRange)
        : selectedChapters.length,
      firstChapterId: selectedChapters[0]?.id ?? null,
    },
    chapters: persistedChapters.map((chapter) => ({
      id: chapter.id,
      order: chapter.order,
      content: chapter.content ?? null,
      conflictLevel: chapter.conflictLevel ?? null,
      revealLevel: chapter.revealLevel ?? null,
      targetWordCount: chapter.targetWordCount ?? null,
      mustAvoid: chapter.mustAvoid ?? null,
      taskSheet: chapter.taskSheet ?? null,
      sceneCards: chapter.sceneCards ?? null,
      generationState: chapter.generationState ?? null,
      chapterStatus: chapter.chapterStatus ?? null,
    })),
    plan: detailPlan,
    scopeLabel: autoExecutionScopeLabel,
    volumeTitle: detailPlan.mode === "volume" ? selectedChapters[0]?.volumeTitle ?? null : null,
    preparedVolumeIds,
    beatChapterListReady: syncCursor.beatChapterListReady,
    volumeChapterListComplete: syncCursor.volumeChapterListComplete,
  });

  const pausedSession = buildDirectorSessionState({
    runMode: request.runMode,
    phase: "chapter_execution",
    isBackgroundRunning: false,
  });
  // 全自动（full_book_autopilot）运行：消除「选择创作界面」人工硬门，
  // 直接自动通过并终止本次 runPipeline 传递；select() 内部已入队 continue 命令。
  if (isFullBookAutopilotRunMode(request.runMode)) {
    await new DirectorProductionExperienceService().autoPassForAutopilot(taskId);
    return;
  }
  await dependencies.workflowService.recordCheckpoint(taskId, {
    stage: "chapter_execution",
    checkpointType: "production_experience_required",
    checkpointSummary: `《${request.candidate.workingTitle.trim() || request.title?.trim() || "当前项目"}》已完成前期准备，请选择创作界面。`,
    itemLabel: `${autoExecutionScopeLabel}已可开写，等待选择创作界面`,
    volumeId: selectedChapters[0]?.volumeId ?? firstVolume.id,
    chapterId: selectedChapters[0]?.id ?? null,
    progress: DIRECTOR_PROGRESS.chapterBatchReady,
    seedPayload: callbacks.buildDirectorSeedPayload(request, novelId, {
      directorSession: pausedSession,
      autoExecution: autoExecutionState,
      startupPreparation: request.startupPreparation,
    }),
  });
  logMemoryUsage({
    event: "done",
    component: "runDirectorStructuredOutlinePhase",
    taskId,
    novelId,
    stage: "structured_outline",
    itemKey: "production_experience_required",
    scope: autoExecutionScopeLabel,
    entrypoint: "auto_director",
    volumeCount: persistedOutlineWorkspace.volumes.length,
    chapterCount: persistedOutlineWorkspace.volumes.reduce((sum, volume) => sum + volume.chapters.length, 0),
    beatSheetCount: persistedOutlineWorkspace.beatSheets.length,
  });
}
