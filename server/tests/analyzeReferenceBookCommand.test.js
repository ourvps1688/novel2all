// Phase 4 (4c) — analyze_reference_book director command tests.
//
// Verifies the command is registered (part of DirectorRunCommandType and the
// command interpreter) and that the dispatch path:
//   - calls the headless orchestration with the reference text,
//   - records { analysisId, documentId } on the task,
//   - does NOT create a checkpoint / enqueue a continue / require approval
//     (it records the result with only 3 args).
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
  assert.equal(captured[0].callArity, 3, "recordCommandResult should be called with only 3 args (no seedPatch / candidateSelectionReady)");
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

  // 3-arg recordCommandResult call => seedPatch (4th) and candidateSelectionReady
  // (5th) arrive as undefined => default to {} / false => no checkpoint /
  // no approval gate is created.
  assert.equal(captured.length, 1);
  assert.equal(captured[0].callArity, 3);
  assert.deepEqual(captured[0].seedPatch, {});
  assert.equal(captured[0].candidateSelectionReady, false);
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

function buildDeps(orchestrationMock, captured) {
  return {
    bookAnalysisOrchestration: { ingestAndAnalyze: orchestrationMock.ingestAndAnalyze },
    // Regular function (not arrow) so we can read `arguments.length` and prove
    // the dispatch passed exactly 3 args — the utility-command contract.
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
    resolveCommandOutcome: async () => "completed",
  };
}
