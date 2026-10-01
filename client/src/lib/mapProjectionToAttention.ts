import type {
  DirectorAttentionLevel,
  DirectorAttentionState,
} from "@ai-novel/shared/types/directorAttention";
import type { DirectorBookAutomationProjection } from "@ai-novel/shared/types/directorRuntime";

/**
 * Client-side adapter that mirrors the server's canonical
 * `mapProjectionToAttention` in
 * `server/src/services/novel/director/attention/DirectorAttentionService.ts`.
 *
 * AI-First red line: this is NOT a second normalization. It reproduces the
 * single projection→attention mapping already owned by the server so surfaces
 * that already hold a `DirectorBookAutomationProjection` can render the unified
 * `DirectorAttentionCenter` without an extra round-trip. No new string→branch
 * table is introduced — `primaryAction` / `fallbackActions` reuse the existing
 * `DirectorBookAutomationAction` structured descriptors.
 *
 * If the server mapping changes, update both copies.
 */
function mapAttentionLevel(projection: DirectorBookAutomationProjection): DirectorAttentionLevel {
  const status = projection.status;
  const derivedState = projection.workerHealth?.derivedState;
  if (status === "waiting_approval") return "waiting_approval";
  if (status === "waiting_recovery" || status === "blocked" || status === "failed") return "needs_recovery";
  if (derivedState === "auto_recovering") return "auto_recovering";
  if (status === "running" || status === "queued") return "running";
  return "idle";
}

export function mapProjectionToAttention(
  projection: DirectorBookAutomationProjection | null | undefined,
): DirectorAttentionState | null {
  if (!projection) return null;
  const level = mapAttentionLevel(projection);
  return {
    novelId: projection.novelId,
    novelTitle: projection.focusNovel?.title ?? null,
    level,
    headline: projection.headline,
    detail: projection.detail ?? projection.blockedReason ?? null,
    requiresUserAction: projection.requiresUserAction,
    primaryAction: projection.primaryAction ?? null,
    fallbackActions: projection.secondaryActions ?? [],
    updatedAt: projection.updatedAt,
  };
}
