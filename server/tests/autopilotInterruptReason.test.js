// T3.4 interrupt / circuit-breaker reason exposure — verification (zero migration).
//
// The runtime latches a circuit-breaker `reason` (7-value set). T3.4 maps it onto the
// full_book_autopilot interrupt reason (5-value set) and surfaces it on the projections
// and the task notice. The circuit-breaker reason is already persisted in the task seed
// payload (autoExecution.circuitBreaker), so no new DB column is required.
const assert = require("node:assert/strict");
const test = require("node:test");

const {
  mapCircuitBreakerReasonToInterruptReason,
  DIRECTOR_FULL_BOOK_AUTOPILOT_INTERRUPT_REASONS,
} = require("@ai-novel/shared/types/novelDirector");
const {
  extractCircuitBreaker,
} = require("../dist/services/novel/director/projections/DirectorBookAutomationProjectionModel.js");

const CIRCUIT_BREAKER_REASONS = [
  "auto_repair_exhausted",
  "replan_loop",
  "model_unavailable",
  "service_unavailable",
  "protected_user_content",
  "unrecoverable_data_risk",
  "usage_anomaly",
];

// Expected mapping: shared reasons 1:1, circuit-breaker-only (replan_loop / usage_anomaly)
// collapse onto the closest interrupt reason (auto_repair_exhausted).
const EXPECTED_MAP = {
  auto_repair_exhausted: "auto_repair_exhausted",
  replan_loop: "auto_repair_exhausted",
  model_unavailable: "model_unavailable",
  service_unavailable: "service_unavailable",
  protected_user_content: "protected_user_content",
  unrecoverable_data_risk: "unrecoverable_data_risk",
  usage_anomaly: "auto_repair_exhausted",
};

test("mapCircuitBreakerReasonToInterruptReason maps all 7 circuit-breaker reasons without throwing", () => {
  for (const reason of CIRCUIT_BREAKER_REASONS) {
    let mapped;
    assert.doesNotThrow(() => {
      mapped = mapCircuitBreakerReasonToInterruptReason(reason);
    });
    assert.equal(mapped, EXPECTED_MAP[reason], `reason=${reason}`);
    assert.ok(
      DIRECTOR_FULL_BOOK_AUTOPILOT_INTERRUPT_REASONS.includes(mapped),
      `mapped value ${mapped} must be a valid interrupt reason`,
    );
  }
});

test("mapCircuitBreakerReasonToInterruptReason returns null for unknown / null / undefined", () => {
  assert.equal(mapCircuitBreakerReasonToInterruptReason(null), null);
  assert.equal(mapCircuitBreakerReasonToInterruptReason(undefined), null);
  assert.equal(mapCircuitBreakerReasonToInterruptReason("not_a_reason"), null);
});

test("projection derives interruptReason from the persisted circuit-breaker state", () => {
  // Mirror the exact derivation performed by buildDirectorBookAutomationProjection:
  //   circuitBreaker = extractCircuitBreaker(latestTask?.seedPayloadJson)
  //   interruptReason = mapCircuitBreakerReasonToInterruptReason(circuitBreaker?.reason)
  for (const reason of CIRCUIT_BREAKER_REASONS) {
    const seedPayloadJson = JSON.stringify({
      autoExecution: { circuitBreaker: { status: "open", reason } },
    });
    const latestTask = { seedPayloadJson };
    const circuitBreaker = extractCircuitBreaker(latestTask.seedPayloadJson);
    const circuitBreakerReason = circuitBreaker?.reason ?? null;
    const interruptReason = mapCircuitBreakerReasonToInterruptReason(circuitBreakerReason);

    assert.equal(circuitBreakerReason, reason);
    assert.equal(interruptReason, EXPECTED_MAP[reason]);
    assert.ok(DIRECTOR_FULL_BOOK_AUTOPILOT_INTERRUPT_REASONS.includes(interruptReason));
  }
});

test("projection carries no interruptReason when no circuit breaker tripped", () => {
  const seedPayloadJson = JSON.stringify({ autoExecution: { circuitBreaker: { status: "closed" } } });
  const circuitBreaker = extractCircuitBreaker(seedPayloadJson);
  const interruptReason = mapCircuitBreakerReasonToInterruptReason(circuitBreaker?.reason ?? null);
  assert.equal(interruptReason, null);
});

test("all mapped interrupt reasons belong to the declared interrupt reason set", () => {
  const mapped = CIRCUIT_BREAKER_REASONS.map((r) => mapCircuitBreakerReasonToInterruptReason(r));
  for (const value of mapped) {
    assert.ok(DIRECTOR_FULL_BOOK_AUTOPILOT_INTERRUPT_REASONS.includes(value));
  }
});
