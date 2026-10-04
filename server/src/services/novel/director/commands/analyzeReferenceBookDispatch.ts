/**
 * Standalone, dependency-light dispatch for the `analyze_reference_book`
 * director command (Phase 4 — foundation, task 4c; autopilot bridge added in
 * task T4.5).
 *
 * This is intentionally a *pure* function with **type-only** imports so the
 * compiled module has no runtime dependency on the heavy director service
 * graph. That keeps it unit-testable in isolation — the `DirectorCommandExecutor`
 * class cannot be required in a standalone test process because its dependency
 * graph contains a pre-existing circular import that crashes at module load
 * (`NovelVolumeService is not a constructor`). By extracting the command's
 * dispatch logic here, tests can cover the real execution behavior of
 * `analyze_reference_book` without loading that fragile graph.
 *
 * No Prisma / LLM calls happen here: the orchestration, the result recorder,
 * and the novel-binding collaborators are injected.
 *
 * When a `novelId` is supplied and the novel has a known writing mode, the
 * produced `analysisId` is bound to the matching column on the `Novel` row
 * (`referenceBookAnalysisId` for `original`, `continuationBookAnalysisId` for
 * `continuation`) via `bindAnalysisToNovel`, and the same column is written
 * into the task seed payload (`seedPatch`) so the downstream director stages
 * can reach the bound analysis from the `DirectorConfirmRequest`.
 */

import type { LLMProvider } from "@ai-novel/shared/types/llm";
import type { BookAnalysisOrchestration } from "../runtime/bookAnalysisOrchestration";
import type { DirectorCommandExecutionOutcome } from "./DirectorCommandExecutor";

/** The two writing modes that map to a distinct bound-analysis column. */
export type NovelWritingMode = "original" | "continuation";

/** Parsed payload of the `analyze_reference_book` command. */
export interface AnalyzeReferenceBookDispatchRequest {
  title?: string | null;
  referenceText: string;
  documentId?: string | null;
  provider?: string | null;
  model?: string | null;
  temperature?: number | null;
  /** Target novel whose bound analysis column should be updated (optional). */
  novelId?: string | null;
}

/** Collaborators the dispatch needs, all injectable for testing. */
export interface AnalyzeReferenceBookDispatchDeps {
  bookAnalysisOrchestration: BookAnalysisOrchestration;
  recordCommandResult: (
    taskId: string,
    commandId: string,
    result: unknown,
    seedPatch?: Record<string, unknown>,
    candidateSelectionReady?: boolean,
  ) => Promise<void>;
  resolveCommandOutcome: (taskId: string) => Promise<DirectorCommandExecutionOutcome>;
  /** Resolve the novel's writing mode, or null if unknown / not found. */
  getNovelWritingMode: (novelId: string) => Promise<NovelWritingMode | null>;
  /** Bind the produced analysis id to the novel's matching analysis column. */
  bindAnalysisToNovel: (
    novelId: string,
    analysisId: string,
    mode: NovelWritingMode,
  ) => Promise<void>;
}

/**
 * Execute the `analyze_reference_book` command:
 *  - ingest (or reuse) the reference text as a knowledge document,
 *  - run a book analysis to completion,
 *  - when a `novelId` is present, bind the produced `analysisId` to the novel's
 *    matching analysis column and write that column into the task seed payload,
 *  - record the produced `analysisId` + `documentId` on the task,
 *  - resolve the command outcome.
 */
export async function dispatchAnalyzeReferenceBook(
  taskId: string,
  commandId: string,
  request: AnalyzeReferenceBookDispatchRequest,
  deps: AnalyzeReferenceBookDispatchDeps,
): Promise<DirectorCommandExecutionOutcome> {
  const result = await deps.bookAnalysisOrchestration.ingestAndAnalyze(
    request.title ?? "参考资料",
    request.referenceText,
    {
      existingDocumentId: request.documentId ?? undefined,
      provider: request.provider as LLMProvider | undefined,
      model: request.model ?? undefined,
      temperature: request.temperature ?? undefined,
    },
  );

  let seedPatch: Record<string, unknown> = {};
  if (request.novelId) {
    const mode = await deps.getNovelWritingMode(request.novelId);
    if (mode) {
      const analysisColumn = mode === "continuation" ? "continuationBookAnalysisId" : "referenceBookAnalysisId";
      seedPatch = { [analysisColumn]: result.analysisId };
      await deps.bindAnalysisToNovel(request.novelId, result.analysisId, mode);
    }
  }

  await deps.recordCommandResult(
    taskId,
    commandId,
    { analysisId: result.analysisId, documentId: result.documentId },
    seedPatch,
  );

  return deps.resolveCommandOutcome(taskId);
}
