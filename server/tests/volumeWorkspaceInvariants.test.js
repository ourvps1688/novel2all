const test = require("node:test");
const assert = require("node:assert/strict");

const {
  assertVolumeWorkspaceDocumentInvariants,
} = require("../dist/services/novel/volume/volumeWorkspacePersistence.js");

function buildDocument(volumes) {
  return { volumes };
}

test("guard accepts a normalized volume workspace document", () => {
  const document = buildDocument([
    {
      id: "v1",
      sortOrder: 1,
      chapters: [
        { id: "c1", volumeId: "v1", chapterOrder: 1 },
        { id: "c2", volumeId: "v1", chapterOrder: 2 },
      ],
    },
    {
      id: "v2",
      sortOrder: 2,
      chapters: [
        { id: "c3", volumeId: "v2", chapterOrder: 3 },
        { id: "c4", volumeId: "v2", chapterOrder: 4 },
      ],
    },
  ]);
  assert.doesNotThrow(() => assertVolumeWorkspaceDocumentInvariants("novel-1", document));
});

test("guard throws a localized error on duplicate (volumeId, chapterOrder) within a volume", () => {
  const document = buildDocument([
    {
      id: "v1",
      sortOrder: 1,
      chapters: [
        { id: "c1", volumeId: "v1", chapterOrder: 1 },
        { id: "c2", volumeId: "v1", chapterOrder: 1 },
      ],
    },
  ]);
  assert.throws(
    () => assertVolumeWorkspaceDocumentInvariants("novel-1", document),
    /卷工作台文档不变量校验失败/,
  );
});

test("guard throws a localized error on duplicate (novelId, sortOrder) across volumes", () => {
  const document = buildDocument([
    {
      id: "v1",
      sortOrder: 1,
      chapters: [{ id: "c1", volumeId: "v1", chapterOrder: 1 }],
    },
    {
      id: "v2",
      sortOrder: 1,
      chapters: [{ id: "c3", volumeId: "v2", chapterOrder: 3 }],
    },
  ]);
  assert.throws(
    () => assertVolumeWorkspaceDocumentInvariants("novel-1", document),
    /卷工作台文档不变量校验失败/,
  );
});

test("guard reports the conflicting values in the error message", () => {
  const document = buildDocument([
    {
      id: "v1",
      sortOrder: 1,
      chapters: [
        { id: "c1", volumeId: "v1", chapterOrder: 5 },
        { id: "c2", volumeId: "v1", chapterOrder: 5 },
      ],
    },
  ]);
  let caught;
  try {
    assertVolumeWorkspaceDocumentInvariants("novel-42", document);
  } catch (error) {
    caught = error;
  }
  assert.ok(caught);
  assert.match(caught.message, /novel-42/);
  assert.match(caught.message, /volumeId=v1/);
  assert.match(caught.message, /chapterOrder=5/);
});
