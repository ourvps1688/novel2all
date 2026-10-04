const test = require("node:test");
const assert = require("node:assert/strict");

// Pre-load the director pipeline runtime module (the same module the integration
// suite loads first) so the director/runtime module graph is fully initialized
// before `DirectorCommandExecutor` is required. The repo has a pre-existing
// circular dependency between these modules whose correctness is load-order
// sensitive; loading via this entry point makes the graph resolve cleanly in an
// isolated test process (test-only scaffolding, not a change to application code).
require("../dist/services/novel/director/novelDirectorPipelineRuntime.js");

const { DirectorCommandService } = require("../dist/services/novel/director/commands/DirectorCommandService.js");
const { DirectorCommandExecutor } = require("../dist/services/novel/director/commands/DirectorCommandExecutor.js");
const { DirectorCommandInterpreter } = require("../dist/services/novel/director/commands/DirectorCommandInterpreter.js");
const { chapterReverseDecomposition } = require("../dist/services/novel/director/runtime/chapterReverseDecomposition.js");
const { prisma } = require("../dist/db/prisma.js");

/**
 * Tests for the `decompose_written_chapter` director command wiring (Phase 4 T4.2).
 *
 * Covers:
 *  - enqueue builds the right command type + payload and behaves as a utility
 *    command (no checkpoint, no approval gating, no follow-up continue command)
 *  - input trimming and default values
 *  - the interpreter recognizes the new command
 *  - the executor dispatches to the service and records
 *    { decomposedChapters, skippedChapters }
 */

function createEnqueueHarness() {
  const commands = [];
  const task = {
    id: "task-1",
    novelId: "novel-1",
    lane: "auto_director",
    status: "waiting_approval",
    pendingManualRecovery: false,
    updatedAt: new Date("2026-04-29T12:00:00.000Z"),
    seedPayloadJson: JSON.stringify({
      runMode: "auto_to_execution",
      issueGovernanceVersion: 1,
      issuePolicy: { maxAutomaticRetries: 1, issueActions: {} },
      issuePolicySource: "global",
    }),
  };
  const workflowService = {
    async getTaskById(taskId) {
      return taskId === task.id ? task : null;
    },
  };
  const original = {
    findFirst: prisma.directorRunCommand.findFirst,
    findMany: prisma.directorRunCommand.findMany,
    create: prisma.directorRunCommand.create,
    updateMany: prisma.directorRunCommand.updateMany,
    taskUpdateMany: prisma.novelWorkflowTask.updateMany,
  };
  prisma.directorRunCommand.findFirst = async () => null;
  prisma.directorRunCommand.findMany = async () => [];
  prisma.directorRunCommand.create = async ({ data }) => {
    const row = {
      id: `command-${commands.length + 1}`,
      novelId: data.novelId ?? null,
      leaseOwner: null,
      leaseExpiresAt: null,
      attempt: 0,
      runAfter: new Date(),
      errorMessage: null,
      startedAt: null,
      finishedAt: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      ...data,
    };
    commands.push(row);
    return row;
  };
  prisma.directorRunCommand.updateMany = async () => ({ count: 0 });
  prisma.novelWorkflowTask.updateMany = async (args) => {
    Object.assign(task, args?.data ?? {});
    return { count: 1 };
  };

  const service = new DirectorCommandService(workflowService);
  service.recoverStaleLeases = async () => 0;

  return {
    commands,
    task,
    service,
    restore() {
      prisma.directorRunCommand.findFirst = original.findFirst;
      prisma.directorRunCommand.findMany = original.findMany;
      prisma.directorRunCommand.create = original.create;
      prisma.directorRunCommand.updateMany = original.updateMany;
      prisma.novelWorkflowTask.updateMany = original.taskUpdateMany;
    },
  };
}

test("enqueueDecomposeWrittenChapterCommand queues the utility command with a normalized payload", async () => {
  const harness = createEnqueueHarness();
  try {
    const accepted = await harness.service.enqueueDecomposeWrittenChapterCommand("task-1", {
      novelId: " novel-1 ",
      chapterId: " c-1 ",
      allChapters: true,
      force: true,
      provider: "p",
      model: "m",
      temperature: 0.4,
    });

    assert.equal(accepted.status, "queued");
    assert.equal(accepted.commandType, "decompose_written_chapter");
    assert.equal(harness.commands.length, 1);

    const req = JSON.parse(harness.commands[0].payloadJson).decomposeWrittenChapterRequest;
    assert.ok(req, "payload carries the decomposeWrittenChapterRequest");
    assert.equal(req.novelId, "novel-1");
    assert.equal(req.chapterId, "c-1");
    assert.equal(req.allChapters, true);
    assert.equal(req.force, true);
    assert.equal(req.provider, "p");
    assert.equal(req.model, "m");
    assert.equal(req.temperature, 0.4);

    // Utility command: no follow-up continue command, no approval gating.
    assert.equal(harness.commands.filter((command) => command.commandType === "continue").length, 0);
    assert.equal(harness.task.pendingManualRecovery, false);
  } finally {
    harness.restore();
  }
});

test("enqueueDecomposeWrittenChapterCommand applies safe defaults and nulls", async () => {
  const harness = createEnqueueHarness();
  try {
    await harness.service.enqueueDecomposeWrittenChapterCommand("task-1", { novelId: "n1" });
    const req = JSON.parse(harness.commands[0].payloadJson).decomposeWrittenChapterRequest;

    assert.equal(req.allChapters, false);
    assert.equal(req.force, false);
    assert.equal(req.chapterId, null);
    assert.equal(req.provider, undefined);
    assert.equal(req.model, undefined);
    assert.equal(req.temperature, undefined);
  } finally {
    harness.restore();
  }
});

test("the interpreter recognizes decompose_written_chapter as a supported command", () => {
  const interpreter = new DirectorCommandInterpreter();
  const pipeline = interpreter.interpret(
    {
      id: "cmd-1",
      taskId: "task-1",
      novelId: "novel-1",
      commandType: "decompose_written_chapter",
      payloadJson: "{}",
    },
    { decomposeWrittenChapterRequest: { novelId: "novel-1", chapterId: "c-1" } },
  );

  assert.equal(pipeline.intent, "decompose_written_chapter");
  assert.equal(pipeline.isControlOnly, false);
});

test("executor dispatch for a single chapter records decomposed/skipped chapters", async () => {
  const recorded = [];
  const originalDecompose = chapterReverseDecomposition.decompose;
  chapterReverseDecomposition.decompose = async (novelId, chapterId) => {
    assert.equal(novelId, "novel-1");
    assert.equal(chapterId, "c-1");
    return { chapterId: "c-1", taskSheet: "t", sceneCards: "s", skipped: false };
  };

  const executor = new DirectorCommandExecutor({
    commandService: {},
    workflowService: {},
    stateStore: {
      readTaskState: async () => ({ task: { novelId: "novel-1" }, runtime: null }),
      recordPipelineDispatch: async () => {},
    },
    interpreter: {
      interpret: (command, payload) => ({
        id: command.id,
        taskId: command.taskId,
        novelId: command.novelId,
        intent: "decompose_written_chapter",
        payload,
        takeoverRequest: null,
        forceResume: false,
        isControlOnly: false,
      }),
    },
  });
  executor.recordCommandResult = async (taskId, id, result) => {
    recorded.push({ taskId, id, result });
  };
  executor.resolveCommandOutcome = async () => "completed";

  try {
    const outcome = await executor.dispatch(
      { id: "cmd-1", taskId: "task-1", novelId: "novel-1", commandType: "decompose_written_chapter" },
      { decomposeWrittenChapterRequest: { novelId: "novel-1", chapterId: "c-1" } },
    );
    assert.equal(outcome, "completed");
    assert.equal(recorded.length, 1);
    assert.deepEqual(recorded[0].result, { decomposedChapters: ["c-1"], skippedChapters: [] });
  } finally {
    chapterReverseDecomposition.decompose = originalDecompose;
  }
});

test("executor dispatch for a single skipped chapter reports it under skippedChapters", async () => {
  const recorded = [];
  const originalDecompose = chapterReverseDecomposition.decompose;
  chapterReverseDecomposition.decompose = async () => ({ chapterId: "c-1", taskSheet: "t", sceneCards: "s", skipped: true });

  const executor = new DirectorCommandExecutor({
    commandService: {},
    workflowService: {},
    stateStore: {
      readTaskState: async () => ({ task: { novelId: "novel-1" }, runtime: null }),
      recordPipelineDispatch: async () => {},
    },
    interpreter: {
      interpret: (command, payload) => ({
        id: command.id,
        taskId: command.taskId,
        novelId: command.novelId,
        intent: "decompose_written_chapter",
        payload,
        takeoverRequest: null,
        forceResume: false,
        isControlOnly: false,
      }),
    },
  });
  executor.recordCommandResult = async (taskId, id, result) => {
    recorded.push({ taskId, id, result });
  };
  executor.resolveCommandOutcome = async () => "completed";

  try {
    await executor.dispatch(
      { id: "cmd-1", taskId: "task-1", novelId: "novel-1", commandType: "decompose_written_chapter" },
      { decomposeWrittenChapterRequest: { novelId: "novel-1", chapterId: "c-1" } },
    );
    assert.deepEqual(recorded[0].result, { decomposedChapters: [], skippedChapters: ["c-1"] });
  } finally {
    chapterReverseDecomposition.decompose = originalDecompose;
  }
});

test("executor dispatch without a chapterId decomposes the whole novel", async () => {
  const recorded = [];
  const originalNovel = chapterReverseDecomposition.decomposeNovel;
  chapterReverseDecomposition.decomposeNovel = async (novelId) => {
    assert.equal(novelId, "novel-1");
    return { decomposed: ["c-1", "c-2"], skipped: ["c-3"] };
  };

  const executor = new DirectorCommandExecutor({
    commandService: {},
    workflowService: {},
    stateStore: {
      readTaskState: async () => ({ task: { novelId: "novel-1" }, runtime: null }),
      recordPipelineDispatch: async () => {},
    },
    interpreter: {
      interpret: (command, payload) => ({
        id: command.id,
        taskId: command.taskId,
        novelId: command.novelId,
        intent: "decompose_written_chapter",
        payload,
        takeoverRequest: null,
        forceResume: false,
        isControlOnly: false,
      }),
    },
  });
  executor.recordCommandResult = async (taskId, id, result) => {
    recorded.push({ taskId, id, result });
  };
  executor.resolveCommandOutcome = async () => "completed";

  try {
    await executor.dispatch(
      { id: "cmd-1", taskId: "task-1", novelId: "novel-1", commandType: "decompose_written_chapter" },
      { decomposeWrittenChapterRequest: { novelId: "novel-1" } },
    );
    assert.deepEqual(recorded[0].result, { decomposedChapters: ["c-1", "c-2"], skippedChapters: ["c-3"] });
  } finally {
    chapterReverseDecomposition.decomposeNovel = originalNovel;
  }
});
