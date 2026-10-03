/**
 * 续写（extend）的生成编排。
 *
 * 设计目标：让「确认并继续」在卷规划已耗尽、自动导演卡在 `chapter_batch_ready`
 * 的场景下，真正在【最后卷】内追加一段新的章节规划（继续主线），而不是原地打转。
 *
 * 复用既有 prompt 构造：
 * - 续写节奏段：复用 `volumeBeatSheetPrompt` + `buildVolumeBeatSheetContextBlocks`
 *   （与 `generateBeatSheet` 完全一致），但用续写引导语把生成范围框定在「最后卷之后衔接」。
 * - 续写章节列表：复用 `generateBeatChapterBlock`（即 `generateBeatChunkedChapterList`
 *   内部使用的单段拆章函数），逐段生成章节。
 *
 * 关键安全约束（PR #50 的 @unique 约束）：
 * - 本函数**不**调用 `mergeChapterList`，因为它会把整卷章节重排为 1-based 从而破坏
 *   已有的 82–89 章。所有新章节的 `chapterOrder` 由纯函数 `planExtendedVolumeDocument`
 *   从 `max(chapterOrder) + 1`（本项目为 90）开始连续分配。
 * - 新节奏段的 `chapterSpanHint` 会回写为实际生成的章节区间，确保结构化大纲恢复阶段
 *   不会误判章节列表未完成。
 */
import type { VolumePlanDocument } from "@ai-novel/shared/types/novel";
import { runStructuredPrompt } from "../../../prompting/core/promptRunner";
import { volumeBeatSheetPrompt } from "../../../prompting/prompts/novel/volume/beatSheet.prompts";
import { buildVolumeBeatSheetContextBlocks } from "../../../prompting/prompts/novel/volume/contextBlocks";
import { createVolumeChapterListPrompt } from "../../../prompting/prompts/novel/volume/chapterList.prompts";
import { buildVolumeChapterListContextBlocks } from "../../../prompting/prompts/novel/volume/contextBlocks";
import {
  getBeatExpectedChapterCount,
  type GeneratedVolumeChapterBlock,
} from "./volumeGenerationHelpers";
import { generateBeatChapterBlock } from "./volumeChapterListGeneration";
import { buildVolumeWorkspaceDocument } from "./volumeWorkspaceDocument";
import { loadGenerationContext } from "./volumeGenerationOrchestrator";
import {
  computeExtendNextOrder,
  EXTEND_MAX_NEW_CHAPTERS,
  planExtendedVolumeDocument,
  remapContinuationBeat,
} from "./volumeExtendPlanning";
import type {
  VolumeGenerateOptions,
  VolumeGenerationNovel,
  VolumeWorkspace,
} from "./volumeModels";
import type { StoryMacroPlanService } from "../storyMacro/StoryMacroPlanService";

type StoryMacroPlanResult = Awaited<ReturnType<StoryMacroPlanService["getPlan"]>> | null;

/** 续写节奏板的目标章节窗口：让 LLM 围绕「衔接后的前若干章」组织续写段。 */
export const EXTEND_BEAT_SHEET_TARGET_CHAPTER_COUNT = 12;

function buildExtendGuidance(params: {
  lastAbsoluteOrder: number;
  guidance?: string;
}): string {
  const lines = [
    `续写任务：当前主线已经写到第 ${params.lastAbsoluteOrder} 章。请在【当前最后卷】内继续推进主线，`
    + "承接已有剧情、人物状态与伏笔，自然衔接，写到本线在合理范围内的自然终点。",
    `不要新建卷，不要重复或改写已有章节。新增章节的全局序号从 ${params.lastAbsoluteOrder + 1} 开始连续递增。`,
    "节奏板请按「续写段」组织，覆盖衔接后的前若干章即可（不要试图覆盖全书或重置为 1 开始）。",
  ];
  if (params.guidance?.trim()) {
    lines.push(params.guidance.trim());
  }
  return lines.join("\n");
}

function notifyExtendPhaseStart(options: VolumeGenerateOptions): void {
  options.onPhaseStart?.({
    scope: "extend",
    phase: "prompt",
    label: "正在续写最后卷章节规划",
  });
}

export async function generateExtend(params: {
  novelId: string;
  workspace: VolumeWorkspace;
  options: VolumeGenerateOptions;
  storyMacroPlanService: Pick<StoryMacroPlanService, "getPlan">;
}): Promise<VolumePlanDocument> {
  const { novelId, workspace, options, storyMacroPlanService } = params;
  const baseDocument = buildVolumeWorkspaceDocument({
    novelId,
    volumes: workspace.volumes,
    strategyPlan: workspace.strategyPlan,
    critiqueReport: workspace.critiqueReport,
    beatSheets: workspace.beatSheets,
    rebalanceDecisions: workspace.rebalanceDecisions,
    source: workspace.source,
    activeVersionId: workspace.activeVersionId,
  });

  const sortedVolumes = baseDocument.volumes
    .slice()
    .sort((left, right) => right.sortOrder - left.sortOrder);
  const lastVolume = sortedVolumes[0];
  if (!lastVolume) {
    throw new Error("续写失败：当前没有可续写的卷。");
  }

  const nextOrder = computeExtendNextOrder(baseDocument);
  const lastAbsoluteOrder = nextOrder - 1;
  const { novel, storyMacroPlan } = await loadGenerationContext({
    novelId,
    workspace,
    storyMacroPlanService,
  });

  const targetChapterCount = Math.min(
    EXTEND_BEAT_SHEET_TARGET_CHAPTER_COUNT,
    EXTEND_MAX_NEW_CHAPTERS,
  );
  const continuationGuidance = buildExtendGuidance({ lastAbsoluteOrder, guidance: options.guidance });

  notifyExtendPhaseStart(options);

  // 1) 生成续写节奏段（复用 beat sheet prompt，卷内局部跨度从 1 开始，后续平移为全局序号）。
  const beatPromptInput = {
    novel,
    workspace: baseDocument,
    storyMacroPlan,
    strategyPlan: baseDocument.strategyPlan,
    targetVolume: lastVolume,
    targetChapterCount,
    guidance: continuationGuidance,
  };
  const beatGenerated = await runStructuredPrompt({
    asset: volumeBeatSheetPrompt,
    promptInput: beatPromptInput,
    contextBlocks: buildVolumeBeatSheetContextBlocks(beatPromptInput),
    options: {
      provider: options.provider,
      model: options.model,
      temperature: options.temperature ?? 0.35,
      maxTokens: 2_800,
      novelId: baseDocument.novelId,
      volumeId: lastVolume.id,
      taskId: options.taskId,
      stage: "structured_outline",
      itemKey: "beat_sheet",
      scope: "extend",
      entrypoint: options.entrypoint,
      signal: options.signal,
    },
  });

  const rawBeats = beatGenerated.output.beats;
  const continuationBeats = rawBeats.map((beat, index) => (
    remapContinuationBeat(beat, index, lastAbsoluteOrder)
  ));

  // 2) 逐段生成章节列表（复用 generateBeatChapterBlock），并严格限制新增章节总数。
  const generatedBlocks: GeneratedVolumeChapterBlock[] = [];
  let totalNewChapters = 0;
  for (const beat of continuationBeats) {
    if (totalNewChapters >= EXTEND_MAX_NEW_CHAPTERS) {
      break;
    }
    const chapterCount = Math.min(
      Math.max(1, getBeatExpectedChapterCount(beat)),
      EXTEND_MAX_NEW_CHAPTERS - totalNewChapters,
    );
    const startOrder = lastAbsoluteOrder + 1 + totalNewChapters;
    const endOrder = startOrder + chapterCount - 1;

    const block = await generateBeatChapterBlock({
      document: baseDocument,
      workspace: baseDocument,
      novel,
      storyMacroPlan,
      options,
      targetVolume: lastVolume,
      targetBeatSheet: {
        volumeId: lastVolume.id,
        volumeSortOrder: lastVolume.sortOrder,
        status: "generated",
        beats: continuationBeats,
      },
      beatPlan: {
        beat,
        chapterCount,
        chapterStartOrder: startOrder,
        chapterEndOrder: endOrder,
      },
      previousBeat: null,
      nextBeat: null,
      previousBeatChapterSummary: null,
      preservedBeatChapterSummary: null,
      chapterBudgets: [],
    });
    generatedBlocks.push(block);
    totalNewChapters += block.chapters.length;
  }

  if (generatedBlocks.length === 0) {
    throw new Error("续写失败：未能生成任何续写章节规划。");
  }

  // 仅保留实际生成了章节的节奏段，保证 newBeats 与 generatedBlocks 一一对应。
  const usedBeats = continuationBeats.slice(0, generatedBlocks.length);

  return planExtendedVolumeDocument({
    baseDocument,
    newBeats: usedBeats,
    generatedBlocks,
  });
}
