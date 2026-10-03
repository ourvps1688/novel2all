const test = require("node:test");
const assert = require("node:assert/strict");

const { buildChapterWriterContextBlocks } = require("../dist/prompting/prompts/novel/context/chapterContextBlocks.js");
const { chapterWriteContextSchema } = require("@ai-novel/shared/types/chapterRuntime");

// Build a minimal but schema-valid ChapterWriteContext. We only need enough
// fields populated so that buildChapterWriterContextBlocks (and its internal
// normalizeChapterWriteContext) renders without throwing. The cross-volume
// continuity package is injected per-case.
function makeWriteContext(crossVolumeContinuity) {
  const context = chapterWriteContextSchema.parse({
    bookContract: {
      title: "测试小说",
      genre: "玄幻",
      targetAudience: "男频",
      sellingPoint: "逆袭",
      first30ChapterPromise: "主角觉醒",
      narrativePov: "第三人称",
      pacePreference: "快",
      emotionIntensity: "高",
    },
    macroConstraints: null,
    volumeWindow: null,
    chapterMission: {
      chapterId: "c1",
      chapterOrder: 1,
      title: "第一章",
      objective: "开局",
      expectation: "建立处境",
      hookTarget: "留下悬念",
    },
    localStateSummary: "",
    openingAntiRepeatHint: "",
    participants: [],
    lengthBudget: null,
  });
  context.crossVolumeContinuity = crossVolumeContinuity;
  return context;
}

function makeNonEmptyPackage() {
  return {
    targetVolumeSortOrder: 2,
    priorVolumeCount: 1,
    volumeArc: [
      {
        sortOrder: 1,
        title: "v1",
        summary: "s",
        climax: null,
        protagonistChange: null,
        nextVolumeHook: null,
        resetPoint: null,
        openPayoffs: [],
      },
    ],
    characterStates: [],
    pendingPayoffs: [],
    worldRules: null,
    consistencyFacts: [],
    priorChapterSummaries: [],
  };
}

function makeEmptyPackage() {
  return {
    targetVolumeSortOrder: 2,
    priorVolumeCount: 0,
    volumeArc: [],
    characterStates: [],
    pendingPayoffs: [],
    worldRules: null,
    consistencyFacts: [],
    priorChapterSummaries: [],
  };
}

test("buildChapterWriterContextBlocks includes cross_volume_continuity block when package present", () => {
  const blocks = buildChapterWriterContextBlocks(makeWriteContext(makeNonEmptyPackage()), {
    mode: "full",
  });
  const block = blocks.find((item) => item && item.id === "cross_volume_continuity");

  assert.ok(block, "cross_volume_continuity block should be present");
  assert.equal(block.group, "cross_volume_continuity");
  assert.equal(block.priority, 93);
  assert.ok(block.content.trim().length > 0, "content should be non-empty");
  assert.ok(block.content.includes("v1"), "content should render prior volume arc title");
  assert.ok(block.content.includes("volume 1"), "content should reference prior volume 1");
});

test("buildChapterWriterContextBlocks omits cross_volume_continuity block when package is null", () => {
  const blocks = buildChapterWriterContextBlocks(makeWriteContext(null), {
    mode: "full",
  });
  const block = blocks.find((item) => item && item.id === "cross_volume_continuity");

  assert.equal(block, undefined, "no cross_volume_continuity block when package is null");
});

test("buildChapterWriterContextBlocks drops empty cross_volume_continuity package via empty-content filter", () => {
  const blocks = buildChapterWriterContextBlocks(makeWriteContext(makeEmptyPackage()), {
    mode: "full",
  });
  const block = blocks.find((item) => item && item.id === "cross_volume_continuity");

  assert.equal(block, undefined, "empty package yields no cross_volume_continuity block");
});
