import { resolveAppRuntimeMode } from "../runtime/appPaths";

export type DatabaseProvider = "sqlite";

const DEFAULT_SQLITE_DATABASE_URL = "file:./dev.db";
const SQLITE_PRISMA_SCHEMA_PATH = "src/prisma/schema.sqlite.prisma";
const SQLITE_PRISMA_MIGRATIONS_PATH = "src/prisma/migrations.sqlite";

function normalizeDatabaseMode(rawValue: string | undefined): DatabaseProvider | null {
  const normalized = rawValue?.trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized === "sqlite" || normalized === "file") {
    return "sqlite";
  }
  return null;
}

export function normalizeDatabaseUrl(rawValue: string | undefined): string {
  const normalized = rawValue?.trim();
  if (!normalized) {
    return DEFAULT_SQLITE_DATABASE_URL;
  }
  if (normalized.startsWith("file:")) {
    return normalized;
  }
  return normalized;
}

export function getDatabaseUrl(options?: { allowDefault?: boolean; preferSqlite?: boolean }): string {
  const normalized = process.env.DATABASE_URL?.trim();
  if (normalized) {
    if (normalized.startsWith("postgres")) {
      throw new Error(
        "PostgreSQL is no longer supported. Set DATABASE_URL to a SQLite file: URL (e.g. file:./dev.db).",
      );
    }
    return normalizeDatabaseUrl(normalized);
  }
  const allowDefault =
    options?.allowDefault ??
    (process.env.NODE_ENV !== "production" || resolveAppRuntimeMode() === "desktop");
  if (allowDefault) {
    return DEFAULT_SQLITE_DATABASE_URL;
  }
  throw new Error("DATABASE_URL is required in production.");
}

export interface DatabaseRuntimeConfig {
  provider: DatabaseProvider;
  url: string;
  prismaSchemaPath: string;
  prismaMigrationsPath: string;
}

export function resolveDatabaseRuntimeConfig(options?: {
  allowDefault?: boolean;
  preferSqlite?: boolean;
}): DatabaseRuntimeConfig {
  const url = getDatabaseUrl(options);
  return {
    provider: "sqlite",
    url,
    prismaSchemaPath: SQLITE_PRISMA_SCHEMA_PATH,
    prismaMigrationsPath: SQLITE_PRISMA_MIGRATIONS_PATH,
  };
}

const DEFAULT_DATABASE_URL = DEFAULT_SQLITE_DATABASE_URL;

export {
  DEFAULT_DATABASE_URL,
  DEFAULT_SQLITE_DATABASE_URL,
  SQLITE_PRISMA_SCHEMA_PATH,
  SQLITE_PRISMA_MIGRATIONS_PATH,
};
