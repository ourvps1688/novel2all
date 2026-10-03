const test = require("node:test");
const assert = require("node:assert/strict");
const { prisma } = require("../dist/db/prisma.js");
const {
  DirectorProductionExperienceService,
} = require("../dist/services/novel/director/commands/DirectorProductionExperienceService.js");

function installPrismaMocks(handlers) {
  const originals = {
    findUnique: prisma.novelWorkflowTask.findUnique,
    transaction: prisma.$transaction,
  };
  prisma.novelWorkflowTask.findUnique = handlers.findUnique;
  prisma.$transaction = handlers.transaction;
  return originals;
}

function restorePrismaMocks(originals) {
  prisma.novelWorkflowTask.findUnique = originals.findUnique;
  prisma.$transaction = originals.transaction;
}

function buildHarness(seed) {
  const defaultSeed = {
    directorInput: {
      candidate: { workingTitle: "Autopilot Demo" },
      runMode: "full_book_autopilot",
    },
    runMode: "full_book_autopilot",
  };
  const finalSeed = seed ?? defaultSeed;
  let taskState = {
    id: "task-pe",
    lane: "auto_director",
    novelId: "novel-pe",
    status: "waiting_approval",
    checkpointType: "production_experience_required",
    seedPayloadJson: JSON.stringify(finalSeed),
  };
  let novelState = { id: "novel-pe", creationExperience: null };
  let checkpointUpdate = null;
  const recorded = [];

  const commandService = {
    enqueueContinueCommand: async (taskId, input) => {
      recorded.push({ taskId, input });
      return { commandId: "cmd-1" };
    },
  };

  const handlers = {
    findUnique: async ({ where }) => (where && where.id === taskState.id ? { ...taskState } : null),
    transaction: async (fn) =>
      fn({
        novelWorkflowTask: {
          updateMany: async (input) => {
            checkpointUpdate = input;
            if (input.where && input.where.id === taskState.id) {
              taskState = { ...taskState, ...input.data };
            }
            return { count: 1 };
          },
        },
        novel: {
          update: async (input) => {
            if (input.where && input.where.id === novelState.id) {
              novelState = { ...novelState, ...input.data };
            }
            return { ...novelState };
          },
        },
      }),
  };

  return {
    get taskState() {
      return taskState;
    },
    get novelState() {
      return novelState;
    },
    get checkpointUpdate() {
      return checkpointUpdate;
    },
    get recorded() {
      return recorded;
    },
    commandService,
    handlers,
  };
}

test("autoPassForAutopilot transitions production_experience_required and enqueues a continue command", async () => {
  const harness = buildHarness();
  const originals = installPrismaMocks(harness.handlers);
  try {
    const service = new DirectorProductionExperienceService(harness.commandService);
    const response = await service.autoPassForAutopilot(harness.taskState.id);

    assert.equal(harness.taskState.checkpointType, "chapter_batch_ready");
    assert.equal(harness.novelState.creationExperience, "simple");
    assert.equal(harness.recorded.length, 1);
    assert.deepEqual(harness.recorded[0].input, {
      continuationMode: "auto_execute_range",
      forceResume: true,
    });
    assert.equal(response.experience, "simple");
    assert.equal(response.backgroundStarted, true);
    assert.ok(harness.checkpointUpdate && harness.checkpointUpdate.data.seedPayloadJson);
    assert.match(
      JSON.parse(harness.checkpointUpdate.data.seedPayloadJson).runMode,
      /full_book_autopilot/,
    );
  } finally {
    restorePrismaMocks(originals);
  }
});

test("autoPassForAutopilot is idempotent (second call does not re-enqueue)", async () => {
  const harness = buildHarness();
  const originals = installPrismaMocks(harness.handlers);
  try {
    const service = new DirectorProductionExperienceService(harness.commandService);
    await service.autoPassForAutopilot(harness.taskState.id);
    assert.equal(harness.recorded.length, 1);

    // After the first pass the task is no longer in production_experience_required,
    // so the second call must be a no-op (no additional continue command).
    const response = await service.autoPassForAutopilot(harness.taskState.id);
    assert.equal(harness.recorded.length, 1, "second call must not enqueue another command");
    assert.equal(response.backgroundStarted, false);
  } finally {
    restorePrismaMocks(originals);
  }
});

test("autoPassForAutopilot on a non-gate task is a safe no-op (no enqueue)", async () => {
  const harness = buildHarness();
  // Pre-seed the task already out of the hard gate state.
  harness.taskState.checkpointType = "chapter_batch_ready";
  const originals = installPrismaMocks(harness.handlers);
  try {
    const service = new DirectorProductionExperienceService(harness.commandService);
    const response = await service.autoPassForAutopilot(harness.taskState.id);
    assert.equal(harness.recorded.length, 0);
    assert.equal(response.backgroundStarted, false);
    assert.equal(response.experience, "simple");
  } finally {
    restorePrismaMocks(originals);
  }
});
