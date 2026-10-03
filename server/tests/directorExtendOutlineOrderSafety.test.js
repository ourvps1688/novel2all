/**
 * 续写（extend）数据安全性单元测试。
 *
 * 目标：验证「确认并继续」在卷规划耗尽、卡在确认循环的场景下，真正在【最后卷】内
 * 追加新章节规划时，严格遵守 PR #50 的 @unique 约束：
 *   - VolumeChapterPlan @@unique([volumeId, chapterOrder])
 *   - Chapter           @@unique([novelId, order])
 *
 * 本测试使用一个与本项目真实小说同构的工作台文档作为 fixtures：
 *   - 更早的卷承载 1–81 章；
 *   - 最后卷（sortOrder 最大）承载真实的 82–89 章。
 *
 * 断言：
 *   (a) 续写后，最后卷原有的 82–89 章（id / chapterOrder / title / summary / beatKey / volumeId）
 *       必须原样保留，不得被重排或改写；
 *   (b) 新增章节的 chapterOrder 从 90 起连续递增，全部 >= 90，且在全卷范围内全局唯一；
 *   (c) 结果文档通过 assertVolumeWorkspaceDocumentInvariants（无重复 (volumeId, chapterOrder)、
 *       无重复 sortOrder）。
 *
 * 该测试只调用纯函数（planExtendedVolumeDocument / computeExtendNextOrder），不触碰数据库或 LLM。
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  planExtendedVolumeDocument,
  computeExtendNextOrder,
} = require("../dist/services/novel/volume/volumeExtendPlanning.js");
const {
  assertVolumeWorkspaceDocumentInvariants,
} = require("../dist/services/novel/volume/volumeWorkspacePersistence.js");
const {
  buildVolumeWorkspaceDocument,
} = require("../dist/services/novel/volume/volumeWorkspaceDocument.js");

const NOVEL_ID = "test-novel-extend-order-safety";

// 构造与「本项目真实小说」同构的原始卷数据：最后卷承载 82–89 章。
function buildRawVolumes() {
  const makeVolume = (id, sortOrder, startOrder, endOrder) => ({
    id,
    sortOrder,
    title: `卷${sortOrder}`,
    summary: null,
    status: "active",
    openPayoffs: [],
    chapters: Array.from({ length: endOrder - startOrder + 1 }, (_, i) => {
      const order = startOrder + i;
      return {
        id: `ch-${order}`,
        chapterOrder: order,
        title: `第${order}章`,
        summary: `summary-${order}`,
        beatKey: `existing-beat-${order}`,
        payoffRefs: [],
      };
    }),
  });
  return [
    makeVolume("vol-1", 1, 1, 40),
    makeVolume("vol-2", 2, 41, 81),
    makeVolume("vol-3", 3, 82, 89),
  ];
}

function buildStrategyPlan() {
  const volume = (sortOrder) => ({
    sortOrder,
    planningMode: "hard",
    roleLabel: `定位${sortOrder}`,
    coreReward: "读者回报",
    escalationFocus: "升级焦点",
    uncertaintyLevel: "medium",
  });
  return {
    recommendedVolumeCount: 3,
    hardPlannedVolumeCount: 3,
    readerRewardLadder: "读者回报梯度",
    escalationLadder: "升级梯度",
    midpointShift: "中盘转向",
    notes: "卷战略备注",
    volumes: [volume(1), volume(2), volume(3)],
    uncertainties: [],
  };
}

// 通过 buildVolumeWorkspaceDocument 归一化，完全复刻 generateExtend 的入参构造方式。
function buildBaseDocument() {
  return buildVolumeWorkspaceDocument({
    novelId: NOVEL_ID,
    volumes: buildRawVolumes(),
    strategyPlan: buildStrategyPlan(),
    beatSheets: [
      {
        volumeId: "vol-3",
        volumeSortOrder: 3,
        status: "generated",
        beats: [
          {
            key: "climax",
            label: "高潮",
            title: "终局收束",
            summary: "原有高潮段",
            chapterSpanHint: "88-89",
            mustDeliver: ["收束主线伏笔"],
          },
        ],
      },
    ],
    source: "volume",
    activeVersionId: null,
  });
}

// 续写节奏段（与 generateExtend 生成的续写段同构：使用 extend-${i} 唯一 key）。
const newBeats = [
  {
    key: "extend-0",
    label: "续写段0",
    title: "续写段0",
    summary: "承接第 89 章之后的主线推进。",
    chapterSpanHint: "1-3",
    mustDeliver: ["继续当前主线"],
  },
  {
    key: "extend-1",
    label: "续写段1",
    title: "续写段1",
    summary: "把续写主线推到合理自然落点。",
    chapterSpanHint: "1-2",
    mustDeliver: ["收束续写线"],
  },
];

// 续写段对应的章节块（与 generateExtend 调用 generateBeatChapterBlock 得到的结构一致）。
const generatedBlocks = [
  {
    beatKey: "extend-0",
    beatLabel: "续写段0",
    chapterCount: 3,
    chapters: [
      { beatKey: "extend-0", title: "第90章", summary: "续写章节 90" },
      { beatKey: "extend-0", title: "第91章", summary: "续写章节 91" },
      { beatKey: "extend-0", title: "第92章", summary: "续写章节 92" },
    ],
  },
  {
    beatKey: "extend-1",
    beatLabel: "续写段1",
    chapterCount: 2,
    chapters: [
      { beatKey: "extend-1", title: "第93章", summary: "续写章节 93" },
      { beatKey: "extend-1", title: "第94章", summary: "续写章节 94" },
    ],
  },
];

function getLastVolume(document) {
  return [...document.volumes].sort((left, right) => right.sortOrder - left.sortOrder)[0];
}

test("computeExtendNextOrder 返回 max(chapterOrder) + 1（本项目为 90）", () => {
  const document = buildBaseDocument();
  assert.equal(computeExtendNextOrder(document), 90);
});

test("续写后原有 82–89 章保持不变，新增章节 >= 90 且全局唯一，文档满足 @unique 不变量", () => {
  const baseDocument = buildBaseDocument();

  // 记录续写前最后卷（82–89 章）的关键字段。
  const lastVolumeBefore = getLastVolume(baseDocument);
  const originalChapters = lastVolumeBefore.chapters.map((chapter) => ({ ...chapter }));

  const result = planExtendedVolumeDocument({
    baseDocument,
    newBeats,
    generatedBlocks,
  });

  const lastVolumeAfter = getLastVolume(result);

  // (a) 原有 82–89 章必须原样保留（id / chapterOrder / title / summary / beatKey / volumeId 不变）。
  assert.equal(
    lastVolumeAfter.chapters.length,
    originalChapters.length + 5,
    "最后卷章节数应为 原有(8) + 新增(5)",
  );
  for (const original of originalChapters) {
    const found = lastVolumeAfter.chapters.find((chapter) => chapter.id === original.id);
    assert.ok(found, `原有章节 ${original.id} 应仍存在`);
    assert.equal(found.chapterOrder, original.chapterOrder, `章节 ${original.id} 的 chapterOrder 不应改变`);
    assert.equal(found.title, original.title, `章节 ${original.id} 的 title 不应改变`);
    assert.equal(found.summary, original.summary, `章节 ${original.id} 的 summary 不应改变`);
    assert.equal(found.beatKey, original.beatKey, `章节 ${original.id} 的 beatKey 不应改变`);
    assert.equal(found.volumeId, lastVolumeAfter.id, `章节 ${original.id} 的 volumeId 不应改变`);
  }

  // (b) 新增章节 chapterOrder 从 90 起、全部 >= 90，且在全卷范围内全局唯一。
  const allChapterOrders = result.volumes.flatMap((volume) => volume.chapters.map((chapter) => chapter.chapterOrder));
  const totalChapters = result.volumes.reduce((sum, volume) => sum + volume.chapters.length, 0);

  assert.equal(
    new Set(allChapterOrders).size,
    allChapterOrders.length,
    "所有章节 chapterOrder 应全局唯一（含跨卷）",
  );
  assert.equal(allChapterOrders.length, totalChapters, "不应有任何章节丢失");

  const newChapters = result.volumes
    .flatMap((volume) => volume.chapters)
    .filter((chapter) => chapter.chapterOrder >= 90);
  assert.ok(newChapters.length >= 1, "应至少追加一章");
  for (const chapter of newChapters) {
    assert.ok(chapter.chapterOrder >= 90, `新增章节 ${chapter.id} 的 chapterOrder 应 >= 90`);
    assert.equal(chapter.volumeId, lastVolumeAfter.id, `新增章节 ${chapter.id} 应归属最后卷`);
    assert.ok(
      chapter.beatKey === "extend-0" || chapter.beatKey === "extend-1",
      `新增章节 ${chapter.id} 应归属续写段`,
    );
  }

  // 续写起点必须为 90，且新增段连续递增到 94。
  const newOrders = newChapters.map((chapter) => chapter.chapterOrder).sort((a, b) => a - b);
  assert.deepEqual(newOrders, [90, 91, 92, 93, 94], "新增章节序号应为 90–94 连续");

  // 原有最大序号 89 必须仍然保留且不被覆盖。
  assert.ok(allChapterOrders.includes(89), "原有最大序号 89 应保留");
  assert.ok(!allChapterOrders.includes(95), "不应生成超过 94 的章节");

  // (c) 文档满足 @unique 不变量（无重复 (volumeId, chapterOrder)、无重复 sortOrder）。
  assert.doesNotThrow(() => assertVolumeWorkspaceDocumentInvariants(NOVEL_ID, result));
});

test("续写不新建卷：卷数量与卷 id 保持不变", () => {
  const baseDocument = buildBaseDocument();
  const beforeVolumeIds = baseDocument.volumes.map((volume) => volume.id).sort();
  const beforeVolumeCount = baseDocument.volumes.length;

  const result = planExtendedVolumeDocument({ baseDocument, newBeats, generatedBlocks });

  const afterVolumeIds = result.volumes.map((volume) => volume.id).sort();
  assert.equal(result.volumes.length, beforeVolumeCount, "卷数量不应变化");
  assert.deepEqual(afterVolumeIds, beforeVolumeIds, "卷 id 集合不应变化（不新建卷）");
});

test("空续写块应被安全跳过，不产生任何新增章节", () => {
  const baseDocument = buildBaseDocument();
  const beforeTotal = baseDocument.volumes.reduce((sum, volume) => sum + volume.chapters.length, 0);

  const result = planExtendedVolumeDocument({
    baseDocument,
    newBeats: [],
    generatedBlocks: [],
  });

  const afterTotal = result.volumes.reduce((sum, volume) => sum + volume.chapters.length, 0);
  assert.equal(afterTotal, beforeTotal, "空续写块不应改变章节总数");
  assert.doesNotThrow(() => assertVolumeWorkspaceDocumentInvariants(NOVEL_ID, result));
});
