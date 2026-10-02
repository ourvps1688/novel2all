import type { DirectorBookAutomationAction } from "@ai-novel/shared/types/directorRuntime";

/**
 * Destination anchors a recovery action can ask the client to auto-locate.
 *
 * These keys are intentionally decoupled from any single novel: the client
 * derives them from the *type* of the recovery action (and its `target.tab`),
 * never from per-novel data. That keeps the auto-location mechanism a single
 * source of truth that works for every novel.
 */
export type RecoveryFocusKey =
  | "beat-sheet"
  | "strategy-plan"
  | "quality-repair"
  | "chapter-execution"
  | "task-panel"
  | "candidate-selection"
  | "production-selection";

/**
 * Map a recovery action to the focus key of the destination it should
 * auto-locate. Returns `null` for actions that either run in place (commands)
 * or have no meaningful navigation destination we can highlight.
 *
 * Only NAVIGATION-type actions get a focus key — command semantics
 * (continue / retry / cancel / auto_execute_range) are intentionally excluded
 * here because they execute in place and ignore focus.
 */
export function resolveRecoveryFocusKey(action: DirectorBookAutomationAction): RecoveryFocusKey | null {
  const tab = action.target?.tab ?? null;
  switch (action.type) {
    case "open_details":
      return "task-panel";
    case "open_chapter":
      return "chapter-execution";
    case "confirm_candidate":
      return "candidate-selection";
    case "open_novel":
      return "production-selection";
    case "auto_execute_range":
      // A pipeline-tagged range lands the user on the structured page so the
      // beat-sheet card can be highlighted; a chapter-tagged range points at the
      // chapter-execution area.
      return tab === "chapter" ? "chapter-execution" : "beat-sheet";
    default:
      return null;
  }
}

/**
 * Append a `?focus=<key>` token to a deep link. If either the href or the focus
 * key is missing, the href is returned unchanged so callers can append blindly.
 */
export function withFocus(href: string | null | undefined, focus: RecoveryFocusKey | null): string {
  if (!href || !focus) {
    return href ?? "";
  }
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}focus=${focus}`;
}
