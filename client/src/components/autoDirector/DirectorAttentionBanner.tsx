import { useState } from "react";
import type { DirectorBookAutomationAction } from "@ai-novel/shared/types/directorRuntime";
import { useDirectorAttention } from "@/hooks/useDirectorAttention";
import { DirectorAttentionCenter } from "./DirectorAttentionCenter";

export interface DirectorAttentionBannerProps {
  novelId: string;
  /** Optional external action handler (e.g. to coordinate with parent UI). */
  onAction?: (action: DirectorBookAutomationAction) => void | Promise<void>;
}

/**
 * Thin wrapper over `DirectorAttentionCenter` (banner variant) used by NovelEdit.
 * Pulls the single-novel attention via `useDirectorAttention`. The banner is
 * dismissible, but the global Navbar badge is a separate query and stays visible
 * after dismiss (so "收起" never removes the entry point).
 */
export default function DirectorAttentionBanner({ novelId, onAction }: DirectorAttentionBannerProps) {
  const { data: attention } = useDirectorAttention(novelId);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed || !attention) {
    return null;
  }

  return (
    <DirectorAttentionCenter
      state={attention}
      variant="banner"
      onAction={onAction}
      onDismiss={() => setDismissed(true)}
    />
  );
}
