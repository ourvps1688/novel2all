const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ChapterReverseDecomposition,
} = require("../dist/services/novel/director/runtime/chapterReverseDecomposition.js");

/**
 * Unit tests for the reverse decomposition of written chapters (Phase 4 T4.2).
 *
 * The service is exercised with fully injected fake dependencies so no database
 * is touched. We assert:
 *  - task sheet + serialized scene cards are written
 *  - the 章法定位 beat note is appended to the task sheet
 *  - idempotent skip when both artifacts already exist (and force override)
 *  - continuation vs reference analysis selection for evidence
 *  - best-effort execution-contract fill (failure must not fail decompose)
 *  - novel-wide aggregation in decomposeNovel
 */

function makeScenePlan(targetWordCount = 3000) {
  return {
    targetWordCount,
    scenes: [
      { title: "对峙", purpose: "逼问身世", entryState: "回到旧宅", exitState: "老仆承认", targetWordCount: 1000 },
      { title: "吐露", purpose: "临终线索", entryState: "老仆承认", exitState: "连夜出逃", targetWordCount: 1000 },
      { title: "出逃", purpose: "带名逃亡", entryState: "连夜出逃", exitState: "踏上新路", targetWordCount: 1000 },
    ],
  };
}

function makePromptResult(overrides = {}) {
  return {
    output: {
      taskSheet: "章节目标：揭露身世。\n关键角色：主角、老仆。\n必须推进：身世真相。\n必须保留：玉佩。\n风险提醒：别揭反派。\n收尾钩子：第二个名字。",
      scenePlan: makeScenePlan(),
      beatNote: "中段压力升级",
      ...overrides,
    },
  };
}

function makeService(overrides = {}) {
  const calls = {
    update: [],
    ensure: [],
    getConfig: [],
    promptInputs: [],
    buildEvidenceCalls: [],
  };
  const deps = {
    getChapter: async () => ({
      id: "c1",
      novelId: "n1",
      title: "第1章",
      order: 1,
      content: "正文内容……",
      taskSheet: null,
      sceneCards: null,
    }),
    listChapters: async () => [{ id: "c1" }, { id: "c2" }],
    updateChapterArtifacts: async (novelId, chapterId, artifacts) => {
      calls.update.push({ novelId, chapterId, artifacts });
    },
    getNovelConfig: async (novelId) => {
      calls.getConfig.push(novelId);
      return { writingMode: "original", analysisId: "analysis-1" };
    },
    buildAnalysisEvidence: async (analysisId, stage, sectionKeys) => {
      calls.buildEvidenceCalls.push({ analysisId, stage, sectionKeys });
      return `evidence:${analysisId ?? "null"}`;
    },
    ensureExecutionContract: async (novelId, chapterId) => {
      calls.ensure.push({ novelId, chapterId });
      return { ok: true };
    },
    promptRunner: async (args) => {
      calls.promptInputs.push(args.promptInput);
      return makePromptResult();
    },
    ...overrides,
  };
  const service = new ChapterReverseDecomposition(deps);
  return { service, calls };
}

test("decompose writes the task sheet and serialized scene cards and fills the execution contract", async () => {
  const { service, calls } = makeService();
  const result = await service.decompose("n1", "c1");

  assert.equal(result.skipped, false);
  assert.equal(result.chapterId, "c1");
  assert.ok(result.taskSheet.includes("章节目标"));
  assert.equal(calls.update.length, 1);

  const artifacts = calls.update[0].artifacts;
  assert.equal(artifacts.taskSheet, result.taskSheet);
  const parsed = JSON.parse(artifacts.sceneCards);
  assert.equal(parsed.scenes.length, 3);
  assert.ok(parsed.lengthBudget, "scene plan must be normalized with a length budget");
  assert.equal(calls.ensure.length, 1);
  assert.deepEqual(calls.ensure[0], { novelId: "n1", chapterId: "c1" });
});

test("decompose appends the 章法定位 beat note to the persisted task sheet", async () => {
  const { service } = makeService();
  const result = await service.decompose("n1", "c1");

  assert.ok(result.taskSheet.includes("章法定位：中段压力升级"));
  assert.ok(result.taskSheet.length <= 600, "task sheet must stay within the 600-char contract");
});

test("decompose is idempotent and skips chapters that already carry both artifacts", async () => {
  const { service, calls } = makeService({
    getChapter: async () => ({
      id: "c1",
      novelId: "n1",
      title: "第1章",
      order: 1,
      content: "正文内容……",
      taskSheet: "已有任务单",
      sceneCards: '{"scenes":[]}',
    }),
  });
  const result = await service.decompose("n1", "c1");

  assert.equal(result.skipped, true);
  assert.equal(calls.update.length, 0);
  assert.equal(calls.ensure.length, 0);
  assert.equal(calls.promptInputs.length, 0);
});

test("force overrides the idempotent skip", async () => {
  const { service, calls } = makeService({
    getChapter: async () => ({
      id: "c1",
      novelId: "n1",
      title: "第1章",
      order: 1,
      content: "正文内容……",
      taskSheet: "已有任务单",
      sceneCards: '{"scenes":[]}',
    }),
  });
  const result = await service.decompose("n1", "c1", { force: true });

  assert.equal(result.skipped, false);
  assert.equal(calls.update.length, 1);
  assert.equal(calls.promptInputs.length, 1);
});

test("continuation mode selects continuationBookAnalysisId for evidence", async () => {
  const configCalls = [];
  const { service, calls } = makeService({
    getNovelConfig: async (novelId) => {
      configCalls.push(novelId);
      return { writingMode: "continuation", analysisId: "continuation-analysis" };
    },
  });
  await service.decompose("n1", "c1");

  assert.deepEqual(configCalls, ["n1"]);
  assert.equal(calls.promptInputs[0].analysisEvidence, "evidence:continuation-analysis");
});

test("reference mode selects referenceBookAnalysisId for evidence", async () => {
  const { service, calls } = makeService({
    getNovelConfig: async () => ({ writingMode: "original", analysisId: "reference-analysis" }),
  });
  await service.decompose("n1", "c1");

  assert.equal(calls.promptInputs[0].analysisEvidence, "evidence:reference-analysis");
});

test("no analysis evidence is built when the novel has no analysis id", async () => {
  const { service, calls } = makeService({
    getNovelConfig: async () => ({ writingMode: "original", analysisId: null }),
  });
  await service.decompose("n1", "c1");

  assert.equal(calls.promptInputs[0].analysisEvidence, "");
  assert.equal(calls.buildEvidenceCalls.length, 0);
});

test("a failed execution-contract fill is best-effort and must not fail the decompose", async () => {
  const { service, calls } = makeService({
    ensureExecutionContract: async () => {
      throw new Error("chapter cannot be matched into a volume plan");
    },
  });
  const result = await service.decompose("n1", "c1");

  assert.equal(result.skipped, false);
  assert.equal(calls.update.length, 1, "artifacts are still written even when the contract fill throws");
});

test("missing chapter throws before any LLM call or write", async () => {
  const { service, calls } = makeService({
    getChapter: async () => {
      throw new Error("章节不存在。");
    },
  });
  await assert.rejects(() => service.decompose("n1", "c1"), /章节不存在/);
  assert.equal(calls.promptInputs.length, 0);
  assert.equal(calls.update.length, 0);
});

test("chapter title falls back to 第N章 when the title is missing", async () => {
  const { service, calls } = makeService({
    getChapter: async () => ({
      id: "c1",
      novelId: "n1",
      title: null,
      order: 3,
      content: "正文内容……",
      taskSheet: null,
      sceneCards: null,
    }),
  });
  await service.decompose("n1", "c1");
  assert.equal(calls.promptInputs[0].chapterTitle, "第3章");
});

test("decomposeNovel aggregates decomposed and skipped chapters", async () => {
  const updateCalls = [];
  const service = new ChapterReverseDecomposition({
    getChapter: async (novelId, chapterId) => chapterId === "c1"
      ? { id: "c1", novelId: "n1", title: "第1章", order: 1, content: "x", taskSheet: null, sceneCards: null }
      : { id: "c2", novelId: "n1", title: "第2章", order: 2, content: "x", taskSheet: "t", sceneCards: '{"scenes":[]}' },
    listChapters: async () => [{ id: "c1" }, { id: "c2" }],
    updateChapterArtifacts: async (novelId, chapterId, artifacts) => {
      updateCalls.push({ novelId, chapterId, artifacts });
    },
    getNovelConfig: async () => ({ writingMode: "original", analysisId: "a1" }),
    buildAnalysisEvidence: async () => "",
    ensureExecutionContract: async () => {},
    promptRunner: async () => makePromptResult(),
  });

  const result = await service.decomposeNovel("n1");
  assert.deepEqual(result.decomposed, ["c1"]);
  assert.deepEqual(result.skipped, ["c2"]);
  assert.equal(updateCalls.length, 1);
  assert.equal(updateCalls[0].chapterId, "c1");
});
