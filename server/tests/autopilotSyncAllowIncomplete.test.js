const test = require("node:test");
const assert = require("node:assert/strict");

const { prisma } = require("../dist/db/prisma.js");
const persistence = require("../dist/services/novel/volume/volumeWorkspacePersistence.js");
const { VolumeChapterSyncService } = require("../dist/services/novel/volume/VolumeChapterSyncService.js");

function buildWorkspace() {
  const chapter = {
    id: "volume-chapter-1",
    chapterId: "chapter-1",
    volumeId: "volume-1",
    chapterOrder: 1,
    beatKey: null,
    title: "第一章",
    summary: "章节摘要",
    purpose: null,
    exclusiveEvent: null,
    endingState: null,
    nextChapterEntryState: null,
    conflictLevel: null,
    conflictLevelSource: null,
    revealLevel: null,
    targetWordCount: null,
    mustAvoid: null,
    // Incomplete historical contract: a task-sheet fragment but no usable scene cards.
    taskSheet: "这是一段未通过质量门禁的历史任务单片段",
    sceneCards: null,
    styleContract: null,
    payoffRefs: [],
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
  };
  return {
    novelId: "novel-1",
    workspaceVersion: "v2",
    volumes: [
      {
        id: "volume-1",
        novelId: "novel-1",
        sortOrder: 1,
        title: "第一卷",
        summary: null,
        openingHook: null,
        mainPromise: null,
        primaryPressureSource: null,
        coreSellingPoint: null,
        escalationMode: null,
        protagonistChange: null,
        midVolumeRisk: null,
        climax: null,
        payoffType: null,
        nextVolumeHook: null,
        resetPoint: null,
        openPayoffs: [],
        status: "active",
        sourceVersionId: null,
        chapters: [chapter],
        createdAt: chapter.createdAt,
        updatedAt: chapter.updatedAt,
      },
    ],
    strategyPlan: null,
    critiqueReport: null,
    beatSheets: [],
    rebalanceDecisions: [],
    readiness: {
      canGenerateStrategy: true,
      canGenerateSkeleton: true,
      canGenerateChapterList: true,
      canGenerateBeatSheet: true,
      blockingReasons: [],
    },
    derivedOutline: "",
    derivedStructuredOutline: "",
    source: "volume",
    activeVersionId: "version-1",
  };
}

function mockPrismaAndPersistence() {
  const originalFindMany = prisma.chapter.findMany;
  const originalTransaction = persistence.runVolumeWorkspaceTransaction;
  const originalPersist = persistence.persistActiveVolumeWorkspace;
  const writes = [];
  prisma.chapter.findMany = async () => [
    {
      id: "chapter-1",
      order: 1,
      title: "第一章",
      content: "",
      generationState: "planned",
      chapterStatus: "unplanned",
      expectation: "旧摘要",
      targetWordCount: null,
      conflictLevel: null,
      revealLevel: null,
      mustAvoid: null,
      taskSheet: null,
      sceneCards: null,
    },
  ];
  persistence.runVolumeWorkspaceTransaction = async (callback) => callback({
    chapter: {
      updateMany: async (args) => writes.push(args),
      create: async () => {},
      deleteMany: async () => {},
    },
    storyPlan: { updateMany: async () => {} },
    volumePlanVersion: { update: async () => {} },
  });
  persistence.persistActiveVolumeWorkspace = async () => {};
  return {
    writes,
    restore() {
      prisma.chapter.findMany = originalFindMany;
      persistence.runVolumeWorkspaceTransaction = originalTransaction;
      persistence.persistActiveVolumeWorkspace = originalPersist;
    },
  };
}

test("autopilot sync allows incomplete execution contracts when flag is set", async () => {
  const workspace = buildWorkspace();
  const mocks = mockPrismaAndPersistence();
  try {
    await new VolumeChapterSyncService({
      ensureVolumeWorkspace: async () => workspace,
      ensureActiveVersionRecord: async () => ({ versionId: "version-1", version: 1 }),
      emitVolumeUpdated: () => {},
      syncPayoffLedger: () => {},
    }).syncVolumeChaptersWithOptions("novel-1", {
      volumes: workspace.volumes,
      allowIncompleteExecutionContracts: true,
    });
    assert.ok(mocks.writes.length > 0, "sync should have written the chapter plan");
  } finally {
    mocks.restore();
  }
});

test("autopilot sync still asserts incomplete execution contracts when flag is omitted", async () => {
  const workspace = buildWorkspace();
  const mocks = mockPrismaAndPersistence();
  try {
    await assert.rejects(
      async () => new VolumeChapterSyncService({
        ensureVolumeWorkspace: async () => workspace,
        ensureActiveVersionRecord: async () => ({ versionId: "version-1", version: 1 }),
        emitVolumeUpdated: () => {},
        syncPayoffLedger: () => {},
      }).syncVolumeChaptersWithOptions("novel-1", { volumes: workspace.volumes }),
      /质量门禁|执行合同/,
    );
  } finally {
    mocks.restore();
  }
});
