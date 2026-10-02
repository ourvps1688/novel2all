const test = require("node:test");
const assert = require("node:assert/strict");

const {
  normalizeVolumeDraftInput,
} = require("../dist/services/novel/volume/volumePlanUtils.js");

// Regression guard for the volume-workspace "duplicate chapter slot" bug.
//
// hydrateCanonicalChapterFields / mirrorChapterIntoWorkspace rewrite each plan
// chapter's chapterOrder from the canonical Chapter table; when a stale
// chapterId falls back to an order already owned by another plan chapter (or a
// chapterId/order double-match collapses two chapters), the in-memory document
// briefly carries a duplicate (volumeId, chapterOrder) slot. Both paths now
// re-run normalizeVolumeDraftInput before persisting, so this normalizer must
// deterministically de-duplicate colliding orders while preserving ids.

test("normalizeVolumeDraftInput resolves colliding chapterOrder within a volume", () => {
  const volumes = normalizeVolumeDraftInput("novel-1", [
    {
      id: "v1",
      sortOrder: 1,
      title: "第一卷",
      summary: "s",
      chapters: [
        // Two chapters resolved onto the same canonical order=8 by hydration.
        { id: "c1", chapterId: "real-a", chapterOrder: 7, title: "第七章", summary: "s" },
        { id: "c2", chapterId: "real-b", chapterOrder: 8, title: "第八章", summary: "s" },
        { id: "c3", chapterId: "stale-c", chapterOrder: 8, title: "另一个第八章", summary: "s" },
      ],
    },
  ]);

  const orders = volumes[0].chapters.map((chapter) => chapter.chapterOrder);
  assert.deepEqual(orders, [7, 8, 9]);
  // ids preserved, not regenerated
  const ids = volumes[0].chapters.map((chapter) => chapter.id);
  assert.deepEqual(ids, ["c1", "c2", "c3"]);
});

test("normalizeVolumeDraftInput enforces globally-unique chapterOrder across volumes", () => {
  const volumes = normalizeVolumeDraftInput("novel-1", [
    {
      id: "v1",
      sortOrder: 1,
      title: "第一卷",
      summary: "s",
      chapters: [
        { id: "c1", chapterOrder: 8, title: "A", summary: "s" },
      ],
    },
    {
      id: "v2",
      sortOrder: 2,
      title: "第二卷",
      summary: "s",
      chapters: [
        { id: "c2", chapterOrder: 8, title: "B", summary: "s" },
      ],
    },
  ]);

  const allOrders = volumes.flatMap((volume) => volume.chapters.map((chapter) => chapter.chapterOrder));
  assert.equal(new Set(allOrders).size, allOrders.length, "chapterOrder must be globally unique");
});

test("normalizeVolumeDraftInput keeps an already-unique document intact", () => {
  const input = [
    {
      id: "v1",
      sortOrder: 1,
      title: "第一卷",
      summary: "s",
      chapters: [
        { id: "c1", chapterOrder: 1, title: "A", summary: "s" },
        { id: "c2", chapterOrder: 2, title: "B", summary: "s" },
      ],
    },
  ];
  const volumes = normalizeVolumeDraftInput("novel-1", input);
  assert.deepEqual(volumes[0].chapters.map((c) => c.chapterOrder), [1, 2]);
  assert.deepEqual(volumes[0].chapters.map((c) => c.id), ["c1", "c2"]);
});
