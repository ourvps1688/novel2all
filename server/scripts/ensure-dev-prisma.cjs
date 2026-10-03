const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const rootDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(rootDir, "..");
const generatedClientPath = path.join(rootDir, "node_modules", "@prisma", "client", "index.js");
const stampPath = path.join(rootDir, ".tmp", "prisma-dev-prepare.json");
const prismaCliPath = path.join(rootDir, "node_modules", "prisma", "build", "index.js");

function normalizeDatabaseMode(rawValue) {
  const normalized = rawValue?.trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized === "sqlite" || normalized === "file") {
    return "sqlite";
  }
  return null;
}

function resolveDatabaseRuntimeConfig() {
  const normalizedDatabaseUrl = process.env.DATABASE_URL?.trim();
  const provider = "sqlite";

  return {
    provider,
    url: normalizedDatabaseUrl ?? "file:./dev.db",
    prismaSchemaPath: "src/prisma/schema.sqlite.prisma",
  };
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
}

function runPrisma(args) {
  const result = spawnSync(process.execPath, [prismaCliPath, ...args], {
    cwd: rootDir,
    stdio: "inherit",
    env: process.env,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

// 直接在当前进程内探测依赖是否可加载：原先的 spawnSync(process.execPath, ["-e", …])
// 在 Windows / Git-Bash 环境下会偶发返回 status:null（spawn 直接失败而非真正的加载错误），
// 导致 canLoad* 永远返回 false、误删可用的 better-sqlite3 原生 binding。改为 try/catch 内联
// require，既能准确反映当前 Node 下 binding 是否真的可用，也彻底规避了子进程 spawn 的坑。
function canLoadPrismaClient() {
  try {
    const client = require("@prisma/client");
    return typeof client.PrismaClient === "function";
  } catch {
    return false;
  }
}

function resolveBetterSqlite3Dir() {
  const adapterEntryPath = require.resolve("@prisma/adapter-better-sqlite3", {
    paths: [rootDir],
  });
  const adapterDir = path.dirname(adapterEntryPath);
  const betterSqlitePkgPath = require.resolve("better-sqlite3/package.json", {
    paths: [adapterDir],
  });
  return path.dirname(betterSqlitePkgPath);
}

function resolvePrebuildInstallCliPath() {
  const pnpmVirtualStoreDir = path.join(repoRoot, "node_modules", ".pnpm");
  const match = fs
    .readdirSync(pnpmVirtualStoreDir, { withFileTypes: true })
    .find((entry) => entry.isDirectory() && entry.name.startsWith("prebuild-install@"));

  if (!match) {
    throw new Error(`Unable to resolve prebuild-install under ${pnpmVirtualStoreDir}.`);
  }

  return path.join(pnpmVirtualStoreDir, match.name, "node_modules", "prebuild-install", "bin.js");
}

function canLoadBetterSqlite3Binding(betterSqlite3Dir) {
  try {
    const Database = require(betterSqlite3Dir);
    const db = new Database(":memory:");
    db.prepare("select 1 as x").get();
    db.close();
    return true;
  } catch {
    return false;
  }
}

function repairBetterSqlite3Binding(betterSqlite3Dir) {
  const prebuildInstallCliPath = resolvePrebuildInstallCliPath();
  const staleBindingCandidates = [
    path.join(betterSqlite3Dir, "build", "Release", "better_sqlite3.node"),
    path.join(betterSqlite3Dir, "build", "Debug", "better_sqlite3.node"),
  ];

  for (const candidate of staleBindingCandidates) {
    fs.rmSync(candidate, { force: true });
  }

  const result = spawnSync(process.execPath, [prebuildInstallCliPath], {
    cwd: betterSqlite3Dir,
    stdio: "inherit",
    env: process.env,
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function ensureBetterSqlite3Binding() {
  let betterSqlite3Dir;
  try {
    betterSqlite3Dir = resolveBetterSqlite3Dir();
  } catch (error) {
    console.warn("[dev-prisma] unable to resolve better-sqlite3 package.", error);
    return;
  }

  const bindingCandidates = [
    path.join(betterSqlite3Dir, "build", "Release", "better_sqlite3.node"),
    path.join(betterSqlite3Dir, "build", "Debug", "better_sqlite3.node"),
  ];
  const hasBinding = bindingCandidates.some((candidate) => fs.existsSync(candidate));
  if (hasBinding && canLoadBetterSqlite3Binding(betterSqlite3Dir)) {
    return;
  }

  console.log("[dev-prisma] better-sqlite3 binding missing or incompatible, refreshing native binary...");
  repairBetterSqlite3Binding(betterSqlite3Dir);

  if (!canLoadBetterSqlite3Binding(betterSqlite3Dir)) {
    console.error("[dev-prisma] better-sqlite3 native binding is still unhealthy after refresh.");
    process.exit(1);
  }
}

function resolveSqliteDbPath(databaseUrl) {
  const rawFilePath = databaseUrl.replace(/^file:/, "") || "dev.db";
  return path.isAbsolute(rawFilePath) ? rawFilePath : path.join(rootDir, rawFilePath);
}

function main() {
  const runtimeConfig = resolveDatabaseRuntimeConfig();
  if (runtimeConfig.provider === "sqlite") {
    ensureBetterSqlite3Binding();
  }

  const schemaPath = path.join(rootDir, runtimeConfig.prismaSchemaPath);
  const dbPath = runtimeConfig.provider === "sqlite" ? resolveSqliteDbPath(runtimeConfig.url) : null;
  const schemaStat = fs.statSync(schemaPath);
  const stamp = readJson(stampPath);
  const schemaMtimeMs = schemaStat.mtimeMs;
  const schemaChanged = !stamp
    || stamp.schemaMtimeMs !== schemaMtimeMs
    || stamp.prismaSchemaPath !== runtimeConfig.prismaSchemaPath
    || stamp.databaseProvider !== runtimeConfig.provider;
  const missingGeneratedClient = !fs.existsSync(generatedClientPath) || !canLoadPrismaClient();
  const missingDb = dbPath ? !fs.existsSync(dbPath) : false;

  if (!schemaChanged && !missingGeneratedClient && !missingDb) {
    console.log("[dev-prisma] schema unchanged, skipping prisma generate/push.");
    return;
  }

  if (schemaChanged || missingGeneratedClient) {
    console.log("[dev-prisma] running prisma generate...");
    runPrisma(["generate", "--schema", runtimeConfig.prismaSchemaPath]);
  }

  if (schemaChanged || missingDb) {
    console.log("[dev-prisma] running prisma push...");
    runPrisma(["db", "push", "--schema", runtimeConfig.prismaSchemaPath]);
  }

  fs.mkdirSync(path.dirname(stampPath), { recursive: true });
  fs.writeFileSync(
    stampPath,
    `${JSON.stringify(
      {
        schemaMtimeMs,
        prismaSchemaPath: runtimeConfig.prismaSchemaPath,
        databaseProvider: runtimeConfig.provider,
      },
      null,
      2,
    )}\n`,
    "utf8",
  );
}

main();
