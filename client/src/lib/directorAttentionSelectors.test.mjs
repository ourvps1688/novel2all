import test from "node:test";
import assert from "node:assert/strict";
import {
  selectVisibleDirectorAttentions,
  selectAttentionByNovelId,
  selectContinueNovels,
} from "./directorAttentionSelectors.ts";

function attention(overrides = {}) {
  return {
    novelId: "n1",
    novelTitle: "测试小说",
    level: "idle",
    headline: "",
    detail: null,
    requiresUserAction: false,
    primaryAction: null,
    fallbackActions: [],
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

// --- selectVisibleDirectorAttentions ---
test("shows needs_recovery attentions", () => {
  const list = [attention({ novelId: "a", level: "needs_recovery" })];
  const result = selectVisibleDirectorAttentions(list, new Set());
  assert.equal(result.length, 1);
  assert.equal(result[0].novelId, "a");
});

test("shows waiting_approval attentions", () => {
  const list = [attention({ novelId: "a", level: "waiting_approval" })];
  assert.equal(selectVisibleDirectorAttentions(list, new Set()).length, 1);
});

test("hides running attentions", () => {
  const list = [attention({ novelId: "a", level: "running" })];
  assert.equal(selectVisibleDirectorAttentions(list, new Set()).length, 0);
});

test("hides auto_recovering attentions", () => {
  const list = [attention({ novelId: "a", level: "auto_recovering" })];
  assert.equal(selectVisibleDirectorAttentions(list, new Set()).length, 0);
});

test("hides idle attentions", () => {
  const list = [attention({ novelId: "a", level: "idle" })];
  assert.equal(selectVisibleDirectorAttentions(list, new Set()).length, 0);
});

test("hides dismissed novel ids even if actionable", () => {
  const list = [attention({ novelId: "a", level: "needs_recovery" })];
  assert.equal(selectVisibleDirectorAttentions(list, new Set(["a"])).length, 0);
});

test("handles null/empty input", () => {
  assert.deepEqual(selectVisibleDirectorAttentions(null, new Set()), []);
  assert.deepEqual(selectVisibleDirectorAttentions([], new Set()), []);
});

// --- selectAttentionByNovelId ---
test("builds map keyed by novelId, dropping idle", () => {
  const list = [
    attention({ novelId: "a", level: "needs_recovery" }),
    attention({ novelId: "b", level: "idle" }),
    attention({ novelId: "c", level: "waiting_approval" }),
  ];
  const map = selectAttentionByNovelId(list);
  assert.equal(map.size, 2);
  assert.ok(map.has("a"));
  assert.ok(!map.has("b"));
  assert.ok(map.has("c"));
});

test("returns empty map for empty input", () => {
  assert.equal(selectAttentionByNovelId([]).size, 0);
});

// --- selectContinueNovels ---
test("keeps only novels that have attention, capped at 3", () => {
  const novels = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }, { id: "e" }];
  const map = new Map([
    ["a", attention()],
    ["c", attention()],
    ["e", attention()],
    ["x", attention()],
  ]);
  const result = selectContinueNovels(novels, map);
  assert.deepEqual(result.map((n) => n.id), ["a", "c", "e"]);
});

test("excludes novels without attention", () => {
  const novels = [{ id: "a" }, { id: "b" }];
  const map = new Map([["a", attention()]]);
  assert.deepEqual(selectContinueNovels(novels, map).map((n) => n.id), ["a"]);
});

test("caps at first 3 novels with attention", () => {
  const novels = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
  const map = new Map(novels.map((n) => [n.id, attention()]));
  const result = selectContinueNovels(novels, map);
  assert.equal(result.length, 3);
  assert.deepEqual(result.map((n) => n.id), ["a", "b", "c"]);
});
