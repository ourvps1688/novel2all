/**
 * Historical execution-contract backfill.
 *
 * Novels created before the AI Director / full_book_autopilot pipeline existed may
 * have chapters WITHOUT an execution contract (task sheet + scene cards). The
 * autopilot runtime expects every executable chapter to carry one. This module is
 * a safe, best-effort, idempotent repair utility that generates the missing
 * contracts by reusing the existing generator
 * (`ChapterExecutionContractService.ensureChapterExecutionContract`).
 *
 * Design constraints (repo policy):
 * - ZERO schema / data migration. We reuse the existing chapter columns and the
 *   existing generator's persistence path.
 * - Never let a single bad chapter abort the whole backfill. A failure (e.g.
 *   `findVolumeChapterMatch` throwing because the chapter is not mapped into the
 *   current volume plan) is caught and recorded in the returned summary.
 * - `ensureChapterExecutionContract` already persists on its own through
 *   `runVolumeWorkspaceTransaction`, so we do NOT separately call updateChapter.
 */
import { prisma } from "../../../../db/prisma";

export interface HistoricalExecutionContractBackfillChapterRow {
  id: string;
  novelId: string;
  order: number;
  title?: string | null;
  taskSheet?: string | null;
  sceneCards?: string | null;
}

export interface HistoricalExecutionContractBackfillDeps {
  listChapters: (novelId: string) => Promise<HistoricalExecutionContractBackfillChapterRow[]>;
  ensureChapterExecutionContract: (
    novelId: string,
    chapterId: string,
    options?: Record<string, unknown>,
  ) => Promise<unknown>;
}

export interface HistoricalExecutionContractBackfillOptions {
  provider?: string;
  model?: string;
  temperature?: number;
  guidance?: string;
  entrypoint?: string;
  taskStyleProfileId?: string;
}

export interface HistoricalExecutionContractBackfillError {
  chapterId: string;
  chapterOrder?: number;
  error: string;
}

export interface HistoricalExecutionContractBackfillResult {
  novelId: string;
  totalChapters: number;
  backfilled: number;
  skipped: number;
  errors: HistoricalExecutionContractBackfillError[];
}

export interface HistoricalExecutionContractBackfillInput {
  novelId: string;
  options?: HistoricalExecutionContractBackfillOptions;
}

/**
 * A chapter is considered to already have an execution contract only when it
 * carries BOTH a task sheet and scene cards. This is intentionally conservative:
 * a chapter with only one of the two artifacts is still treated as incomplete
 * and eligible for (re)generation.
 */
export function hasExecutionContract(chapter: {
  taskSheet?: string | null;
  sceneCards?: string | null;
}): boolean {
  return Boolean(chapter.taskSheet?.trim()) && Boolean(chapter.sceneCards?.trim());
}

/**
 * Production chapter lister. Mirrors the prisma access pattern already used by
 * `VolumeChapterSyncService` (it queries `prisma.chapter` directly) and reuses
 * the existing `chapter` columns — no new query path or schema change.
 */
export function listNovelChaptersForContractBackfill(
  novelId: string,
): Promise<HistoricalExecutionContractBackfillChapterRow[]> {
  return prisma.chapter.findMany({
    where: { novelId },
    orderBy: { order: "asc" },
    select: {
      id: true,
      novelId: true,
      order: true,
      title: true,
      taskSheet: true,
      sceneCards: true,
    },
  });
}

/**
 * Generate missing execution contracts for every chapter of a novel that lacks
 * one. Idempotent and crash-safe: a single chapter failure is collected into the
 * returned summary rather than thrown.
 */
export async function backfillMissingExecutionContracts(
  deps: HistoricalExecutionContractBackfillDeps,
  input: HistoricalExecutionContractBackfillInput,
): Promise<HistoricalExecutionContractBackfillResult> {
  const { novelId } = input;
  const options = input.options ?? {};
  const chapters = await deps.listChapters(novelId);

  const result: HistoricalExecutionContractBackfillResult = {
    novelId,
    totalChapters: chapters.length,
    backfilled: 0,
    skipped: 0,
    errors: [],
  };

  for (const chapter of chapters) {
    if (hasExecutionContract(chapter)) {
      result.skipped += 1;
      continue;
    }
    try {
      await deps.ensureChapterExecutionContract(novelId, chapter.id, {
        entrypoint: "auto_director",
        ...options,
      });
      result.backfilled += 1;
    } catch (error) {
      // `ensureChapterExecutionContract` may throw internally (e.g. when
      // `findVolumeChapterMatch` cannot map the historical chapter into the
      // current volume plan). Record it and keep going.
      result.errors.push({
        chapterId: chapter.id,
        chapterOrder: chapter.order,
        error: error instanceof Error ? error.message : "未知错误",
      });
    }
  }

  return result;
}
