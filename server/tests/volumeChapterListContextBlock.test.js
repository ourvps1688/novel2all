const test = require("node:test");
const assert = require("node:assert/strict");

const { buildVolumeChapterListContextBlocks } = require("../dist/prompting/prompts/novel/volume/contextBlocks.js");

function makeCrossVolumeContinuity() {
  return {
    targetVolumeSortOrder: 3,
    priorVolumeCount: 2,
    volumeArc: [
      {
        sortOrder: 1,
        title: "霜狱初醒",
        summary: "主角入狱",
        climax: "劫狱高潮",
        protagonistChange: "从懦弱到决绝",
        nextVolumeHook: "令牌浮现",
        resetPoint: null,
        openPayoffs: ["令牌线索"],
      },
      {
        sortOrder: 2,
        title: "血引之约",
        summary: "主角逃出",
        climax: "血祭反杀",
        protagonistChange: "学会代价",
        nextVolumeHook: "令牌认主",
        resetPoint: null,
        openPayoffs: ["令牌认主伏笔"],
      },
    ],
    characterStates: [
      { name: "林惊蛰", role: "protagonist", currentState: "被困", currentGoal: "夺回令牌" },
    ],
    pendingPayoffs: [
      { ledgerKey: "bk1", title: "令牌之谜", summary: "主人未明", scopeType: "book", status: "pending_payoff" },
    ],
    worldRules: "灵气枯竭",
    consistencyFacts: ["[plot] 主角左眼有旧伤"],
    priorChapterSummaries: [],
  };
}

function makePromptInput() {
  return {
    novel: {
      characters: [],
      title: "测试小说",
      genre: { name: "玄幻" },
    },
    workspace: {},
    storyMacroPlan: null,
    strategyPlan: null,
    targetVolume: {
      id: "vol-3",
      novelId: "novel-x",
      sortOrder: 3,
      title: "令牌归处",
      openPayoffs: [],
      chapters: [],
      status: "draft",
      createdAt: "",
      updatedAt: "",
    },
    targetBeatSheet: {
      volumeId: "vol-3",
      volumeSortOrder: 3,
      status: "active",
      beats: [],
    },
    targetBeat: {
      label: "开卷抓手",
      key: "opening",
      summary: "开篇",
      chapterSpanHint: "1-3章",
      mustDeliver: ["建立处境"],
    },
    previousBeat: null,
    nextBeat: null,
    previousVolume: undefined,
    nextVolume: undefined,
    crossVolumeContinuity: makeCrossVolumeContinuity(),
    guidance: undefined,
    targetBeatChapterCount: 3,
    targetChapterStartOrder: 1,
    targetChapterEndOrder: 3,
    nextAvailableChapterOrder: 1,
    previousBeatChapterSummary: null,
    preservedBeatChapterSummary: null,
  };
}

test("buildVolumeChapterListContextBlocks includes cross_volume_continuity block", () => {
  const blocks = buildVolumeChapterListContextBlocks(makePromptInput());
  const continuityBlock = blocks.find((block) => block.id === "cross_volume_continuity");

  assert.ok(continuityBlock, "cross_volume_continuity block should be present");
  assert.equal(continuityBlock.group, "cross_volume_continuity");
  assert.ok(continuityBlock.content.includes("霜狱初醒"), "block should render prior volume arcs");
  assert.ok(continuityBlock.content.includes("令牌之谜"), "block should render pending payoffs");
});

test("buildVolumeChapterListContextBlocks renders empty continuity when package is absent", () => {
  const input = makePromptInput();
  input.crossVolumeContinuity = undefined;

  const blocks = buildVolumeChapterListContextBlocks(input);
  const continuityBlock = blocks.find((block) => block.id === "cross_volume_continuity");

  assert.ok(continuityBlock, "block container should still be present");
  assert.equal(continuityBlock.content.trim(), "", "content should be empty when package absent");
});
