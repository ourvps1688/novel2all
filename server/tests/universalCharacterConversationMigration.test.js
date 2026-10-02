const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const migrationName = "20260714110000_universal_character_conversation";
const prismaRoot = path.join(__dirname, "..", "src", "prisma");

function readMigration(directory) {
  return fs.readFileSync(path.join(prismaRoot, directory, migrationName, "migration.sql"), "utf8");
}

test("universal character conversation migrations preserve legacy dialogue records", () => {
  const sqlite = readMigration("migrations.sqlite");

  assert.match(sqlite, /CharacterConversationSession/);
  assert.match(sqlite, /CharacterConversationTurn/);
  assert.match(sqlite, /conversationSessionId/);
  assert.doesNotMatch(sqlite, /DROP TABLE "CharacterDialogueSession"/);
  assert.doesNotMatch(sqlite, /DROP TABLE "CharacterDialogueTurn"/);
  assert.match(sqlite, /INSERT INTO "new_CharacterDialogueInfluence"/);
  assert.match(sqlite, /FROM "CharacterDialogueInfluence"/);
  assert.match(sqlite, /"sessionId" TEXT/);
});
