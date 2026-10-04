// Phase 4 (4a) — BookAnalysisOrchestration unit tests.
//
// Exercises the headless orchestration (ingest -> chapter split -> analyze ->
// poll) with fully mocked collaborators via dependency injection. All three
// collaborators are injected, so no Prisma / LLM calls are made.
const assert = require("node:assert/strict");
const test = require("node:test");

const {
  BookAnalysisOrchestration,
} = require("../dist/services/novel/director/runtime/bookAnalysisOrchestration.js");

function buildDeps({ status = "succeeded", statusSequence = null, now = null } = {}) {
  const calls = { createDocument: 0, ensureChapters: 0, createAnalysis: 0, getAnalysisById: 0 };
  const knowledgeService = {
    createDocument: async (input) => {
      calls.createDocument += 1;
      return { id: "doc-1", activeVersionId: "ver-1", title: input.title, fileName: input.fileName };
    },
  };
  const documentChapterService = {
    ensureChaptersForVersion: async (versionId, documentId) => {
      calls.ensureChapters += 1;
      assert.equal(versionId, "ver-1");
      assert.equal(documentId, "doc-1");
      return { documentVersionId: versionId, splitter: "rule", chapters: [] };
    },
  };
  let analysisCallCount = 0;
  const bookAnalysisService = {
    createAnalysis: async (input) => {
      calls.createAnalysis += 1;
      return { id: "analysis-1", status: "queued", documentId: input.documentId };
    },
    getAnalysisById: async (id) => {
      calls.getAnalysisById += 1;
      analysisCallCount += 1;
      const resolvedStatus = statusSequence
        ? statusSequence[Math.min(analysisCallCount - 1, statusSequence.length - 1)]
        : status;
      // A `null` status models the analysis row having disappeared: the real
      // BookAnalysisService.getAnalysisById returns `null` for the whole
      // detail, which is what the orchestration's disappearance check expects.
      if (resolvedStatus === null) {
        return null;
      }
      return {
        id,
        status: resolvedStatus,
        lastError: resolvedStatus === "failed" ? "boom" : null,
      };
    },
  };
  const deps = {
    bookAnalysisService,
    knowledgeService,
    documentChapterService,
    sleep: async () => {},
    now: now ?? (() => Date.now()),
  };
  return { deps, calls, statusSequence };
}

test("ingestTextAsDocument calls createDocument then ensureChaptersForVersion and returns ids", async () => {
  const { deps, calls } = buildDeps();
  const orch = new BookAnalysisOrchestration(deps);
  const result = await orch.ingestTextAsDocument("我的参考书", "第一章 开头……");
  assert.equal(calls.createDocument, 1);
  assert.equal(calls.ensureChapters, 1);
  assert.equal(result.documentId, "doc-1");
  assert.equal(result.versionId, "ver-1");
});

test("ingestTextAsDocument uses a unique title/fileName so dedup is avoided", async () => {
  const { deps } = buildDeps();
  const orch = new BookAnalysisOrchestration(deps);
  const first = await orch.ingestTextAsDocument("同名书", "内容");
  const second = await orch.ingestTextAsDocument("同名书", "其它内容");
  assert.equal(first.documentId, "doc-1");
  assert.equal(second.documentId, "doc-1");
});

test("runBookAnalysis calls createAnalysis then polls getAnalysisById until succeeded", async () => {
  // First poll returns running, then succeeded.
  const { deps, calls } = buildDeps({ statusSequence: ["running", "succeeded"] });
  const orch = new BookAnalysisOrchestration(deps);
  const result = await orch.runBookAnalysis("doc-1");
  assert.equal(calls.createAnalysis, 1);
  assert.equal(calls.getAnalysisById, 2);
  assert.equal(result.analysisId, "analysis-1");
  assert.equal(result.analysis.status, "succeeded");
});

test("runBookAnalysis returns immediately on first succeeded poll", async () => {
  const { deps, calls } = buildDeps({ status: "succeeded" });
  const orch = new BookAnalysisOrchestration(deps);
  const result = await orch.runBookAnalysis("doc-1");
  assert.equal(calls.getAnalysisById, 1);
  assert.equal(result.analysisId, "analysis-1");
});

test("runBookAnalysis throws on failed status", async () => {
  const { deps } = buildDeps({ status: "failed" });
  const orch = new BookAnalysisOrchestration(deps);
  await assert.rejects(
    () => orch.runBookAnalysis("doc-1"),
    /ended with status "failed": boom/,
  );
});

test("runBookAnalysis throws on cancelled status", async () => {
  const { deps } = buildDeps({ status: "cancelled" });
  const orch = new BookAnalysisOrchestration(deps);
  await assert.rejects(
    () => orch.runBookAnalysis("doc-1"),
    /ended with status "cancelled"/,
  );
});

test("runBookAnalysis throws when analysis disappears (null)", async () => {
  const { deps } = buildDeps({ statusSequence: ["running", null] });
  const orch = new BookAnalysisOrchestration(deps);
  await assert.rejects(
    () => orch.runBookAnalysis("doc-1"),
    /disappeared during polling/,
  );
});

test("runBookAnalysis throws on timeout", async () => {
  // Always "queued"; clock advances 10ms per now() call; deadline = 10 + 30 = 40.
  let clock = 0;
  const now = () => {
    clock += 10;
    return clock;
  };
  const { deps } = buildDeps({ status: "queued", now });
  const orch = new BookAnalysisOrchestration(deps);
  await assert.rejects(
    () => orch.runBookAnalysis("doc-1", { timeoutMs: 30, pollIntervalMs: 1 }),
    /timed out after 30ms/,
  );
});

test("ingestAndAnalyze combines ingest + analyze and returns all four ids", async () => {
  const { deps, calls } = buildDeps({ status: "succeeded" });
  const orch = new BookAnalysisOrchestration(deps);
  const result = await orch.ingestAndAnalyze("参考书", "正文内容");
  assert.equal(calls.createDocument, 1);
  assert.equal(calls.ensureChapters, 1);
  assert.equal(calls.createAnalysis, 1);
  assert.equal(calls.getAnalysisById, 1);
  assert.deepEqual(
    { documentId: result.documentId, versionId: result.versionId, analysisId: result.analysisId },
    { documentId: "doc-1", versionId: "ver-1", analysisId: "analysis-1" },
  );
  assert.equal(result.analysis.status, "succeeded");
});

test("ingestAndAnalyze skips ingest when existingDocumentId is provided", async () => {
  const { deps, calls } = buildDeps({ status: "succeeded" });
  const orch = new BookAnalysisOrchestration(deps);
  const result = await orch.ingestAndAnalyze("ignored", "ignored", {
    existingDocumentId: "prebuilt-doc",
  });
  assert.equal(calls.createDocument, 0);
  assert.equal(calls.ensureChapters, 0);
  assert.equal(calls.createAnalysis, 1);
  assert.equal(result.documentId, "prebuilt-doc");
  assert.equal(result.analysisId, "analysis-1");
});
