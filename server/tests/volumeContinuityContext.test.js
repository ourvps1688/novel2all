const test = require("node:test");
const assert = require("node:assert/strict");

const { buildCrossVolumeContinuityPackage } = require("../dist/services/novel/volume/volumeContinuityContext.js");

// Build a fake in-memory prisma-like client so we can exercise the optional
// DB enrichment without a real database connection ("No DB needed").
function makeFakeDb() {
  const characters = [
    {
      id: "char-1",
      name: "林惊蛰",
      role: "protagonist",
      currentState: "被困于霜狱第三层",
      currentGoal: "夺回家族令牌",
    },
  ];
  const mindSnapshots = [
    { characterId: "char-1", currentInterpretation: "表面顺从，暗中布局" },
  ];
  const payoffLedgerItems = [
    {
      ledgerKey: "ledger-book-1",
      title: "家族令牌之谜",
      summary: "令牌真实主人尚未揭晓",
      scopeType: "book",
      currentStatus: "pending_payoff",
    },
    {
      ledgerKey: "ledger-chapter-1",
      title: "第三章小伏笔",
      summary: "仅章节级兑现",
      scopeType: "chapter",
      currentStatus: "paid_off",
    },
  ];
  const novelBible = { worldRules: "灵气枯竭后，术法需以血为引" };
  const consistencyFacts = [
    { category: "plot", content: "主角左眼有旧伤" },
    { category: "character", content: "反派不饮热茶" },
  ];

  return {
    character: { findMany: async () => characters },
    characterMindSnapshot: { findMany: async () => mindSnapshots },
    payoffLedgerItem: { findMany: async () => payoffLedgerItems },
    novelBible: { findFirst: async () => novelBible },
    consistencyFact: { findMany: async () => consistencyFacts },
    chapterSummary: { findMany: async () => [] },
  };
}

function makeDocument() {
  const vol1 = {
    id: "vol-1",
    novelId: "novel-x",
    sortOrder: 1,
    title: "霜狱初醒",
    summary: "主角入狱",
    climax: "劫狱高潮",
    protagonistChange: "从懦弱到决绝",
    nextVolumeHook: "令牌浮现",
    resetPoint: null,
    openPayoffs: JSON.stringify(["令牌线索", "旧友背叛"]),
    status: "active",
    chapters: [{ id: "c1", chapterOrder: 1, title: "入狱" }],
    createdAt: "",
    updatedAt: "",
  };
  const vol2 = {
    id: "vol-2",
    novelId: "novel-x",
    sortOrder: 2,
    title: "血引之约",
    summary: "主角逃出",
    climax: "血祭反杀",
    protagonistChange: "学会代价",
    nextVolumeHook: "令牌认主",
    resetPoint: null,
    openPayoffs: JSON.stringify(["令牌认主伏笔"]),
    status: "active",
    chapters: [{ id: "c2", chapterOrder: 1, title: "逃亡" }],
    createdAt: "",
    updatedAt: "",
  };
  const vol3 = {
    id: "vol-3",
    novelId: "novel-x",
    sortOrder: 3,
    title: "令牌归处",
    summary: "终局前夜",
    climax: null,
    protagonistChange: null,
    nextVolumeHook: null,
    resetPoint: null,
    openPayoffs: JSON.stringify([]),
    status: "draft",
    chapters: [],
    createdAt: "",
    updatedAt: "",
  };

  return {
    novelId: "novel-x",
    workspaceVersion: "v2",
    volumes: [vol1, vol2, vol3],
    strategyPlan: null,
    critiqueReport: null,
    beatSheets: [],
    rebalanceDecisions: [],
    readiness: {
      canGenerateStrategy: true,
      canGenerateSkeleton: true,
      canGenerateBeatSheet: true,
      canGenerateChapterList: true,
      blockingReasons: [],
    },
    derivedOutline: "",
    derivedStructuredOutline: "",
    source: "volume",
    activeVersionId: null,
  };
}

test("buildCrossVolumeContinuityPackage builds in-memory package with DB enrichment", async () => {
  const document = makeDocument();
  const db = makeFakeDb();

  const pkg = await buildCrossVolumeContinuityPackage({
    novelId: "novel-x",
    targetVolumeSortOrder: 3,
    document,
    db,
  });

  assert.equal(pkg.targetVolumeSortOrder, 3);
  assert.equal(pkg.priorVolumeCount, 2);

  // volumeArc includes the prior volumes (1 and 2) with climax + openPayoffs.
  assert.equal(pkg.volumeArc.length, 2);
  const vol1Arc = pkg.volumeArc.find((v) => v.sortOrder === 1);
  const vol2Arc = pkg.volumeArc.find((v) => v.sortOrder === 2);
  assert.ok(vol1Arc, "volume 1 arc present");
  assert.ok(vol2Arc, "volume 2 arc present");
  assert.equal(vol1Arc.climax, "劫狱高潮");
  assert.deepEqual(vol1Arc.openPayoffs, ["令牌线索", "旧友背叛"]);
  assert.equal(vol2Arc.nextVolumeHook, "令牌认主");

  // characterStates populated from the Character model + isCurrent snapshot.
  assert.equal(pkg.characterStates.length, 1);
  assert.equal(pkg.characterStates[0].name, "林惊蛰");
  assert.equal(pkg.characterStates[0].currentState, "被困于霜狱第三层");
  assert.equal(pkg.characterStates[0].mindSnapshot, "表面顺从，暗中布局");

  // pendingPayoffs: only the book-scope ledger item (chapter-scope filtered out).
  assert.equal(pkg.pendingPayoffs.length, 1);
  assert.equal(pkg.pendingPayoffs[0].ledgerKey, "ledger-book-1");
  assert.equal(pkg.pendingPayoffs[0].scopeType, "book");
  assert.equal(pkg.pendingPayoffs[0].status, "pending_payoff");

  // worldRules present from NovelBible.
  assert.equal(pkg.worldRules, "灵气枯竭后，术法需以血为引");

  // consistencyFacts present.
  assert.equal(pkg.consistencyFacts.length, 2);
  assert.ok(pkg.consistencyFacts[0].startsWith("[plot]"));
});

test("buildCrossVolumeContinuityPackage in-memory path without db leaves enrichment empty", async () => {
  const document = makeDocument();

  const pkg = await buildCrossVolumeContinuityPackage({
    novelId: "novel-x",
    targetVolumeSortOrder: 2,
    document,
  });

  assert.equal(pkg.priorVolumeCount, 1);
  assert.equal(pkg.volumeArc.length, 1);
  assert.equal(pkg.volumeArc[0].sortOrder, 1);
  assert.equal(pkg.characterStates.length, 0);
  assert.equal(pkg.pendingPayoffs.length, 0);
  assert.equal(pkg.worldRules, null);
  assert.equal(pkg.consistencyFacts.length, 0);
});
