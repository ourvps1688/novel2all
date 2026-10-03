// Locks in the extend_outline narrowing fix.
//
// The fix (in novelDirectorStructuredOutlinePhase.ts) computes `extendChapterRange`
// so the volume-chapter quality gate and sync only touch the NEWLY-ADDED chapters
// (orders > pre-extend max), never re-validating historical chapters whose
// persisted execution contracts may be incomplete. This unit test exercises the
// exact pure function that feeds all four edit sites, so a regression that
// widens the range back to the whole book will fail here.
const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveExtendOutlineChapterRange } = require("../dist/services/novel/director/phases/novelDirectorStructuredOutlinePhase.js");

function buildWorkspace(orders) {
  return {
    novelId: "novel-demo",
    volumes: [
      {
        id: "volume-1",
        sortOrder: 1,
        chapters: orders.map((order) => ({
          id: `chapter-${order}`,
          chapterOrder: order,
          title: `Chapter ${order}`,
        })),
      },
    ],
  };
}

function multiVolumeWorkspace(volumeChapters) {
  return {
    novelId: "novel-demo",
    volumes: volumeChapters.map((orders, index) => ({
      id: `volume-${index + 1}`,
      sortOrder: index + 1,
      chapters: orders.map((order) => ({
        id: `chapter-${order}`,
        chapterOrder: order,
        title: `Chapter ${order}`,
      })),
    })),
  };
}

test("resolveExtendOutlineChapterRange narrows to newly-added chapters only", () => {
  // 续写前 3 章，续写后 6 章 → 新增 4-6，历史 1-3 必须被排除
  const range = resolveExtendOutlineChapterRange(
    buildWorkspace([1, 2, 3]),
    buildWorkspace([1, 2, 3, 4, 5, 6]),
  );
  assert.deepEqual(range, { startOrder: 4, endOrder: 6 });
});

test("resolveExtendOutlineChapterRange handles a fresh book (no pre-extend chapters)", () => {
  // 从空开始续写 5 章 → 1-5（历史区间为空，startOrder 从 1 起）
  const range = resolveExtendOutlineChapterRange(
    buildWorkspace([]),
    buildWorkspace([1, 2, 3, 4, 5]),
  );
  assert.deepEqual(range, { startOrder: 1, endOrder: 5 });
});

test("resolveExtendOutlineChapterRange tracks the max order across volumes", () => {
  // 续写前卷1含 1-10，续写后卷1 1-10 + 卷2 11-12 → 新增 11-12
  const range = resolveExtendOutlineChapterRange(
    multiVolumeWorkspace([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]),
    multiVolumeWorkspace([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [11, 12]]),
  );
  assert.deepEqual(range, { startOrder: 11, endOrder: 12 });
});

test("resolveExtendOutlineChapterRange is monotonically non-empty for any positive new chapter", () => {
  // 一般性质：无论历史多少章，新增章节区间 startOrder 永远 > 历史最大序
  const pre = buildWorkspace([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  const post = buildWorkspace([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  const range = resolveExtendOutlineChapterRange(pre, post);
  assert.equal(range.startOrder, 10);
  assert.equal(range.endOrder, 10);
  assert.ok(range.endOrder >= range.startOrder);
});
