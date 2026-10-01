import { useState } from "react";
import { useDirectorAttentions } from "@/hooks/useDirectorAttention";
import { DirectorAttentionCenter } from "./DirectorAttentionCenter";
import { selectVisibleDirectorAttentions } from "@/lib/directorAttentionSelectors";

/**
 * Phase 5-C (T8): replaces the old default-OFF OS browser-notification watcher
 * with an always-on, in-app banner.
 *
 * It surfaces only the states that genuinely require the user to act
 * (`needs_recovery` / `waiting_approval`). Dismissal is session-scoped React
 * state — it is NOT persisted to sessionStorage, so dismissed novels reappear
 * after a full reload while staying hidden for the current session. The navbar
 * attention badge (`DirectorAttentionBadge`) remains the persistent count.
 */
export default function GlobalDirectorAttentionBanner() {
  const attentionsQuery = useDirectorAttentions();
  const [dismissedNovelIds, setDismissedNovelIds] = useState<Set<string>>(new Set());

  const visible = selectVisibleDirectorAttentions(attentionsQuery.data ?? [], dismissedNovelIds);

  if (visible.length === 0) {
    return null;
  }

  const dismiss = (novelId: string) => {
    setDismissedNovelIds((current) => {
      const next = new Set(current);
      next.add(novelId);
      return next;
    });
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 top-16 z-40 flex flex-col gap-2 px-4 py-2">
      <div className="pointer-events-auto mx-auto w-full max-w-3xl space-y-2">
        {visible.map((attention) => (
          <DirectorAttentionCenter
            key={attention.novelId}
            state={attention}
            variant="banner"
            onDismiss={() => dismiss(attention.novelId)}
          />
        ))}
      </div>
    </div>
  );
}
