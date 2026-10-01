import test from "node:test";
import assert from "node:assert/strict";
import { resolveCreativeHubWorkspacePresentation } from "./creativeHubWorkspaceViewModel.ts";

function baseInput(overrides = {}) {
  return {
    isRunning: false,
    ...overrides,
  };
}

const needsRecoveryAttention = {
  novelId: "n1",
  novelTitle: "测试小说",
  level: "needs_recovery",
  headline: "自动导演需要恢复",
  detail: "执行失败，需要你处理。",
  requiresUserAction: true,
  primaryAction: {
    type: "continue_director_runtime",
    label: "继续自动导演",
    emphasis: "default",
    target: { href: "/novels/n1" },
    commandPayload: { taskId: "t1" },
  },
  fallbackActions: [],
  updatedAt: new Date().toISOString(),
};

test("returns open_recovery when director attention is needs_recovery", () => {
  const result = resolveCreativeHubWorkspacePresentation(
    baseInput({
      diagnostics: { failureSummary: "boom" },
      directorAttention: needsRecoveryAttention,
    }),
  );
  assert.equal(result.recommendation.action, "open_recovery");
  assert.equal(result.recommendation.recoveryAction, needsRecoveryAttention.primaryAction);
  assert.equal(result.recommendation.actionLabel, "继续自动导演");
  assert.equal(result.recommendation.tone, "danger");
});

test("returns open_recovery (warning tone) when director attention is waiting_approval", () => {
  const waiting = { ...needsRecoveryAttention, level: "waiting_approval", headline: "等待审批" };
  const result = resolveCreativeHubWorkspacePresentation(
    baseInput({
      diagnostics: { failureSummary: "boom" },
      directorAttention: waiting,
    }),
  );
  assert.equal(result.recommendation.action, "open_recovery");
  assert.equal(result.recommendation.tone, "warning");
});

test("falls back to send_prompt when no director attention is supplied", () => {
  const result = resolveCreativeHubWorkspacePresentation(
    baseInput({ diagnostics: { failureSummary: "boom" } }),
  );
  assert.equal(result.recommendation.action, "send_prompt");
  assert.ok(result.recommendation.prompt);
});

test("falls back to send_prompt when attention is running (not actionable)", () => {
  const running = { ...needsRecoveryAttention, level: "running", primaryAction: null };
  const result = resolveCreativeHubWorkspacePresentation(
    baseInput({
      diagnostics: { failureSummary: "boom" },
      directorAttention: running,
    }),
  );
  assert.equal(result.recommendation.action, "send_prompt");
});
