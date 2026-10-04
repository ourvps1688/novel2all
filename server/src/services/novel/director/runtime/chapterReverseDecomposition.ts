/**
 * Reverse decomposition of written chapters (Phase 4 T4.2).
 *
 * For B-mode (continuation) autopilot resume, a novel may already have WRITTEN
 * chapters whose internal planning artifacts (Chapter.taskSheet + Chapter.sceneCards)
 * are missing. This service reverse-generates those artifacts from the finished
 * prose plus the novel's book analysis (used as EVIDENCE of intent), persists them
 * to the existing chapter columns, and then reuses the existing
 * `ChapterExecutionContractService.ensureChapterExecutionContract` to populate the
 * rest of the execution contract "for free".
 *
 * Design constraints (repo policy):
 * - ZERO schema / migration. We only write to the existing `taskSheet` /
 *   `sceneCards` columns and reuse the existing execution-contract generator.
 * - Idempotent: a chapter that already has BOTH `taskSheet` and `sceneCards` is
 *   skipped (unless `force: true`) — no LLM call, no writes.
 * - The beat sheet is volume-level and owned by the existing generator; we capture
 *   a lightweight 章法定位 line appended to the task sheet instead of writing a
 *   risky volume-level beat sheet. (Documented scoping decision.)
 * - Utility-class command (no checkpoint / no continue-enqueue / no approval):
 *   see `decompose_written_chapter` in the director command wiring.
 */
import { prisma } from "../../../../db/prisma";
import {
  normalizeChapterScenePlan,
  serializeChapterScenePlan,
} from "@ai-novel/shared/types/chapterLengthControl";
import type { BookAnalysisSectionKey } from "@ai-novel/shared/types/bookAnalysis";
import { runStructuredPrompt } from "../../../../prompting/core/promptRunner";
import { reverseDecomposeChapterPrompt } from "../../../../prompting/prompts/novel/reverseDecomposeChapter.prompts";
import { NovelCoreCrudService } from "../../novelCoreCrudService";
import { novelReferenceService } from "../../NovelReferenceService";
import { NovelVolumeService } from "../../volume/NovelVolumeService";

const novelCoreCrudService = new NovelCoreCrudService();
const novelVolumeService = new NovelVolumeService();

const DEFAULT_EVIDENCE_SECTION_KEYS: BookAnalysisSectionKey[] = [
  "plot_structure",
  "timeline",
  "character_system",
  "worldbuilding",
];

export interface ReverseDecomposeChapterGetChapterRow {
  id?: string;
  novelId: string;
  title?: string | null;
  order?: number | null;
  content: string | null;
  taskSheet?: string | null;
  sceneCards?: string | null;
}

export interface ChapterReverseDecompositionOptions {
  provider?: string;
  model?: string;
  temperature?: number;
  force?: boolean;
  sectionKeys?: BookAnalysisSectionKey[];
}

export interface ChapterReverseDecompositionDeps {
  promptRunner?: typeof runStructuredPrompt;
  getChapter?: (novelId: string, chapterId: string) => Promise<ReverseDecomposeChapterGetChapterRow>;
  listChapters?: (novelId: string) => Promise<Array<{ id: string }>>;
  updateChapterArtifacts?: (
    novelId: string,
    chapterId: string,
    artifacts: { taskSheet: string; sceneCards: string },
  ) => Promise<void>;
  getNovelConfig?: (
    novelId: string,
  ) => Promise<{ writingMode: string | null; analysisId: string | null }>;
  buildAnalysisEvidence?: (
    analysisId: string | null | undefined,
    stage: string,
    sectionKeys?: BookAnalysisSectionKey[] | null,
  ) => Promise<string>;
  ensureExecutionContract?: (
    novelId: string,
    chapterId: string,
    options?: ChapterReverseDecompositionOptions,
  ) => Promise<unknown>;
}

export interface DecomposeChapterResult {
  chapterId: string;
  taskSheet: string;
  sceneCards: string;
  skipped: boolean;
}

export interface DecomposeNovelResult {
  decomposed: string[];
  skipped: string[];
}

export class ChapterReverseDecomposition {
  private readonly deps: Required<ChapterReverseDecompositionDeps>;

  constructor(deps: ChapterReverseDecompositionDeps = {}) {
    this.deps = {
      promptRunner: deps.promptRunner ?? runStructuredPrompt,
      getChapter: deps.getChapter ?? this.defaultGetChapter,
      listChapters: deps.listChapters ?? this.defaultListChapters,
      updateChapterArtifacts: deps.updateChapterArtifacts ?? this.defaultUpdateChapterArtifacts,
      getNovelConfig: deps.getNovelConfig ?? this.defaultGetNovelConfig,
      buildAnalysisEvidence: deps.buildAnalysisEvidence ?? this.defaultBuildAnalysisEvidence,
      ensureExecutionContract: deps.ensureExecutionContract ?? this.defaultEnsureExecutionContract,
    };
  }

  private readonly defaultGetChapter = async (
    novelId: string,
    chapterId: string,
  ): Promise<ReverseDecomposeChapterGetChapterRow> => {
    const row = await prisma.chapter.findFirst({
      where: { id: chapterId, novelId },
      select: {
        id: true,
        novelId: true,
        title: true,
        order: true,
        content: true,
        taskSheet: true,
        sceneCards: true,
      },
    });
    if (!row) {
      throw new Error("章节不存在。");
    }
    return row;
  };

  private readonly defaultListChapters = async (
    novelId: string,
  ): Promise<Array<{ id: string }>> => {
    const chapters = await novelCoreCrudService.listChapters(novelId);
    return chapters.map((chapter) => ({ id: chapter.id }));
  };

  private readonly defaultUpdateChapterArtifacts = async (
    novelId: string,
    chapterId: string,
    artifacts: { taskSheet: string; sceneCards: string },
  ): Promise<void> => {
    await novelCoreCrudService.updateChapter(novelId, chapterId, {
      taskSheet: artifacts.taskSheet,
      sceneCards: artifacts.sceneCards,
    });
  };

  private readonly defaultGetNovelConfig = async (
    novelId: string,
  ): Promise<{ writingMode: string | null; analysisId: string | null }> => {
    const row = await prisma.novel.findFirst({
      where: { id: novelId },
      select: {
        writingMode: true,
        continuationBookAnalysisId: true,
        referenceBookAnalysisId: true,
      },
    });
    if (!row) {
      return { writingMode: null, analysisId: null };
    }
    const analysisId = row.writingMode === "continuation" && row.continuationBookAnalysisId
      ? row.continuationBookAnalysisId
      : row.referenceBookAnalysisId;
    return { writingMode: row.writingMode, analysisId: analysisId ?? null };
  };

  private readonly defaultBuildAnalysisEvidence = (
    analysisId: string | null | undefined,
    stage: string,
    sectionKeys?: BookAnalysisSectionKey[] | null,
  ): Promise<string> => {
    return novelReferenceService.buildReferenceFromAnalysisId(
      analysisId,
      stage as Parameters<typeof novelReferenceService.buildReferenceFromAnalysisId>[1],
      sectionKeys,
    );
  };

  private readonly defaultEnsureExecutionContract = (
    novelId: string,
    chapterId: string,
    options?: ChapterReverseDecompositionOptions,
  ): Promise<unknown> => {
    return novelVolumeService.ensureChapterExecutionContract(
      novelId,
      chapterId,
      {
        provider: options?.provider,
        model: options?.model,
        temperature: options?.temperature,
      },
    );
  };

  async decompose(
    novelId: string,
    chapterId: string,
    options: ChapterReverseDecompositionOptions = {},
  ): Promise<DecomposeChapterResult> {
    const chapter = await this.deps.getChapter(novelId, chapterId);
    if (!chapter) {
      throw new Error("章节不存在。");
    }

    // Idempotent skip: a chapter that already carries BOTH artifacts is considered
    // fully reverse-decomposed. Skipping avoids an unnecessary LLM call and writes.
    if (!options.force && chapter.taskSheet?.trim() && chapter.sceneCards?.trim()) {
      return {
        chapterId,
        taskSheet: chapter.taskSheet ?? "",
        sceneCards: chapter.sceneCards ?? "",
        skipped: true,
      };
    }

    const config = await this.deps.getNovelConfig(novelId);
    const evidence = config.analysisId
      ? await this.deps.buildAnalysisEvidence(
        config.analysisId,
        "outline",
        options.sectionKeys ?? DEFAULT_EVIDENCE_SECTION_KEYS,
      )
      : "";

    const parsed = await this.deps.promptRunner({
      asset: reverseDecomposeChapterPrompt,
      promptInput: {
        chapterTitle: chapter.title || (chapter.order != null ? `第${chapter.order}章` : "本章"),
        chapterContent: chapter.content ?? "",
        analysisEvidence: evidence,
        targetWordCount: undefined,
      },
      options: {
        provider: options.provider,
        model: options.model,
        temperature: options.temperature ?? 0.3,
        novelId,
        taskId: undefined,
        stage: "reverse_decomp",
        itemKey: `chapter_${chapterId}`,
        entrypoint: "auto_director",
      },
    });

    const { taskSheet: rawTaskSheet, scenePlan, beatNote } = parsed.output;

    // Compose the final task sheet, appending the 章法定位 line when present, and
    // guarantee it never exceeds the 600-char contract.
    let finalTaskSheet = rawTaskSheet;
    if (beatNote && beatNote.trim()) {
      const prefix = "\n章法定位：";
      const budget = 600 - finalTaskSheet.length - prefix.length;
      const note = budget > 0 ? beatNote.trim().slice(0, budget) : "";
      if (note) {
        finalTaskSheet += prefix + note;
      }
    }
    if (finalTaskSheet.length > 600) {
      finalTaskSheet = finalTaskSheet.slice(0, 600);
    }

    // Complete the relaxed LLM scene plan into a canonical ChapterScenePlan
    // (lengthBudget + readerExperience are derived), then serialize.
    const normalizedScenePlan = normalizeChapterScenePlan(scenePlan, scenePlan.targetWordCount);
    const sceneCardsJson = serializeChapterScenePlan(normalizedScenePlan);

    await this.deps.updateChapterArtifacts(novelId, chapterId, {
      taskSheet: finalTaskSheet,
      sceneCards: sceneCardsJson,
    });

    // Reuse the existing execution-contract generator to populate the rest of the
    // contract (expectation / targetWordCount / conflictLevel / revealLevel /
    // mustAvoid / hook + VolumeChapterPlan columns + story-plan hash) for free.
    // This is best-effort: when the chapter cannot be matched into a volume plan
    // (e.g. foreign continuation chapters), the reverse-decomp artifacts already
    // written above are the valuable output, so we surface a warning and continue.
    try {
      await this.deps.ensureExecutionContract(novelId, chapterId, {
        provider: options.provider,
        model: options.model,
        temperature: options.temperature,
      });
    } catch (error) {
      console.warn("[chapter-reverse-decomposition] ensureChapterExecutionContract skipped.", {
        novelId,
        chapterId,
        error: error instanceof Error ? error.message : String(error),
      });
    }

    return {
      chapterId,
      taskSheet: finalTaskSheet,
      sceneCards: sceneCardsJson,
      skipped: false,
    };
  }

  async decomposeNovel(
    novelId: string,
    options: ChapterReverseDecompositionOptions = {},
  ): Promise<DecomposeNovelResult> {
    const chapters = await this.deps.listChapters(novelId);
    const decomposed: string[] = [];
    const skipped: string[] = [];
    for (const chapter of chapters) {
      const result = await this.decompose(novelId, chapter.id, options);
      if (result.skipped) {
        skipped.push(chapter.id);
      } else {
        decomposed.push(chapter.id);
      }
    }
    return { decomposed, skipped };
  }
}

export const chapterReverseDecomposition = new ChapterReverseDecomposition();
