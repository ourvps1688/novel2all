/**
 * 续写（extend）的纯函数规划工具。
 *
 * 这些函数不依赖数据库、LLM 或任何运行时服务，只负责在已有的
 * `VolumePlanDocument` 之上构造「在最后卷内追加新节奏段 + 新章节规划」的结果文档。
 * 所有章节序号（chapterOrder）都是全局连续递增的，因此可以直接交给
 * `VolumeChapterSyncService` 按 `chapterOrder` 作为 `order` 落库，而不会产生
 * `@unique([volumeId, chapterOrder])` 或 `@unique([novelId, order])` 冲突。
 *
 * 关键不变量：
 * - 已有卷/章节（例如本项目的 82–89 章）保持完全不变。
 * - 新追加的章节从 `max(chapterOrder) + 1` 继续编号（本项目为 90）。
 * - 每个新节奏段的 `chapterSpanHint` 严格等于它实际生成的章节区间，使
 *   `getBeatExpectedChapterCount(beat) === 实际章节数`，避免结构化大纲恢复阶段误判
 *   章节列表未完成而触发 `mergeChapterList`（后者会把整卷章节重排为 1-based）。
 */
import { randomUUID } from "node:crypto";
import type {
  VolumeBeat,
  VolumeChapterPlan,
  VolumePlanDocument,
} from "@ai-novel/shared/types/novel";
import { buildVolumeWorkspaceDocument } from "./volumeWorkspaceDocument";
import type { GeneratedVolumeChapterBlock } from "./volumeGenerationHelpers";

/** 单次续写最多新增的章节数，用于约束 LLM 成本与潜在的数据膨胀。 */
export const EXTEND_MAX_NEW_CHAPTERS = 30;

const EPOCH = new Date(0).toISOString();

function createExtendChapterId(): string {
  return `extend-chapter-${randomUUID()}`;
}

/**
 * 计算续写起始序号：已存在章节的最大 `chapterOrder` + 1。
 * 本项目最后卷章节到 89，因此返回 90。
 */
export function computeExtendNextOrder(baseDocument: VolumePlanDocument): number {
  const maxOrder = baseDocument.volumes.reduce(
    (max, volume) => volume.chapters.reduce(
      (volumeMax, chapter) => Math.max(volumeMax, chapter.chapterOrder),
      max,
    ),
    -Infinity,
  );
  if (!Number.isFinite(maxOrder)) {
    return 1;
  }
  return Math.max(1, maxOrder + 1);
}

/**
 * 将「卷内局部」的章节跨度提示（例如 "1-2章"）整体平移为全局绝对序号。
 * 续写段在最后卷之后衔接，因此偏移量取「最后已存在章节的绝对序号」。
 */
export function shiftChapterSpanHintToAbsolute(hint: string, offset: number): string {
  const matches = hint.match(/\d+/g);
  if (!matches || matches.length === 0) {
    return hint;
  }
  const numbers = matches.map((raw) => Number.parseInt(raw, 10) + offset);
  if (numbers.length === 1) {
    return `${numbers[0]}章`;
  }
  return `${numbers[0]}-${numbers[numbers.length - 1]}`;
}

/**
 * 把 LLM 生成的续写节奏段重映射为「续写专用」节奏段：
 * - 使用唯一 key（extend-${index}），避免与最后卷已有固定职能槽位 key 冲突；
 * - 标签使用非固定职能名（续写段${index}），避免被 normalizeBeat 重新解析回固定槽位；
 * - 章节跨度提示平移为全局绝对序号。
 */
export function remapContinuationBeat(
  beat: VolumeBeat,
  index: number,
  lastAbsoluteOrder: number,
): VolumeBeat {
  const shiftedHint = shiftChapterSpanHintToAbsolute(beat.chapterSpanHint, lastAbsoluteOrder);
  return {
    key: `extend-${index}`,
    label: `续写段${index}`,
    title: beat.title || `续写段${index}`,
    summary: beat.summary,
    chapterSpanHint: shiftedHint,
    mustDeliver: beat.mustDeliver.length > 0
      ? beat.mustDeliver
      : ["继续当前主线，自然衔接已有剧情。"],
  };
}

/**
 * 在最后卷内追加续写节奏段与新章节规划，构造结果 `VolumePlanDocument`。
 *
 * 约定：`newBeats[i]` 与 `generatedBlocks[i]` 一一对应。函数会根据实际生成的章节数
 * 回写每个新节奏段的 `chapterSpanHint`，保证「预期章节数 === 实际章节数」。
 *
 * 该函数不会改动任何已有卷/章节的内容或序号。
 */
export function planExtendedVolumeDocument(params: {
  baseDocument: VolumePlanDocument;
  newBeats: VolumeBeat[];
  generatedBlocks: GeneratedVolumeChapterBlock[];
}): VolumePlanDocument {
  const { baseDocument, newBeats, generatedBlocks } = params;
  const sortedVolumes = baseDocument.volumes
    .slice()
    .sort((left, right) => right.sortOrder - left.sortOrder);
  const lastVolume = sortedVolumes[0];
  if (!lastVolume) {
    throw new Error("续写失败：当前工作台文档没有可续写的卷。");
  }

  const nextOrder = computeExtendNextOrder(baseDocument);
  let counter = nextOrder;

  const newChapters: VolumeChapterPlan[] = [];
  const adjustedBeats: VolumeBeat[] = [];

  for (let index = 0; index < newBeats.length; index += 1) {
    const beat = newBeats[index];
    const block = generatedBlocks[index];
    if (!block || block.chapters.length === 0) {
      continue;
    }

    const startOrder = counter;
    const beatChapterIds: string[] = [];
    const beatChapters: VolumeChapterPlan[] = block.chapters.map((chapter) => {
      const chapterOrder = counter;
      counter += 1;
      beatChapterIds.push(createExtendChapterId());
      return {
        id: beatChapterIds[beatChapterIds.length - 1],
        volumeId: lastVolume.id,
        chapterId: null,
        chapterOrder,
        beatKey: beat.key,
        title: chapter.title || `第${chapterOrder}章`,
        summary: chapter.summary || "",
        purpose: null,
        exclusiveEvent: null,
        endingState: null,
        nextChapterEntryState: null,
        conflictLevel: null,
        conflictLevelSource: null,
        revealLevel: null,
        targetWordCount: null,
        mustAvoid: null,
        taskSheet: null,
        sceneCards: null,
        styleContract: null,
        payoffRefs: [],
        createdAt: EPOCH,
        updatedAt: EPOCH,
      };
    });
    const endOrder = counter - 1;

    newChapters.push(...beatChapters);
    adjustedBeats.push({
      ...beat,
      chapterSpanHint: `${startOrder}-${endOrder}`,
    });
  }

  const extendedVolumes = baseDocument.volumes.map((volume) => (
    volume.id === lastVolume.id
      ? { ...volume, chapters: [...volume.chapters, ...newChapters] }
      : volume
  ));

  let beatSheets = baseDocument.beatSheets;
  const existingSheet = beatSheets.find((sheet) => sheet.volumeId === lastVolume.id);
  if (existingSheet) {
    beatSheets = beatSheets.map((sheet) => (
      sheet.volumeId === lastVolume.id
        ? { ...sheet, beats: [...sheet.beats, ...adjustedBeats] }
        : sheet
    ));
  } else {
    beatSheets = [
      ...beatSheets,
      {
        volumeId: lastVolume.id,
        volumeSortOrder: lastVolume.sortOrder,
        status: "generated" as const,
        beats: adjustedBeats,
      },
    ];
  }

  return buildVolumeWorkspaceDocument({
    novelId: baseDocument.novelId,
    volumes: extendedVolumes,
    strategyPlan: baseDocument.strategyPlan,
    critiqueReport: baseDocument.critiqueReport,
    beatSheets,
    rebalanceDecisions: baseDocument.rebalanceDecisions,
    source: baseDocument.source,
    activeVersionId: baseDocument.activeVersionId,
  });
}
