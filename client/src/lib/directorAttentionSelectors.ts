import type { DirectorAttentionState } from "@ai-novel/shared/types/directorAttention";

const VISIBLE_LEVELS = new Set<DirectorAttentionState["level"]>(["needs_recovery", "waiting_approval"]);

/** Banner visibility: only actionable states the user must act on, minus session-dismissed novels (T8). */
export function selectVisibleDirectorAttentions(
  attentions: DirectorAttentionState[] | null | undefined,
  dismissedNovelIds: ReadonlySet<string>,
): DirectorAttentionState[] {
  return (attentions ?? []).filter(
    (attention) => VISIBLE_LEVELS.has(attention.level) && !dismissedNovelIds.has(attention.novelId),
  );
}

/** Non-idle attention keyed by novelId (drives NovelList "继续创作" + navbar badge). */
export function selectAttentionByNovelId(
  attentions: DirectorAttentionState[] | null | undefined,
): Map<string, DirectorAttentionState> {
  const map = new Map<string, DirectorAttentionState>();
  for (const attention of attentions ?? []) {
    if (attention.level !== "idle") {
      map.set(attention.novelId, attention);
    }
  }
  return map;
}

export interface ContinueNovelLike {
  id: string;
}

/** First 3 novels that currently need attention (NovelList "继续创作" shelf). */
export function selectContinueNovels<T extends ContinueNovelLike>(
  novels: readonly T[],
  attentionByNovelId: ReadonlyMap<string, DirectorAttentionState>,
): T[] {
  return novels.filter((novel) => attentionByNovelId.has(novel.id)).slice(0, 3);
}
