const STORAGE_KEY = "ai-novel.last-novel-id";

/**
 * Tracks the most-recently opened novel so global entry points (the Sidebar
 * "创作资产" item, the legacy /assets route) can open the assets drawer inside a
 * concrete novel workspace. Assets are global/reusable, so the drawer does not
 * need to belong to a specific book — we just need *some* workspace to host it.
 */
export function getLastNovelId(): string {
  try {
    if (typeof window === "undefined" || !window.localStorage) return "";
    return window.localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setLastNovelId(id: string): void {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;
    if (!id) return;
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // ignore storage failures (private mode, quota, etc.)
  }
}
