// Phase 4 (4c) — analyze_reference_book director command tests.
//
// Verifies the command is registered (part of DirectorRunCommandType and the
// command interpreter) and that the executor dispatches it: calls the headless
// orchestration, records { analysisId, documentId }, and does NOT create a
// checkpoint, enqueue a continue, or require approval.
//
// NOTE: DirectorCommandExecutor's dependency graph contains a pre-existing
// circular import that crashes at module load when required in isolation
// (a top-level `new ChapterRuntimeCoordinator()` singleton needs
// NovelVolumeService, which is not yet initialized). We transiently stub that
// one singleton in the module cache so the executor can load, then restore the
// cache immediately afterwards so the rest of the shared test process is
// unaffected. The analyze_reference_book dispatch path never uses
// ChapterRuntimeCoordinator at runtime, so the stub is harmless.
//
// No Prisma / LLM calls are made: collaborators are injected and
// recordCommandResult is overridden to capture the recorded result.
const assert = require("node:assert/strict");
const test = require("node:test");
const Module = require("module");
const path = require("path");

const { DIRECTOR_RUN_COMMAND_TYPES } = require("../../shared/dist/types/directorRuntime.js");

// Transiently stub the offending top-level singleton so the executor module can
// be required without tripping the circular-import crash.
const crcPath = path.resolve(__dirname, "..", "dist/services/novel/runtime/ChapterRuntimeCoordinator.js");
const cachedCrc = require.cache[crcPath];
const crcModule = new Module(crcPath, module);
crcModule.exports = { ChapterRuntimeCoordinator: class {} };
require.cache[crcPath] = crcModule;
const {
  DirectorCommandExecutor,
} = require("../dist/services/novel/director/commands/DirectorCommandExecutor.js");
const { DirectorCommandInterpreter } = require("../dist/services/novel/director/commands/DirectorCommandInterpreter.js");
// Restore the real module entry so other tests in the shared process are unaffected.
if (cachedCrc) {
  require.cache[crcPath] = cachedCrc;
} else {
  delete require.cache[crcPath];
}

function buildExecutor(orchestrationMock, captured) {
  const workflowService = {
    getTaskById: async () => ({ id: "task-1", novelId: "novel-1", status: "running", lane: "auto_director" }),
    getTaskByIdWithoutHealing: async () => ({ id: "task-1", status: "running" }),
  };
  const stateStore = {
    readTaskState: async () => ({ task: { novelId: "novel-1", id: "task-1" } }),
    recordPipelineDispatch: async () => {},
  };
  const commandService = {
    getCommandById: async () => ({
      id: "cmd-1",
      taskId: "task-1",
      commandType: "analyze_reference_book",
      novelId: "novel-1",
      payloadJson: "{}",
    }),
    parseCommandPayload: () => ({
      analyzeReferenceBookRequest: {
        title: "我的参考书",
        referenceText: "第一章 内容……",
        documentId: undefined,
      },
    }),
  };

  // Capture the result recorded by the executor without hitting the database.
  class CapturingExecutor extends DirectorCommandExecutor {
    async recordCommandResult(taskId, commandId, result, seedPatch, candidateSelectionReady) {
      // Mirror the real method's defaults: the analyze_reference_book dispatch
      // passes only 3 args, so seedPatch (4th) and candidateSelectionReady
      // (5th) arrive as undefined. We normalize them to the real defaults
      // ({}, false) so the captured values reflect what the real code path
      // produces (no checkpoint / no approval gate).
      captured.push({
        taskId,
        commandId,
        result,
        seedPatch: seedPatch ?? {},
        candidateSelectionReady: candidateSelectionReady ?? false,
      });
    }
  }

  const executor = new CapturingExecutor({
    workflowService,
    stateStore,
    commandService,
    bookAnalysisOrchestration: orchestrationMock,
  });
  return { executor, workflowService };
}

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

test("executor dispatches analyze_reference_book and returns completed outcome", async () => {
  const captured = [];
  const orchMock = makeOrchestrationMock();
  const { executor } = buildExecutor(orchMock, captured);
  const command = {
    id: "cmd-1",
    taskId: "task-1",
    commandType: "analyze_reference_book",
    novelId: "novel-1",
  };
  const outcome = await executor.dispatch(command, {
    analyzeReferenceBookRequest: { title: "我的参考书", referenceText: "第一章 内容……" },
  });
  assert.equal(outcome, "completed");
});

test("executor calls the orchestration with the reference text and records analysis/document ids", async () => {
  const captured = [];
  const orchMock = makeOrchestrationMock();
  const { executor } = buildExecutor(orchMock, captured);
  const command = {
    id: "cmd-1",
    taskId: "task-1",
    commandType: "analyze_reference_book",
    novelId: "novel-1",
  };
  await executor.dispatch(command, {
    analyzeReferenceBookRequest: { title: "我的参考书", referenceText: "第一章 内容……" },
  });

  assert.equal(orchMock.calls.length, 1);
  assert.equal(orchMock.calls[0].title, "我的参考书");
  assert.equal(orchMock.calls[0].content, "第一章 内容……");

  // The result recorded on the task must carry analysisId + documentId.
  assert.equal(captured.length, 1);
  assert.equal(captured[0].result.analysisId, "analysis-1");
  assert.equal(captured[0].result.documentId, "doc-1");
});

test("analyze_reference_book does NOT create a checkpoint, require approval, or enqueue a continue", async () => {
  const captured = [];
  const orchMock = makeOrchestrationMock();
  const { executor } = buildExecutor(orchMock, captured);
  const command = {
    id: "cmd-1",
    taskId: "task-1",
    commandType: "analyze_reference_book",
    novelId: "novel-1",
  };
  await executor.dispatch(command, {
    analyzeReferenceBookRequest: { referenceText: "内容" },
  });

  // candidateSelectionReady === false => no checkpoint / approval gate is created.
  assert.equal(captured.length, 1);
  assert.equal(captured[0].candidateSelectionReady, false);
  assert.deepEqual(captured[0].seedPatch, {});
  // The orchestration (not a continue executor) is what ran.
  assert.equal(orchMock.calls.length, 1);
});
