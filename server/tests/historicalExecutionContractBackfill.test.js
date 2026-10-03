const test = require("node:test");
const assert = require("node:assert/strict");

const {
  backfillMissingExecutionContracts,
  hasExecutionContract,
} = require("../dist/services/novel/director/runtime/historicalExecutionContractBackfill.js");

test("hasExecutionContract requires both task sheet and scene cards", () => {
  assert.equal(hasExecutionContract({ taskSheet: null, sceneCards: null }), false);
  assert.equal(hasExecutionContract({ taskSheet: "x", sceneCards: null }), false);
  assert.equal(hasExecutionContract({ taskSheet: null, sceneCards: "x" }), false);
  assert.equal(hasExecutionContract({ taskSheet: "x", sceneCards: "y" }), true);
});

test("backfill generates contracts for missing chapters, skips present ones, swallows match failures", async () => {
  const chapters = [
    { id: "c1", novelId: "n1", order: 1, title: "第一章", taskSheet: null, sceneCards: null },
    { id: "c2", novelId: "n1", order: 2, title: "第二章", taskSheet: "ts", sceneCards: "sc" },
    { id: "c3", novelId: "n1", order: 3, title: "第三章", taskSheet: null, sceneCards: null },
  ];
  const ensureCalls = [];
  const deps = {
    listChapters: async () => chapters,
    ensureChapterExecutionContract: async (novelId, chapterId, options) => {
      ensureCalls.push({ novelId, chapterId, options });
      // Simulate findVolumeChapterMatch throwing for an unmapped historical chapter.
      if (chapterId === "c3") {
        throw new Error("当前章节未映射到卷规划章节，无法生成执行合同。");
      }
      return { id: chapterId };
    },
  };

  const result = await backfillMissingExecutionContracts(deps, { novelId: "n1" });

  assert.equal(result.novelId, "n1");
  assert.equal(result.totalChapters, 3);
  assert.equal(result.backfilled, 1);
  assert.equal(result.skipped, 1);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].chapterId, "c3");
  assert.match(result.errors[0].error, /未映射|执行合同/);

  // ensureChapterExecutionContract is called only for chapters lacking a contract (c1, c3), not c2.
  assert.deepEqual(
    ensureCalls.map((call) => call.chapterId).sort(),
    ["c1", "c3"],
  );
  // The autopilot entrypoint is forwarded to the reused generator.
  assert.equal(ensureCalls[0].options.entrypoint, "auto_director");
});

test("backfill with no chapters returns empty summary and does not call generator", async () => {
  const ensureCalls = [];
  const deps = {
    listChapters: async () => [],
    ensureChapterExecutionContract: async () => {
      ensureCalls.push(true);
      return {};
    },
  };
  const result = await backfillMissingExecutionContracts(deps, { novelId: "n1" });
  assert.equal(result.totalChapters, 0);
  assert.equal(result.backfilled, 0);
  assert.equal(result.skipped, 0);
  assert.equal(result.errors.length, 0);
  assert.equal(ensureCalls.length, 0);
});

test("backfill forwards explicit options to the generator", async () => {
  const ensureCalls = [];
  const deps = {
    listChapters: async () => [
      { id: "c1", novelId: "n1", order: 1, title: "第一章", taskSheet: null, sceneCards: null },
    ],
    ensureChapterExecutionContract: async (novelId, chapterId, options) => {
      ensureCalls.push(options);
      return { id: chapterId };
    },
  };
  const result = await backfillMissingExecutionContracts(deps, {
    novelId: "n1",
    options: { provider: "openai", model: "gpt-4o", entrypoint: "manual_repair" },
  });
  assert.equal(result.backfilled, 1);
  assert.equal(ensureCalls[0].provider, "openai");
  assert.equal(ensureCalls[0].model, "gpt-4o");
  // Explicit entrypoint overrides the default auto_director.
  assert.equal(ensureCalls[0].entrypoint, "manual_repair");
});
