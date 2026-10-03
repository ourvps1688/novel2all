const test = require("node:test");
const assert = require("node:assert/strict");

const { generateWholeBookPlan } = require("../dist/services/novel/volume/volumeGenerationOrchestrator.js");

const NOVEL_ID = "novel-whole-book-1";

function createChapter(id, order, title, beatKey) {
  return {
    id,
    volumeId: id.split("-").slice(0, 2).join("-"),
    chapterOrder: order,
    beatKey,
    title,
    summary: `${title} summary`,
    purpose: null,
    exclusiveEvent: null,
    endingState: null,
    nextChapterEntryState: null,
    conflictLevel: null,
    conflictLevelSource: null,
    revealLevel: null,
    targetWordCount: null,
    mustAvoid: null,
    taskSheet: null,
    sceneCards: null,
    payoffRefs: [],
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
  };
}

function createSkeletonVolume(id, sortOrder) {
  return {
    id,
    novelId: NOVEL_ID,
    sortOrder,
    title: `Volume ${sortOrder}`,
    summary: "",
    openingHook: "",
    mainPromise: "",
    primaryPressureSource: "",
    coreSellingPoint: "",
    escalationMode: "",
    protagonistChange: "",
    midVolumeRisk: "",
    climax: "",
    payoffType: "",
    nextVolumeHook: "",
    resetPoint: "",
    openPayoffs: [],
    status: "draft",
    sourceVersionId: null,
    chapters: [],
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
  };
}

function createWorkspace() {
  return {
    novelId: NOVEL_ID,
    workspaceVersion: "v2",
    volumes: [createSkeletonVolume("volume-1", 1), createSkeletonVolume("volume-2", 2)],
    strategyPlan: {
      recommendedVolumeCount: 2,
      centralPromise: "test",
      volumeArcs: [],
      pacing: {},
    },
    critiqueReport: null,
    beatSheets: [],
    rebalanceDecisions: [],
    source: "volume",
    activeVersionId: null,
  };
}

// Records every injected generator call so the test can assert coverage.
function makeStubs(novelId) {
  const beatSheetCalls = [];
  const chapterListCalls = [];

  const generateBeatSheet = async (params) => {
    const { document, options } = params;
    beatSheetCalls.push({
      novelId,
      targetVolumeId: options.targetVolumeId,
      scope: options.scope,
    });
    const volumeId = options.targetVolumeId;
    const sortOrder = document.volumes.find((v) => v.id === volumeId)?.sortOrder ?? 0;
    const beats = [
      { key: "b1", label: "Beat 1", summary: "b1", chapterSpanHint: "1-2章", mustDeliver: [] },
      { key: "b2", label: "Beat 2", summary: "b2", chapterSpanHint: "3-4章", mustDeliver: [] },
    ];
    const beatSheets = [
      ...document.beatSheets.filter((sheet) => sheet.volumeId !== volumeId),
      { volumeId, volumeSortOrder: sortOrder, status: "generated", beats },
    ];
    return { ...document, beatSheets };
  };

  const generateChapterList = async (params) => {
    const { document, options } = params;
    chapterListCalls.push({
      novelId,
      targetVolumeId: options.targetVolumeId,
      scope: options.scope,
      targetBeatKey: options.targetBeatKey,
    });
    const volumeId = options.targetVolumeId;
    const beatKey = options.targetBeatKey;
    const volumes = document.volumes.map((v) => {
      if (v.id !== volumeId) {
        return v;
      }
      const order = v.chapters.length + 1;
      const chapter = createChapter(`${volumeId}-${beatKey}-${order}`, order, `Chapter ${order} (${beatKey})`, beatKey);
      chapter.volumeId = volumeId;
      return { ...v, chapters: [...v.chapters, chapter] };
    });
    return { ...document, volumes };
  };

  return { beatSheetCalls, chapterListCalls, generateBeatSheet, generateChapterList };
}

// Minimal injected context so the function skips the database load.
const DUMMY_NOVEL = { title: "n", completionProfile: {}, storyModePromptBlock: null };
const DUMMY_STORY_MACRO = null;

test("generateWholeBookPlan plans beat sheets + chapter lists for every volume", async () => {
  const workspace = createWorkspace();
  const { beatSheetCalls, chapterListCalls, generateBeatSheet, generateChapterList } = makeStubs(NOVEL_ID);

  const result = await generateWholeBookPlan({
    novelId: NOVEL_ID,
    workspace,
    options: { scope: "book" },
    storyMacroPlanService: { getPlan: async () => null },
    generateBeatSheet,
    generateChapterList,
    novel: DUMMY_NOVEL,
    storyMacroPlan: DUMMY_STORY_MACRO,
  });

  // Both volumes must have a beat sheet.
  assert.equal(result.beatSheets.length, 2, "expected a beat sheet for both volumes");
  for (const volume of result.volumes) {
    const sheet = result.beatSheets.find((s) => s.volumeId === volume.id);
    assert.ok(sheet, `expected beat sheet for volume ${volume.id}`);
    assert.equal(sheet.beats.length, 2, `expected 2 beats for volume ${volume.id}`);
  }

  // Both volumes must have their chapters populated (one chapter per beat).
  for (const volume of result.volumes) {
    assert.equal(volume.chapters.length, 2, `expected 2 chapters for volume ${volume.id}`);
  }

  // Coverage assertions: every volume covered by a beat_sheet call, every beat covered
  // by a chapter_list call.
  const beatSheetVolumeIds = beatSheetCalls.map((c) => c.targetVolumeId).sort();
  assert.deepEqual(
    beatSheetVolumeIds,
    ["volume-1", "volume-2"],
    "every volume should have exactly one beat_sheet call",
  );

  const chapterListVolumeBeatKeys = chapterListCalls.map((c) => `${c.targetVolumeId}:${c.targetBeatKey}`).sort();
  assert.deepEqual(
    chapterListVolumeBeatKeys,
    [
      "volume-1:b1",
      "volume-1:b2",
      "volume-2:b1",
      "volume-2:b2",
    ],
    "every beat of every volume should have a chapter_list call",
  );
  assert.equal(chapterListCalls.length, 4, "expected 4 chapter_list calls (2 beats x 2 volumes)");
});

test("generateWholeBookPlan throws a clear error when strategy is missing (readiness guard)", async () => {
  const workspace = createWorkspace();
  delete workspace.strategyPlan;
  const { generateBeatSheet, generateChapterList } = makeStubs(NOVEL_ID);

  await assert.rejects(
    () => generateWholeBookPlan({
      novelId: NOVEL_ID,
      workspace,
      options: { scope: "book" },
      storyMacroPlanService: { getPlan: async () => null },
      generateBeatSheet,
      generateChapterList,
      novel: DUMMY_NOVEL,
      storyMacroPlan: DUMMY_STORY_MACRO,
    }),
    /strategy.*skeleton|book scope requires/i,
    "expected a clear readiness error",
  );
});

test("generateWholeBookPlan throws a clear error when there are no volumes", async () => {
  const workspace = createWorkspace();
  workspace.volumes = [];
  const { generateBeatSheet, generateChapterList } = makeStubs(NOVEL_ID);

  await assert.rejects(
    () => generateWholeBookPlan({
      novelId: NOVEL_ID,
      workspace,
      options: { scope: "book" },
      storyMacroPlanService: { getPlan: async () => null },
      generateBeatSheet,
      generateChapterList,
      novel: DUMMY_NOVEL,
      storyMacroPlan: DUMMY_STORY_MACRO,
    }),
    /book scope requires/i,
    "expected a clear readiness error for empty volumes",
  );
});
