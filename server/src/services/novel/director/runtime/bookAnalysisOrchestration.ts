/**
 * Headless orchestration for reference-book analysis in the AI Director autopilot
 * pipeline (Phase 4 — foundation, task 4a).
 *
 * Wires together the existing, server-side services so that a caller (e.g. the
 * `analyze_reference_book` director command) can:
 *   1. ingest raw reference text as a knowledge document (KnowledgeService),
 *   2. ensure rule-based chapter splits exist (DocumentChapterService),
 *   3. kick off a BookAnalysis and poll it to completion (BookAnalysisService).
 *
 * This module does NOT call any LLM directly — it only orchestrates services
 * that already exist. It is dependency-injected so it can be unit-tested with
 * mock services (matching the repo's `deps` pattern used across the director
 * runtime).
 */

import { randomUUID } from "node:crypto";
import type { LLMProvider } from "@ai-novel/shared/types/llm";
import type {
  BookAnalysisDetail,
  BookAnalysisSectionKey,
  BookAnalysisStatus,
} from "@ai-novel/shared/types/bookAnalysis";
import { bookAnalysisService } from "../../../bookAnalysis/BookAnalysisService";
import { KnowledgeService } from "../../../knowledge/KnowledgeService";
import { DocumentChapterService } from "../../../knowledge/DocumentChapterService";

/** Result of ingesting raw text as a knowledge document. */
export interface IngestTextAsDocumentResult {
  documentId: string;
  versionId: string;
}

/** Options accepted by {@link BookAnalysisOrchestration.runBookAnalysis}. */
export interface RunBookAnalysisOptions {
  provider?: LLMProvider;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  budgetTokens?: number | null;
  includeTimeline?: boolean;
  enabledSectionKeys?: BookAnalysisSectionKey[];
  /** Maximum time to wait for completion. Defaults to 20 minutes. */
  timeoutMs?: number;
  /** Poll interval. Defaults to 5 seconds. */
  pollIntervalMs?: number;
}

/** Result of running a book analysis to completion. */
export interface RunBookAnalysisResult {
  analysisId: string;
  analysis: BookAnalysisDetail;
}

/** Options accepted by {@link BookAnalysisOrchestration.ingestAndAnalyze}. */
export interface IngestAndAnalyzeOptions extends RunBookAnalysisOptions {
  /**
   * If provided, analysis runs directly on this already-ingested document and
   * the ingestion step is skipped (used when the caller already created the
   * knowledge document out-of-band).
   */
  existingDocumentId?: string;
}

/** Result of the combined ingest + analyze flow. */
export interface IngestAndAnalyzeResult {
  documentId: string;
  versionId: string;
  analysisId: string;
  analysis: BookAnalysisDetail;
}

/** Injectable collaborators for the orchestration (enables unit testing). */
export interface BookAnalysisOrchestrationDeps {
  bookAnalysisService: typeof bookAnalysisService;
  knowledgeService: KnowledgeService;
  documentChapterService: DocumentChapterService;
  /** Async sleep used between polls. */
  sleep: (ms: number) => Promise<void>;
  /** Current epoch-ms clock, used for the timeout check. */
  now: () => number;
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const DEFAULT_TIMEOUT_MS = 20 * 60 * 1000;
const DEFAULT_POLL_INTERVAL_MS = 5000;

/**
 * Headless orchestrator that turns reference text into a completed book analysis.
 *
 * The default instance (`bookAnalysisOrchestration`) wires the real server
 * singletons. Unit tests should construct their own instance with mock deps.
 */
export class BookAnalysisOrchestration {
  private readonly deps: BookAnalysisOrchestrationDeps;

  constructor(deps: Partial<BookAnalysisOrchestrationDeps> = {}) {
    this.deps = {
      bookAnalysisService: deps.bookAnalysisService ?? bookAnalysisService,
      knowledgeService: deps.knowledgeService ?? new KnowledgeService(),
      documentChapterService: deps.documentChapterService ?? new DocumentChapterService(),
      sleep: deps.sleep ?? defaultSleep,
      now: deps.now ?? (() => Date.now()),
    };
  }

  /**
   * Ingest raw reference text as a knowledge document and ensure its chapters
   * are split. A unique title/fileName suffix is appended so the
   * title-dedup path in KnowledgeService never silently appends a version to an
   * unrelated document.
   */
  async ingestTextAsDocument(title: string, content: string): Promise<IngestTextAsDocumentResult> {
    const uniqueSuffix = randomUUID().slice(0, 8);
    const baseTitle = title?.trim() || "参考资料";
    const safeTitle = `${baseTitle} · ${uniqueSuffix}`;
    const safeFileName = `${baseTitle.replace(/[^\w一-龥-]+/g, "_")}_${uniqueSuffix}.txt`;

    const detail = await this.deps.knowledgeService.createDocument({
      title: safeTitle,
      fileName: safeFileName,
      content,
    });

    const versionId = detail.activeVersionId;
    if (!versionId) {
      throw new Error("知识文档创建后缺少激活版本（activeVersionId）。");
    }

    await this.deps.documentChapterService.ensureChaptersForVersion(versionId, detail.id);

    return { documentId: detail.id, versionId };
  }

  /**
   * Create a book analysis for the given document and poll until it reaches a
   * terminal state. Resolves with the completed detail on "succeeded"; throws on
   * "failed" / "cancelled" / disappearance / timeout.
   */
  async runBookAnalysis(
    documentId: string,
    options: RunBookAnalysisOptions = {},
  ): Promise<RunBookAnalysisResult> {
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;

    const created = await this.deps.bookAnalysisService.createAnalysis({
      documentId,
      provider: options.provider,
      model: options.model,
      temperature: options.temperature,
      maxTokens: options.maxTokens,
      budgetTokens: options.budgetTokens,
      includeTimeline: options.includeTimeline,
      enabledSectionKeys: options.enabledSectionKeys,
    });

    const analysisId = created.id;
    const deadline = this.deps.now() + timeoutMs;

    // Poll until a terminal state is reached.
    for (;;) {
      await this.deps.sleep(pollIntervalMs);
      const detail = await this.deps.bookAnalysisService.getAnalysisById(analysisId);
      if (!detail) {
        throw new Error(`Book analysis ${analysisId} disappeared during polling.`);
      }
      const status: BookAnalysisStatus = detail.status;
      if (status === "succeeded") {
        return { analysisId, analysis: detail };
      }
      if (status === "failed" || status === "cancelled") {
        throw new Error(
          `Book analysis ${analysisId} ended with status "${status}": ${detail.lastError ?? "unknown error"}`,
        );
      }
      if (this.deps.now() >= deadline) {
        throw new Error(
          `Book analysis ${analysisId} timed out after ${timeoutMs}ms (last status "${status}").`,
        );
      }
    }
  }

  /**
   * Convenience flow: ingest (unless an existing document is provided) then run
   * the analysis to completion.
   */
  async ingestAndAnalyze(
    title: string,
    content: string,
    options: IngestAndAnalyzeOptions = {},
  ): Promise<IngestAndAnalyzeResult> {
    let documentId: string;
    let versionId: string;

    if (options.existingDocumentId) {
      documentId = options.existingDocumentId;
      versionId = "";
    } else {
      const ingested = await this.ingestTextAsDocument(title, content);
      documentId = ingested.documentId;
      versionId = ingested.versionId;
    }

    const { analysisId, analysis } = await this.runBookAnalysis(documentId, options);

    return { documentId, versionId, analysisId, analysis };
  }
}

/** Default shared orchestrator wired to the real server services. */
export const bookAnalysisOrchestration = new BookAnalysisOrchestration();

/** Functional wrapper delegating to the default {@link bookAnalysisOrchestration}. */
export function ingestTextAsDocument(title: string, content: string): Promise<IngestTextAsDocumentResult> {
  return bookAnalysisOrchestration.ingestTextAsDocument(title, content);
}

/** Functional wrapper delegating to the default {@link bookAnalysisOrchestration}. */
export function runBookAnalysis(
  documentId: string,
  options?: RunBookAnalysisOptions,
): Promise<RunBookAnalysisResult> {
  return bookAnalysisOrchestration.runBookAnalysis(documentId, options);
}

/** Functional wrapper delegating to the default {@link bookAnalysisOrchestration}. */
export function ingestAndAnalyze(
  title: string,
  content: string,
  options?: IngestAndAnalyzeOptions,
): Promise<IngestAndAnalyzeResult> {
  return bookAnalysisOrchestration.ingestAndAnalyze(title, content, options);
}
