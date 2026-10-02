const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const databaseConfigPath = path.join(__dirname, "../dist/config/database.js");

function loadDatabaseConfig() {
  delete require.cache[databaseConfigPath];
  return require(databaseConfigPath);
}

test("normalizeDatabaseUrl returns the default SQLite URL for empty input", () => {
  const { normalizeDatabaseUrl, DEFAULT_SQLITE_DATABASE_URL } = loadDatabaseConfig();

  assert.equal(normalizeDatabaseUrl(""), DEFAULT_SQLITE_DATABASE_URL);
  assert.equal(normalizeDatabaseUrl(undefined), DEFAULT_SQLITE_DATABASE_URL);
});

test("normalizeDatabaseUrl trims and passthroughs SQLite file: URLs", () => {
  const { normalizeDatabaseUrl } = loadDatabaseConfig();

  assert.equal(
    normalizeDatabaseUrl("  file:./custom.db  "),
    "file:./custom.db",
  );
  assert.equal(
    normalizeDatabaseUrl("file:./other.db"),
    "file:./other.db",
  );
});

test("getDatabaseUrl defaults to sqlite when DATABASE_URL is unset outside production", () => {
  const originalDatabaseUrl = process.env.DATABASE_URL;
  const originalNodeEnv = process.env.NODE_ENV;
  const originalRuntime = process.env.AI_NOVEL_RUNTIME;
  const originalMode = process.env.AI_NOVEL_DATABASE_MODE;
  delete process.env.DATABASE_URL;
  delete process.env.NODE_ENV;
  delete process.env.AI_NOVEL_RUNTIME;
  delete process.env.AI_NOVEL_DATABASE_MODE;

  try {
    const {
      DEFAULT_DATABASE_URL,
      DEFAULT_SQLITE_DATABASE_URL,
      getDatabaseUrl,
      resolveDatabaseRuntimeConfig,
    } = loadDatabaseConfig();
    const config = resolveDatabaseRuntimeConfig();

    assert.equal(DEFAULT_DATABASE_URL, DEFAULT_SQLITE_DATABASE_URL);
    assert.equal(getDatabaseUrl(), DEFAULT_SQLITE_DATABASE_URL);
    assert.equal(config.provider, "sqlite");
    assert.equal(config.url, DEFAULT_SQLITE_DATABASE_URL);
    assert.equal(config.prismaSchemaPath, "src/prisma/schema.sqlite.prisma");
    assert.equal(config.prismaMigrationsPath, "src/prisma/migrations.sqlite");
  } finally {
    if (originalDatabaseUrl === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = originalDatabaseUrl;
    }
    if (originalNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = originalNodeEnv;
    }
    if (originalRuntime === undefined) {
      delete process.env.AI_NOVEL_RUNTIME;
    } else {
      process.env.AI_NOVEL_RUNTIME = originalRuntime;
    }
    if (originalMode === undefined) {
      delete process.env.AI_NOVEL_DATABASE_MODE;
    } else {
      process.env.AI_NOVEL_DATABASE_MODE = originalMode;
    }
  }
});

test("getDatabaseUrl rejects missing DATABASE_URL in production", () => {
  const originalDatabaseUrl = process.env.DATABASE_URL;
  const originalNodeEnv = process.env.NODE_ENV;
  delete process.env.DATABASE_URL;
  process.env.NODE_ENV = "production";

  try {
    const { getDatabaseUrl } = loadDatabaseConfig();
    assert.throws(() => getDatabaseUrl(), /DATABASE_URL is required in production/);
  } finally {
    if (originalDatabaseUrl === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = originalDatabaseUrl;
    }
    if (originalNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = originalNodeEnv;
    }
  }
});

test("getDatabaseUrl allows the default sqlite URL in production when running as the desktop app", () => {
  const originalDatabaseUrl = process.env.DATABASE_URL;
  const originalNodeEnv = process.env.NODE_ENV;
  const originalRuntime = process.env.AI_NOVEL_RUNTIME;
  delete process.env.DATABASE_URL;
  process.env.NODE_ENV = "production";
  process.env.AI_NOVEL_RUNTIME = "desktop";

  try {
    const { getDatabaseUrl, DEFAULT_SQLITE_DATABASE_URL } = loadDatabaseConfig();
    assert.equal(getDatabaseUrl(), DEFAULT_SQLITE_DATABASE_URL);
  } finally {
    if (originalDatabaseUrl === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = originalDatabaseUrl;
    }
    if (originalNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = originalNodeEnv;
    }
    if (originalRuntime === undefined) {
      delete process.env.AI_NOVEL_RUNTIME;
    } else {
      process.env.AI_NOVEL_RUNTIME = originalRuntime;
    }
  }
});

test("getDatabaseUrl can prefer the sqlite default for legacy local runtime", () => {
  const originalDatabaseUrl = process.env.DATABASE_URL;
  const originalNodeEnv = process.env.NODE_ENV;
  delete process.env.DATABASE_URL;
  delete process.env.NODE_ENV;

  try {
    const { getDatabaseUrl, DEFAULT_SQLITE_DATABASE_URL } = loadDatabaseConfig();
    assert.equal(getDatabaseUrl({ preferSqlite: true }), DEFAULT_SQLITE_DATABASE_URL);
  } finally {
    if (originalDatabaseUrl === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = originalDatabaseUrl;
    }
    if (originalNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = originalNodeEnv;
    }
  }
});

test("resolveDatabaseRuntimeConfig selects sqlite schema for desktop legacy mode", () => {
  const originalDatabaseUrl = process.env.DATABASE_URL;
  const originalNodeEnv = process.env.NODE_ENV;
  const originalRuntime = process.env.AI_NOVEL_RUNTIME;
  const originalMode = process.env.AI_NOVEL_DATABASE_MODE;
  delete process.env.DATABASE_URL;
  delete process.env.NODE_ENV;
  process.env.AI_NOVEL_RUNTIME = "desktop";
  delete process.env.AI_NOVEL_DATABASE_MODE;

  try {
    const {
      DEFAULT_SQLITE_DATABASE_URL,
      resolveDatabaseRuntimeConfig,
    } = loadDatabaseConfig();
    const config = resolveDatabaseRuntimeConfig();

    assert.equal(config.provider, "sqlite");
    assert.equal(config.url, DEFAULT_SQLITE_DATABASE_URL);
    assert.equal(config.prismaSchemaPath, "src/prisma/schema.sqlite.prisma");
    assert.equal(config.prismaMigrationsPath, "src/prisma/migrations.sqlite");
  } finally {
    if (originalDatabaseUrl === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = originalDatabaseUrl;
    }
    if (originalNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = originalNodeEnv;
    }
    if (originalRuntime === undefined) {
      delete process.env.AI_NOVEL_RUNTIME;
    } else {
      process.env.AI_NOVEL_RUNTIME = originalRuntime;
    }
    if (originalMode === undefined) {
      delete process.env.AI_NOVEL_DATABASE_MODE;
    } else {
      process.env.AI_NOVEL_DATABASE_MODE = originalMode;
    }
  }
});

test("getDatabaseUrl rejects postgres URLs now that only SQLite is supported", () => {
  const originalDatabaseUrl = process.env.DATABASE_URL;
  process.env.DATABASE_URL = "postgresql://writer:pass@db.internal:5432/ai_novel";

  try {
    const { getDatabaseUrl } = loadDatabaseConfig();
    assert.throws(
      () => getDatabaseUrl(),
      /PostgreSQL|postgres/i,
    );
  } finally {
    if (originalDatabaseUrl === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = originalDatabaseUrl;
    }
  }
});
