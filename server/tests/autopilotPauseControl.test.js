// T3.3 global pause control — verification.
// Zero-migration: a paused autopilot run is encoded as a `waiting_approval` task that also
// carries `pendingManualRecovery === true`. The autopilot loop treats that combination as a
// STOP, and the checkpoint watchdog must never auto-resolve it.
const assert = require("node:assert/strict");
const test = require("node:test");

const {
  shouldStopAutoExecution,
} = require("../dist/services/novel/director/automation/novelDirectorAutoExecutionRuntimePreparation.js");
const {
  AutopilotCheckpointWatchdog,
} = require("../dist/services/novel/director/runtime/autopilotCheckpointWatchdog.js");
const {
  resolveAutopilotWaitingCheckpoint,
  isAutopilotCheckpointPaused,
} = require("../dist/services/novel/director/runtime/autopilotCheckpointResolver.js");

function buildStopDeps(row, cancelSpy) {
  return {
    workflowService: { getTaskById: async () => row },
    novelService: { cancelPipelineJob: cancelSpy ?? (async () => {}) },
  };
}

test("paused autopilot task (waiting_approval + pendingManualRecovery) stops the loop", async () => {
  const deps = buildStopDeps({ status: "waiting_approval", pendingManualRecovery: true });
  assert.equal(await shouldStopAutoExecution(deps, "task-paused", null), true);
});

test("cancelled task still stops (regression) and cancels the pipeline job", async () => {
  let cancelled = false;
  const deps = {
    workflowService: { getTaskById: async () => ({ status: "cancelled", pendingManualRecovery: false }) },
    novelService: { cancelPipelineJob: async () => { cancelled = true; } },
  };
  assert.equal(await shouldStopAutoExecution(deps, "task-cancelled", "job-1"), true);
  assert.equal(cancelled, true);
});

test("running / queued task does not stop", async () => {
  for (const status of ["running", "queued", "succeeded", "failed"]) {
    const deps = buildStopDeps({ status, pendingManualRecovery: false });
    assert.equal(await shouldStopAutoExecution(deps, "task-x", null), false, `status=${status}`);
  }
});

test("waiting_approval WITHOUT pendingManualRecovery does not stop (normal checkpoint)", async () => {
  const deps = buildStopDeps({ status: "waiting_approval", pendingManualRecovery: false });
  assert.equal(await shouldStopAutoExecution(deps, "task-wa", null), false);
});

test("isAutopilotCheckpointPaused predicate identifies paused tasks", () => {
  assert.equal(isAutopilotCheckpointPaused({ status: "waiting_approval", pendingManualRecovery: true }), true);
  assert.equal(isAutopilotCheckpointPaused({ status: "waiting_approval", pendingManualRecovery: false }), false);
  assert.equal(isAutopilotCheckpointPaused({ status: "running", pendingManualRecovery: true }), false);
  assert.equal(isAutopilotCheckpointPaused({ status: "cancelled", pendingManualRecovery: true }), false);
  assert.equal(isAutopilotCheckpointPaused({ status: "waiting_approval" }), false);
});

test("watchdog scanOnce never auto-resolves a paused (pendingManualRecovery) task", async () => {
  const rows = [
    {
      id: "t-paused",
      lane: "auto_director",
      status: "waiting_approval",
      pendingManualRecovery: true,
      seedPayloadJson: JSON.stringify({ runMode: "full_book_autopilot" }),
    },
    {
      id: "t-normal",
      lane: "auto_director",
      status: "waiting_approval",
      pendingManualRecovery: false,
      seedPayloadJson: JSON.stringify({ runMode: "full_book_autopilot" }),
    },
    {
      id: "t-other-mode",
      lane: "auto_director",
      status: "waiting_approval",
      pendingManualRecovery: false,
      seedPayloadJson: JSON.stringify({ runMode: "auto_to_execution" }),
    },
  ];
  const mockPrisma = {
    novelWorkflowTask: {
      findMany: async ({ where }) =>
        rows.filter(
          (r) =>
            r.lane === where.lane &&
            r.status === where.status &&
            r.pendingManualRecovery === where.pendingManualRecovery,
        ),
    },
  };
  const resolved = [];
  const watchdog = new AutopilotCheckpointWatchdog({
    prisma: mockPrisma,
    resolve: async (taskId) => {
      resolved.push(taskId);
    },
  });

  const result = await watchdog.scanOnce();

  assert.deepEqual(result.sort(), ["t-normal"]);
  assert.deepEqual(resolved.sort(), ["t-normal"]);
  assert.ok(!resolved.includes("t-paused"), "paused task must NOT be auto-resolved by the watchdog");
});

test("resolveAutopilotWaitingCheckpoint skips a paused (pendingManualRecovery) task", async () => {
  const calls = { continue: 0, autoPass: 0 };
  const deps = {
    workflowService: {
      getTaskById: async () => ({
        status: "waiting_approval",
        pendingManualRecovery: true,
        checkpointType: "chapter_batch_ready",
      }),
    },
    commandService: { enqueueContinueCommand: async () => { calls.continue += 1; } },
    productionExperienceService: { autoPassForAutopilot: async () => { calls.autoPass += 1; } },
  };
  await resolveAutopilotWaitingCheckpoint(deps, "task-paused");
  assert.equal(calls.continue, 0, "resolver must not enqueue continue for a paused task");
  assert.equal(calls.autoPass, 0, "resolver must not auto-pass for a paused task");
});

test("resolveAutopilotWaitingCheckpoint still resolves non-paused checkpoints", async () => {
  const calls = { continue: 0 };
  const deps = {
    workflowService: {
      getTaskById: async () => ({
        status: "waiting_approval",
        pendingManualRecovery: false,
        checkpointType: "chapter_batch_ready",
      }),
    },
    commandService: { enqueueContinueCommand: async () => { calls.continue += 1; } },
    productionExperienceService: { autoPassForAutopilot: async () => {} },
  };
  await resolveAutopilotWaitingCheckpoint(deps, "task-x");
  assert.equal(calls.continue, 1);
});
