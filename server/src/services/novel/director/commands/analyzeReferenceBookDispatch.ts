/**
 * Standalone, dependency-light dispatch for the `analyze_reference_book`
 * director command (Phase 4 — foundation, task 4c).
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
 * No Prisma / LLM calls happen here: the orchestration and the result recorder
 * are injected.
 */

import type { LLMProvider } from "@ai-novel/shared/types/llm";
import type { BookAnalysisOrchestration } from "../runtime/bookAnalysisOrchestration";
import type { DirectorCommandExecutionOutcome } from "./DirectorCommandExecutor";

/** Parsed payload of the `analyze_reference_book` command. */
export interface AnalyzeReferenceBookDispatchRequest {
  title?: string | null;
  referenceText: string;
  documentId?: string | null;
  provider?: string | null;
  model?: string | null;
  temperature?: number | null;
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
}

/**
 * Execute the `analyze_reference_book` command:
 *  - ingest (or reuse) the reference text as a knowledge document,
 *  - run a book analysis to completion,
 *  - record the produced `analysisId` + `documentId` on the task,
 *  - resolve the command outcome.
 *
 * This is a *utility* command: it records its result with only three arguments
 * (no `seedPatch`, no `candidateSelectionReady`), so it does NOT create a
 * checkpoint, enqueue a continue, or require an approval gate.
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

  await deps.recordCommandResult(taskId, commandId, {
    analysisId: result.analysisId,
    documentId: result.documentId,
  });

  return deps.resolveCommandOutcome(taskId);
}
