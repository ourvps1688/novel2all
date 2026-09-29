import fs from "node:fs";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

interface ClientPackageJson {
  version?: unknown;
}

function clearStaleOptimizeCache(rootDir: string): void {
  const cacheDir = path.resolve(rootDir, "node_modules/.vite");
  const depsDir = path.join(cacheDir, "deps");
  const metadataPath = path.join(depsDir, "_metadata.json");
  if (!fs.existsSync(metadataPath)) {
    return;
  }

  try {
    const rawMetadata = fs.readFileSync(metadataPath, "utf8");
    const metadata = JSON.parse(rawMetadata) as {
      optimized?: Record<string, { src?: string }>;
    };
    const hasMissingSource = Object.values(metadata.optimized ?? {}).some((entry) => {
      if (!entry?.src) {
        return false;
      }
      const resolvedSource = path.resolve(depsDir, entry.src);
      return !fs.existsSync(resolvedSource);
    });
    if (!hasMissingSource) {
      return;
    }
  } catch {
    // Broken metadata should be treated the same as stale metadata.
  }

  fs.rmSync(cacheDir, { recursive: true, force: true });
  console.info("[vite] Cleared stale optimize cache because cached dependency sources no longer exist.");
}

function resolveDevProxyTarget(): string {
  const configuredHost = process.env.HOST?.trim();
  const port = Number(process.env.PORT ?? 3000);
  const targetHost = configuredHost && !["0.0.0.0", "::"].includes(configuredHost)
    ? configuredHost
    : "127.0.0.1";
  return `http://${targetHost}:${port}`;
}

function resolveAppVersion(): string {
  const packageJsonPath = path.resolve(__dirname, "package.json");
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8")) as ClientPackageJson;
  const version = typeof packageJson.version === "string" ? packageJson.version.trim() : "";
  return version || "0.0.0";
}

clearStaleOptimizeCache(__dirname);

const appVersion = resolveAppVersion();

export default defineConfig({
  base: "/",
  plugins: [react()],
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(appVersion),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@ai-novel/shared": path.resolve(__dirname, "../shared"),
    },
  },
  build: {
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("@assistant-ui")) {
            return "assistant-ui";
          }
          if (id.includes("platejs")) {
            return "plate-editor";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    host: true,
    proxy: {
      "/api": {
        target: resolveDevProxyTarget(),
        changeOrigin: true,
      },
    },
  },
});
