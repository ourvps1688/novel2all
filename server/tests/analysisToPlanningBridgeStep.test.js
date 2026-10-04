// Phase 4 (T4.5) — analysis_to_planning_bridge workflow step module tests.
//
// Verifies the new autopilot bridge step:
//   - is registered in the unified director workflow step registry,
//   - declares the expected write contract (story_macro / volume_strategy /
//     beat_sheet) so the module-load write-contract validation stays green,
//   - is blocked (ready === false) when the director input has no bound book
//     analysis (referenceBookAnalysisId / continuationBookAnalysisId).
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  directorWorkflowStepModuleRegistry,
  getDirectorPlanningStepModule,
  validateDirectorWorkflowStepWriteContracts,
} = require("../dist/services/novel/director/workflowStepRuntime/directorWorkflowStepModules.js");

test("analysis_to_planning_bridge step module is registered with the expected contract", () => {
  const module = getDirectorPlanningStepModule("analysis_to_planning_bridge");

  assert.equal(module.id, "book.analysis.planning_bridge");
  assert.equal(module.nodeKey, "analysis_planning_bridge");
  assert.equal(module.targetType, "novel");
  assert.deepEqual(module.reads, ["book_analysis"]);
  assert.deepEqual(module.writes, ["story_macro", "volume_strategy", "beat_sheet"]);
  assert.equal(module.mayModifyUserContent, true);
  assert.equal(module.requiresApprovalByDefault, false);
  assert.equal(module.supportsAutoRetry, false);

  // The module is part of the unified registry.
  const registryIds = directorWorkflowStepModuleRegistry.list().map((entry) => entry.id);
  assert.ok(registryIds.includes("book.analysis.planning_bridge"));
});

test("analysis_to_planning_bridge module satisfies the director write contract at import", () => {
  assert.doesNotThrow(() => validateDirectorWorkflowStepWriteContracts());
});

test("analysis_to_planning_bridge readiness is blocked without a bound book analysis", async () => {
  const module = getDirectorPlanningStepModule("analysis_to_planning_bridge");
  const context = { novelId: "novel-bridge-readiness", mode: "manual" };

  const readiness = await module.inspectReadiness(context);

  assert.equal(readiness.ready, false);
  assert.equal(readiness.blockers.length, 1);
  assert.equal(readiness.blockers[0].code, "missing_book_analysis");
  assert.equal(readiness.blockers[0].nextAction, "analyze_reference_book");
});

test("analysis_to_planning_bridge exposes the full step module hooks", () => {
  const module = getDirectorPlanningStepModule("analysis_to_planning_bridge");

  assert.equal(typeof module.inspectReadiness, "function");
  assert.equal(typeof module.inspectCompletion, "function");
  assert.equal(typeof module.buildInput, "function");
  assert.equal(typeof module.inspectProgress, "function");
  assert.equal(typeof module.recover, "function");
  assert.equal(typeof module.completeCriteria, "function");
  assert.equal(typeof module.commit, "function");
});
