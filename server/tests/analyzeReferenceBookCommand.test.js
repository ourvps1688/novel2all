// Phase 4 (4c / T4.5) — analyze_reference_book director command tests.
//
// Verifies the command is registered (part of DirectorRunCommandType and the
// command interpreter) and that the dispatch path:
//   - calls the headless orchestration with the reference text,
//   - records { analysisId, documentId } on the task,
//   - when a `novelId` is supplied and the novel has a known writing mode,
//     binds the produced `analysisId` to the matching `Novel` analysis column
//     (referenceBookAnalysisId for `original`, continuationBookAnalysisId for
//     `continuation`) and writes that column into the task seed payload,
//   - does NOT create a checkpoint / enqueue a continue / require approval
//     (it records the result with at most a non-gating seedPatch).
//
// IMPORTANT: this test deliberately does NOT require `DirectorCommandExecutor`.
// That class cannot be loaded in a standalone test process because its
// dependency graph contains a pre-existing circular import that crashes at
// module load (`NovelVolumeService is not a constructor`). Requiring it would
// force a `require.cache` stub of `ChapterRuntimeCoordinator`, and that stub
// previously broke the shared `sharedChapterRuntimeCoordinator` export — silently
// poisoning every later test in the shared process (the #58 CI red regression).
// The actual dispatch logic lives in `analyzeReferenceBookDispatch`, which uses
// only type-only imports and is safe to require directly.
//
// No Prisma / LLM calls are made: collaborators are injected.
const assert = require("node:assert/strict");
const test = require("node:test");

const { DIRECTOR_RUN_COMMAND_TYPES } = require("../../shared/dist/types/directorRuntime.js");
const { DirectorCommandInterpreter } = require("../dist/services/novel/director/commands/DirectorCommandInterpreter.js");
const { dispatchAnalyzeReferenceBook } = require("../dist/services/novel/director/commands/analyzeReferenceBookDispatch.js");

test("analyze_reference_book is registered as a DirectorRunCommandType", () => {
  assert.ok(
    DIRECTOR_RUN_COMMAND_TYPES.includes("analyze_reference_book"),
    "DIRECTOR_RUN_COMMAND_TYPES should include analyze_reference_book",
  );
});

test("command interpreter recognizes analyze_reference_book and treats it as a non-control work command", () => {
  const interpreter = new DirectorCommandInterpreter();
  const pipelineCommand = interpreter.interpret(
    { id: "cmd-1", taskId: "task-1", commandType: "analyze_reference_book", novelId: "novel-1" },
    { analyzeReferenceBookRequest: { referenceText: "x" } },
  );
  assert.equal(pipelineCommand.intent, "analyze_reference_book");
  // Not a control-only command (unlike pause_autopilot) => it does real work.
  assert.equal(pipelineCommand.isControlOnly, false);
  // Does not force a resume / continue.
  assert.equal(pipelineCommand.forceResume, false);
});

test("dispatch calls the orchestration with the reference text and records analysis/document ids", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  const outcome = await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    { title: "我的参考书", referenceText: "第一章 内容……" },
    buildDeps(orchestrationMock, captured),
  );

  // The orchestration ran once with the supplied title + reference text.
  assert.equal(orchestrationMock.calls.length, 1);
  assert.equal(orchestrationMock.calls[0].title, "我的参考书");
  assert.equal(orchestrationMock.calls[0].content, "第一章 内容……");

  // The recorded result carries the analysis + document ids.
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 4, "recordCommandResult is called with a seedPatch (4th arg)");
  assert.equal(captured[0].taskId, "task-1");
  assert.equal(captured[0].commandId, "cmd-1");
  assert.deepEqual(captured[0].result, { analysisId: "analysis-1", documentId: "doc-1" });

  // Outcome comes from resolveCommandOutcome.
  assert.equal(outcome, "completed");
});

test("dispatch passes provider / model / existing document id through to the orchestration", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    {
      referenceText: "内容",
      documentId: "existing-doc",
      provider: "openai",
      model: "gpt-4o",
      temperature: 0.3,
    },
    buildDeps(orchestrationMock, captured),
  );

  assert.equal(orchestrationMock.calls.length, 1);
  assert.equal(orchestrationMock.calls[0].title, "参考资料", "title falls back when omitted");
  assert.equal(orchestrationMock.calls[0].content, "内容");
  assert.deepEqual(orchestrationMock.calls[0].options, {
    existingDocumentId: "existing-doc",
    provider: "openai",
    model: "gpt-4o",
    temperature: 0.3,
  });
});

test("analyze_reference_book is a utility command — no checkpoint, no approval gate", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    { referenceText: "内容" },
    buildDeps(orchestrationMock, captured),
  );

  // 4-arg recordCommandResult call => seedPatch (4th) arrives as an empty object
  // and candidateSelectionReady (5th) arrives as undefined => default to {} /
  // false => no checkpoint / no approval gate is created.
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 4);
  assert.deepEqual(captured[0].seedPatch, {});
  assert.equal(captured[0].candidateSelectionReady, false);
});

test("dispatch binds the analysis to referenceBookAnalysisId for an original novel", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  const bindCalls = [];
  await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    { referenceText: "内容", novelId: "novel-original" },
    buildDeps(orchestrationMock, captured, { bindCalls, writingMode: "original" }),
  );

  assert.equal(bindCalls.length, 1);
  assert.deepEqual(bindCalls[0], { novelId: "novel-original", analysisId: "analysis-1", mode: "original" });
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 4);
  assert.deepEqual(captured[0].seedPatch, { referenceBookAnalysisId: "analysis-1" });
});

test("dispatch binds the analysis to continuationBookAnalysisId for a continuation novel", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  const bindCalls = [];
  await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    { referenceText: "内容", novelId: "novel-continuation" },
    buildDeps(orchestrationMock, captured, { bindCalls, writingMode: "continuation" }),
  );

  assert.equal(bindCalls.length, 1);
  assert.deepEqual(bindCalls[0], { novelId: "novel-continuation", analysisId: "analysis-1", mode: "continuation" });
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 4);
  assert.deepEqual(captured[0].seedPatch, { continuationBookAnalysisId: "analysis-1" });
});

test("dispatch does not bind any analysis when novelId is absent", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  const bindCalls = [];
  await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    { referenceText: "内容" },
    buildDeps(orchestrationMock, captured, { bindCalls }),
  );

  assert.equal(bindCalls.length, 0, "no bind should happen without a novelId");
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 4);
  assert.deepEqual(captured[0].seedPatch, {});
});

test("dispatch does not bind when the novel writing mode is unknown", async () => {
  const orchestrationMock = makeOrchestrationMock();
  const captured = [];
  const bindCalls = [];
  await dispatchAnalyzeReferenceBook(
    "task-1",
    "cmd-1",
    { referenceText: "内容", novelId: "novel-unknown-mode" },
    buildDeps(orchestrationMock, captured, { bindCalls, writingMode: null }),
  );

  assert.equal(bindCalls.length, 0, "no bind should happen for an unknown writing mode");
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 4);
  assert.deepEqual(captured[0].seedPatch, {});
});

function makeOrchestrationMock() {
  const calls = [];
  const ingestAndAnalyze = async (title, content, options) => {
    calls.push({ title, content, options });
    return {
      documentId: "doc-1",
      versionId: "ver-1",
      analysisId: "analysis-1",
      analysis: { id: "analysis-1", status: "succeeded" },
    };
  };
  return { ingestAndAnalyze, calls };
}

function buildDeps(orchestrationMock, captured, options = {}) {
  const bindCalls = options.bindCalls ?? [];
  const writingMode = options.writingMode === undefined ? "original" : options.writingMode;
  return {
    bookAnalysisOrchestration: { ingestAndAnalyze: orchestrationMock.ingestAnalyze ?? orchestrationMock.ingestAndAnalyze },
    // Regular function (not arrow) so we can read `arguments.length` and prove
    // the dispatch passed a seedPatch (4th arg). When no novelId is supplied the
    // seedPatch arrives as an empty object, which still keeps the utility-command
    // contract ({}, false => no checkpoint / no approval gate).
    recordCommandResult: function (taskId, commandId, result, seedPatch, candidateSelectionReady) {
      captured.push({
        taskId,
        commandId,
        result,
        callArity: arguments.length,
        // Mirror the real recordCommandResult defaults so we can assert the
        // no-checkpoint / no-approval-gate contract ({}, false).
        seedPatch: seedPatch ?? {},
        candidateSelectionReady: candidateSelectionReady ?? false,
      });
    },
    getNovelWritingMode: async () => writingMode,
    bindAnalysisToNovel: async (novelId, analysisId, mode) => {
      bindCalls.push({ novelId, analysisId, mode });
    },
    resolveCommandOutcome: async () => "completed",
  };
}
