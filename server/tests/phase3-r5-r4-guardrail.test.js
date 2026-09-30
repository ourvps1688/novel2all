// Phase 3 · T3-7 护栏固化（R5 质量债非阻断 + R4 恢复行为不变）
//
// 本文件把 R5 / R4 两条硬性护栏收敛到一处，作为 Phase 3 全程不得转红的回归基线
// （doc16 §T3-7 / §5.3）。它不修改任何生产行为，只锁定既有语义：
//   R5 — 质量债 / 质量检查类通知必须 autoContinuable，不得阻塞全局自动导演链；
//        只有明确的重规划（replan）通知才阻塞。
//   R4 — 恢复解析必须保持确定性映射：observed/resume 相位与 asset-first 恢复决策
//        在给定资产状态下返回稳定结果，不因 Phase 3 的结构收敛而变化。
//
// 运行方式同其它服务端测试：先 `pnpm --filter @ai-novel/shared build` + `pnpm run build`，
// 再 `node --test tests/phase3-r5-r4-guardrail.test.js`（或 `pnpm run test:node`）。

const test = require("node:test");
const assert = require("node:assert/strict");

// R5 只依赖纯函数 novelDirectorQualityRepairRisk（不触碰 prisma / shared ESM 子路径），
// 因此在本沙箱内可直接运行。
const { buildDirectorQualityRepairRisk } = require("../dist/services/novel/director/phases/novelDirectorQualityRepairRisk.js");

const QUALITY_NOTICE = "PIPELINE_QUALITY_REVIEW";
const REPLAN_NOTICE = "PIPELINE_REPLAN_REQUIRED";

test("R5: quality-debt / quality-review notices are always continuable (non-blocking)", () => {
  const cases = [
    {
      noticeCode: QUALITY_NOTICE,
      payload: JSON.stringify({ repairMode: "heavy_repair", qualityAlertDetails: ["第3章", "第4章", "第5章"] }),
      remainingChapterCount: 5,
    },
    {
      noticeCode: QUALITY_NOTICE,
      payload: JSON.stringify({ repairMode: "light_repair" }),
      remainingChapterCount: 1,
    },
    {
      payload: JSON.stringify({ repairMode: "heavy_repair" }),
      remainingChapterCount: 3,
    },
    {
      noticeCode: null,
      payload: JSON.stringify({ qualityAlertDetails: ["第1章"] }),
      remainingChapterCount: 0,
    },
  ];
  for (const input of cases) {
    const risk = buildDirectorQualityRepairRisk(input);
    assert.equal(risk.autoContinuable, true, `期望可继续: ${JSON.stringify(input)}`);
    assert.equal(risk.riskLevel, "low");
    assert.match(risk.reason, /质量债务/);
  }
});

test("R5: replan notice blocks continuation (the only blocking quality category)", () => {
  const risk = buildDirectorQualityRepairRisk({
    noticeCode: REPLAN_NOTICE,
    payload: JSON.stringify({ replanAlertDetails: ["第9章需要重规划（缺失比武环节）"] }),
    remainingChapterCount: 1,
  });
  assert.equal(risk.autoContinuable, false);
  assert.equal(risk.riskLevel, "replan");
});

// R4 依赖 novelDirectorRecovery（其传递依赖 shared ESM 子路径）。在标准 `pnpm test`
// 环境下直接 require 即可；本沙箱若 shared ESM 解析受限，下面这些用例与该仓库既有
// novelDirectorRecovery.test.js 表现一致（环境限制，非语义回归）。
let recoveryModule = null;
function getRecovery() {
  if (!recoveryModule) {
    recoveryModule = require("../dist/services/novel/director/recovery/novelDirectorRecovery.js");
  }
  return recoveryModule;
}

test("R4: observed resume phase only advances to structured_outline with both volume flags", () => {
  const { resolveObservedResumePhaseFromWorkspace } = getRecovery();
  assert.equal(
    resolveObservedResumePhaseFromWorkspace({ hasVolumeWorkspace: true, hasVolumeStrategyPlan: true }),
    "structured_outline",
  );
  assert.equal(
    resolveObservedResumePhaseFromWorkspace({ hasVolumeWorkspace: true, hasVolumeStrategyPlan: false }),
    null,
  );
  assert.equal(
    resolveObservedResumePhaseFromWorkspace({ hasVolumeWorkspace: false, hasVolumeStrategyPlan: true }),
    null,
  );
});

test("R4: safe pipeline phase fallback mapping is preserved (representative rows)", () => {
  const { resolveSafeDirectorPipelineStartPhase } = getRecovery();
  const none = {
    hasStoryMacroPlan: false,
    hasBookContract: false,
    hasWorldSetupPrepared: false,
    hasCharacters: false,
    hasVolumeWorkspace: false,
    hasVolumeStrategyPlan: false,
  };
  assert.equal(resolveSafeDirectorPipelineStartPhase({ requestedPhase: "character_setup", ...none }), "world_setup");
  assert.equal(resolveSafeDirectorPipelineStartPhase({ requestedPhase: "structured_outline", ...none }), "story_macro");

  const worldReady = {
    hasStoryMacroPlan: true,
    hasBookContract: true,
    hasWorldSetupPrepared: true,
    hasCharacters: false,
    hasVolumeWorkspace: false,
    hasVolumeStrategyPlan: false,
  };
  assert.equal(resolveSafeDirectorPipelineStartPhase({ requestedPhase: "character_setup", ...worldReady }), "character_setup");
  assert.equal(resolveSafeDirectorPipelineStartPhase({ requestedPhase: "structured_outline", ...worldReady }), "character_setup");

  const allReady = {
    hasStoryMacroPlan: true,
    hasBookContract: true,
    hasWorldSetupPrepared: true,
    hasCharacters: true,
    hasVolumeWorkspace: true,
    hasVolumeStrategyPlan: true,
  };
  assert.equal(resolveSafeDirectorPipelineStartPhase({ requestedPhase: "story_macro", ...allReady }), "structured_outline");
  assert.equal(resolveSafeDirectorPipelineStartPhase({ requestedPhase: "structured_outline", ...allReady }), "structured_outline");
});

test("R4: asset-first recovery resolves deterministically to auto_execution / phase / null", () => {
  const { resolveAssetFirstRecoveryFromSnapshot } = getRecovery();
  assert.deepEqual(
    resolveAssetFirstRecoveryFromSnapshot({
      runMode: "auto_to_execution",
      structuredOutlineRecoveryStep: "chapter_sync",
      volumeCount: 2,
      hasVolumeStrategyPlan: true,
      hasActivePipelineJob: false,
      hasExecutableRange: true,
      hasAutoExecutionState: true,
      latestCheckpointType: "chapter_batch_ready",
    }),
    { type: "auto_execution", resumeCheckpointType: "chapter_batch_ready" },
  );
  assert.deepEqual(
    resolveAssetFirstRecoveryFromSnapshot({
      runMode: "auto_to_ready",
      structuredOutlineRecoveryStep: "beat_sheet",
      volumeCount: 1,
      hasVolumeStrategyPlan: false,
      hasActivePipelineJob: false,
      hasExecutableRange: false,
      hasAutoExecutionState: false,
      latestCheckpointType: null,
    }),
    null,
  );
});
