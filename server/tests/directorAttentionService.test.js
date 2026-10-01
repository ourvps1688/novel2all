const test = require("node:test");
const assert = require("node:assert/strict");

const { mapProjectionToAttention } = require("../dist/services/novel/director/DirectorAttentionService.js");

function baseProjection(overrides = {}) {
  return {
    novelId: "novel_1",
    focusNovel: { id: "novel_1", title: "Test Novel", href: "/novel/novel_1" },
    status: "idle",
    headline: "All good",
    detail: null,
    blockedReason: null,
    requiresUserAction: false,
    primaryAction: null,
    secondaryActions: [],
    updatedAt: "2026-01-01T00:00:00.000Z",
    workerHealth: { derivedState: "idle" },
    ...overrides,
  };
}

function makeAction(type = "retry") {
  return { type, target: { novelId: "novel_1" } };
}

test("waiting_recovery -> needs_recovery with detail, title, and primaryAction", () => {
  const projection = baseProjection({
    status: "waiting_recovery",
    requiresUserAction: true,
    headline: "Recovery needed",
    detail: "Stuck on step 3",
    focusNovel: { id: "novel_1", title: "My Book", href: "/n/1" },
    primaryAction: makeAction("retry"),
  });
  const state = mapProjectionToAttention(projection);
  assert.equal(state.level, "needs_recovery");
  assert.equal(state.detail, "Stuck on step 3");
  assert.equal(state.novelTitle, "My Book");
  assert.equal(state.requiresUserAction, true);
  assert.ok(state.primaryAction);
});

test("waiting_approval -> waiting_approval with primaryAction", () => {
  const projection = baseProjection({
    status: "waiting_approval",
    primaryAction: makeAction("confirm_candidate"),
  });
  const state = mapProjectionToAttention(projection);
  assert.equal(state.level, "waiting_approval");
  assert.ok(state.primaryAction);
});

test("blocked -> needs_recovery with primaryAction (no dead-end at contract level)", () => {
  const projection = baseProjection({
    status: "blocked",
    primaryAction: makeAction("retry"),
  });
  const state = mapProjectionToAttention(projection);
  assert.equal(state.level, "needs_recovery");
  assert.ok(state.primaryAction);
});

test("failed -> needs_recovery", () => {
  const projection = baseProjection({ status: "failed" });
  assert.equal(mapProjectionToAttention(projection).level, "needs_recovery");
});

test("running + running_step -> running", () => {
  const projection = baseProjection({
    status: "running",
    workerHealth: { derivedState: "running_step" },
  });
  assert.equal(mapProjectionToAttention(projection).level, "running");
});

test("running + auto_recovering -> auto_recovering", () => {
  const projection = baseProjection({
    status: "running",
    workerHealth: { derivedState: "auto_recovering" },
  });
  assert.equal(mapProjectionToAttention(projection).level, "auto_recovering");
});

test("idle / cancelled / completed -> idle", () => {
  for (const status of ["idle", "cancelled", "completed"]) {
    const projection = baseProjection({ status });
    assert.equal(mapProjectionToAttention(projection).level, "idle", `status ${status} should map to idle`);
  }
});

test("missing secondaryActions -> fallbackActions is []", () => {
  const { secondaryActions, ...rest } = baseProjection();
  const projection = rest;
  const state = mapProjectionToAttention(projection);
  assert.deepEqual(state.fallbackActions, []);
});
