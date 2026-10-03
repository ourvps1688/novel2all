const test = require("node:test");
const assert = require("node:assert/strict");
const {
  resolveAutopilotWaitingCheckpoint,
} = require("../dist/services/novel/director/runtime/autopilotCheckpointResolver.js");
const {
  AutopilotCheckpointWatchdog,
} = require("../dist/services/novel/director/runtime/autopilotCheckpointWatchdog.js");

function buildResolverDeps(handler) {
  return {
    workflowService: {
      getTaskById: async () => ({ checkpointType: handler.checkpointType }),
    },
    commandService: {
      enqueueContinueCommand: async (taskId, input) => {
        (handler.continueCalls ||= []).push({ taskId, input });
      },
    },
    productionExperienceService: {
      autoPassForAutopilot: async (taskId) => {
        (handler.autoPassCalls ||= []).push(taskId);
      },
    },
  };
}

test("resolver maps production_experience_required to autoPassForAutopilot", async () => {
  const handler = { checkpointType: "production_experience_required" };
  const deps = buildResolverDeps(handler);
  await resolveAutopilotWaitingCheckpoint(deps, "task-1");
  assert.deepEqual(handler.autoPassCalls, ["task-1"]);
  assert.equal(handler.continueCalls, undefined);
});

test("resolver maps replan_required to skip_quality_repair continue", async () => {
  const handler = { checkpointType: "replan_required" };
  const deps = buildResolverDeps(handler);
  await resolveAutopilotWaitingCheckpoint(deps, "task-2");
  assert.equal(handler.autoPassCalls, undefined);
  assert.equal(handler.continueCalls.length, 1);
  assert.deepEqual(handler.continueCalls[0], {
    taskId: "task-2",
    input: { continuationMode: "skip_quality_repair", forceResume: true },
  });
});

test("resolver maps chapter_batch_ready to auto_execute_range continue", async () => {
  const handler = { checkpointType: "chapter_batch_ready" };
  const deps = buildResolverDeps(handler);
  await resolveAutopilotWaitingCheckpoint(deps, "task-3");
  assert.equal(handler.autoPassCalls, undefined);
  assert.equal(handler.continueCalls.length, 1);
  assert.deepEqual(handler.continueCalls[0], {
    taskId: "task-3",
    input: { continuationMode: "auto_execute_range", forceResume: true },
  });
});

test("resolver maps the remaining auto-execute-range checkpoints", async () => {
  for (const checkpointType of [
    "step_review_required",
    "book_contract_ready",
    "candidate_selection_required",
    "character_setup_required",
    "volume_strategy_ready",
  ]) {
    const handler = { checkpointType };
    const deps = buildResolverDeps(handler);
    await resolveAutopilotWaitingCheckpoint(deps, "task-x");
    assert.equal(handler.autoPassCalls, undefined);
    assert.equal(handler.continueCalls.length, 1);
    assert.equal(handler.continueCalls[0].input.continuationMode, "auto_execute_range");
    assert.equal(handler.continueCalls[0].input.forceResume, true);
  }
});

test("resolver no-ops for workflow_completed / quality_repair / missing checkpoint", async () => {
  for (const checkpointType of ["workflow_completed", "quality_repair", null, undefined]) {
    const handler = { checkpointType };
    const deps = buildResolverDeps(handler);
    await resolveAutopilotWaitingCheckpoint(deps, "task-x");
    assert.equal(handler.autoPassCalls, undefined);
    assert.equal(handler.continueCalls, undefined);
  }
});

test("watchdog scan filters by runMode === full_book_autopilot and skips others", async () => {
  const rows = [
    {
      id: "t-autopilot",
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
    {
      id: "t-no-mode",
      lane: "auto_director",
      status: "waiting_approval",
      pendingManualRecovery: false,
      seedPayloadJson: JSON.stringify({}),
    },
    {
      id: "t-manual-recovery",
      lane: "auto_director",
      status: "waiting_approval",
      pendingManualRecovery: true,
      seedPayloadJson: JSON.stringify({ runMode: "full_book_autopilot" }),
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

  assert.deepEqual(result.sort(), ["t-autopilot"]);
  assert.deepEqual(resolved.sort(), ["t-autopilot"]);
});

test("watchdog startWatchdog triggers periodic scans and stopWatchdog halts them", async () => {
  const rows = [
    {
      id: "t1",
      lane: "auto_director",
      status: "waiting_approval",
      pendingManualRecovery: false,
      seedPayloadJson: JSON.stringify({ runMode: "full_book_autopilot" }),
    },
  ];
  const mockPrisma = {
    novelWorkflowTask: {
      findMany: async () => rows,
    },
  };
  const resolved = [];
  const watchdog = new AutopilotCheckpointWatchdog({
    prisma: mockPrisma,
    resolve: async (taskId) => {
      resolved.push(taskId);
    },
  });

  watchdog.startWatchdog({ intervalMs: 10 });
  await new Promise((resolve) => setTimeout(resolve, 45));
  watchdog.stopWatchdog();
  const afterFirstStop = resolved.length;
  await new Promise((resolve) => setTimeout(resolve, 45));

  assert.ok(afterFirstStop >= 1, "expected at least one scan to resolve the autopilot task");
  assert.equal(resolved.length, afterFirstStop, "stopWatchdog should prevent further scans");
});
