const test = require("node:test");
const assert = require("node:assert/strict");
const {
  computeAutopilotBookBudget,
  MODEL_PRICE_TABLE,
} = require("../dist/services/novel/director/runtime/autopilotBookBudget.js");

const EXPECTED_STAGE_ORDER = [
  "candidate_selection",
  "story_macro",
  "book_contract",
  "world_setup",
  "character_setup",
  "volume_strategy",
  "structured_outline",
  "chapter_execution",
];

test("a) default returns 8 stages in the prescribed order", () => {
  const summary = computeAutopilotBookBudget();
  assert.equal(summary.stages.length, 8);
  assert.deepEqual(
    summary.stages.map((s) => s.stage),
    EXPECTED_STAGE_ORDER,
  );
});

test("b) totals equal the sum of stage fields", () => {
  const summary = computeAutopilotBookBudget();
  const sumCalls = summary.stages.reduce((acc, s) => acc + s.calls, 0);
  const sumInput = summary.stages.reduce((acc, s) => acc + s.inputTokens, 0);
  const sumOutput = summary.stages.reduce((acc, s) => acc + s.outputTokens, 0);
  const sumSeconds = summary.stages.reduce((acc, s) => acc + s.estimatedSeconds, 0);
  assert.equal(summary.totals.calls, sumCalls);
  assert.equal(summary.totals.inputTokens, sumInput);
  assert.equal(summary.totals.outputTokens, sumOutput);
  assert.equal(summary.totals.estimatedSeconds, sumSeconds);
});

test("c) costByModel has an entry for every model, all finite and > 0 by default", () => {
  const summary = computeAutopilotBookBudget();
  for (const modelId of Object.keys(MODEL_PRICE_TABLE)) {
    assert.ok(modelId in summary.costByModel, `missing ${modelId}`);
    const cost = summary.costByModel[modelId];
    assert.ok(Number.isFinite(cost), `${modelId} cost not finite`);
    assert.ok(cost > 0, `${modelId} cost should be > 0 for default 45 chapters`);
  }
});

test("d) determinism: identical input yields deeply-equal results", () => {
  const a = computeAutopilotBookBudget({ expectedVolumes: 4, expectedChaptersPerVolume: 20 });
  const b = computeAutopilotBookBudget({ expectedVolumes: 4, expectedChaptersPerVolume: 20 });
  // Compare everything except the timestamp.
  const strip = (s) => {
    const { generatedAt, ...rest } = s;
    return rest;
  };
  assert.deepEqual(strip(a), strip(b));
});

test("e) edge: expectedVolumes 0 does not crash; chapter stages 0, totals 0, cost 0", () => {
  const summary = computeAutopilotBookBudget({ expectedVolumes: 0 });
  assert.equal(summary.expectedVolumes, 0);
  assert.equal(summary.stages.length, 8);
  for (const stage of summary.stages) {
    assert.equal(stage.calls, 0);
    assert.equal(stage.inputTokens, 0);
    assert.equal(stage.outputTokens, 0);
    assert.equal(stage.estimatedSeconds, 0);
  }
  assert.equal(summary.totals.calls, 0);
  assert.equal(summary.totals.inputTokens, 0);
  assert.equal(summary.totals.outputTokens, 0);
  assert.equal(summary.totals.estimatedSeconds, 0);
  for (const [modelId, cost] of Object.entries(summary.costByModel)) {
    assert.equal(cost, 0, `${modelId} cost should be 0 when no volumes`);
  }
});

test("f) costByModel / input tokens scale with book size", () => {
  const small = computeAutopilotBookBudget();
  const large = computeAutopilotBookBudget({ expectedVolumes: 5, expectedChaptersPerVolume: 30 });
  assert.ok(
    large.totals.inputTokens > small.totals.inputTokens,
    "larger book should have more input tokens",
  );
  for (const modelId of Object.keys(MODEL_PRICE_TABLE)) {
    assert.ok(
      large.costByModel[modelId] > small.costByModel[modelId],
      `${modelId} cost should scale up with size`,
    );
  }
});
