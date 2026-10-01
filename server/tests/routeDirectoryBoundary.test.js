const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const srcRoot = path.join(repoRoot, "src");
const routesRoot = path.join(srcRoot, "routes");

function readSource(...segments) {
  return fs.readFileSync(path.join(srcRoot, ...segments), "utf8");
}

test("app mounts migrated novel and world routers from module HTTP entrypoints", () => {
  const source = readSource("app.ts");

  for (const legacyImport of [
    './routes/novel',
    './routes/novelDirector',
    './routes/novelExport',
    './routes/novelWorkflows',
    './routes/novelDecisions',
    './routes/novelChapterSummary',
    './routes/world',
  ]) {
    assert.equal(source.includes(legacyImport), false, `app.ts must not import ${legacyImport}`);
  }

  for (const moduleImport of [
    './modules/novel/http/novel',
    './services/novel/director/http/novelDirector',
    './services/novel/director/http/novelWorkflows',
    './modules/export/http/novelExport',
    './modules/setup/world/http',
  ]) {
    assert.equal(source.includes(moduleImport), true, `app.ts must import ${moduleImport}`);
  }
});

test("workflow HTTP schema accepts every formal auto-director stage", () => {
  // After the T3-5/T3-6 route + enum consolidation the director HTTP stage
  // schema is driven by the shared canonical enum (DIRECTOR_API_STAGE_VALUES)
  // imported from @ai-novel/shared/types/novelWorkflow, not a hardcoded literal
  // list. The enum still includes "world_setup", so the HTTP surface accepts it.
  const httpSource = readSource("services", "novel", "director", "http", "novelWorkflows.ts");
  assert.equal(
    httpSource.includes("DIRECTOR_API_STAGE_VALUES"),
    true,
    "novelWorkflows.ts must derive its stage schema from the shared DIRECTOR_API_STAGE_VALUES enum",
  );

  const sharedSource = readSource("..", "..", "shared", "types", "novelWorkflow.ts");
  assert.equal(
    sharedSource.includes('"world_setup"'),
    true,
    "shared DIRECTOR_API_STAGE_VALUES must include the world_setup stage",
  );
});

test("migrated route root files do not remain as compatibility shims", () => {
  const forbiddenFiles = [
    "novel.ts",
    "novelBaseRoutes.ts",
    "novelChapterEditorRoutes.ts",
    "novelChapterGeneration.ts",
    "novelChapterRoutes.ts",
    "novelChapterSummary.ts",
    "novelCharacterDynamicsRoutes.ts",
    "novelCharacterPreparationRoutes.ts",
    "novelCharacterResourceRoutes.ts",
    "novelCharacterSyncRoutes.ts",
    "novelCharacterVisibleProfileRoutes.ts",
    "novelDecisions.ts",
    "novelDirector.ts",
    "novelExport.ts",
    "novelFramingRoutes.ts",
    "novelPlanningRoutes.ts",
    "novelProductionRoutes.ts",
    "novelReviewRoutes.ts",
    "novelSnapshotCharacterRoutes.ts",
    "novelStoryMacroRoutes.ts",
    "novelStorylineRoutes.ts",
    "novelVolumeRoutes.ts",
    "novelWorkflows.ts",
    "novelWorldSliceRoutes.ts",
    "world.ts",
  ];

  const offenders = forbiddenFiles.filter((filename) => fs.existsSync(path.join(routesRoot, filename)));
  assert.deepEqual(offenders, []);
});

test("world HTTP split keeps files below the long-route threshold", () => {
  const worldHttpRoot = path.join(srcRoot, "modules", "setup", "world", "http");
  const files = fs
    .readdirSync(worldHttpRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => path.join(worldHttpRoot, entry.name));

  const oversized = files
    .map((file) => ({
      file: path.relative(repoRoot, file),
      lines: fs.readFileSync(file, "utf8").split(/\r?\n/).length,
    }))
    .filter((entry) => entry.lines >= 600);

  assert.deepEqual(oversized, []);
});
