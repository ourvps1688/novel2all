import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type {
  DirectorBookAutomationAction,
  DirectorBookAutomationProjection,
} from "@ai-novel/shared/types/directorRuntime";
import { LayoutDashboard, ListTree, MapPin } from "lucide-react";
import { DirectorAttentionCenter } from "./DirectorAttentionCenter";
import { Button } from "@/components/ui/button";
import { mapProjectionToAttention } from "@/lib/mapProjectionToAttention";
import { useDirectorAttentionActionExecutor } from "@/lib/directorAttentionActions";
import { isDirectorContinuationAction } from "@/lib/directorContinuationActions";
import { resolveRecoveryFocusKey } from "@/lib/recoveryFocus";

interface DirectorBookAutomationCardProps {
  projection: DirectorBookAutomationProjection | null | undefined;
  fallbackSummary?: string | null;
  fallbackStatusLabel?: string | null;
  compact?: boolean;
  onOpenProgress?: () => void;
  onOpenTaskCenter: () => void;
  onSwitchToProjectNav?: () => void;
}

export default function DirectorBookAutomationCard({
  projection,
  fallbackSummary,
  compact = false,
  onOpenTaskCenter,
  onSwitchToProjectNav,
}: DirectorBookAutomationCardProps) {
  // Cancelled projections must read as inert (mirrors the old AICockpit idle
  // branch); the unified center treats `idle` as inert too.
  const attention = useMemo(
    () => mapProjectionToAttention(projection?.status === "cancelled" ? null : projection),
    [projection],
  );
  const executor = useDirectorAttentionActionExecutor();
  const navigate = useNavigate();
  const novelId = projection?.novelId ?? null;
  // When the director is stuck on a recovery/blocked state (often because the
  // beat sheet coverage is insufficient), surface a direct entry point to the
  // structured outline where "重新生成当前卷节奏板" lives — otherwise the user
  // only sees the suggestion with no way to act on it.
  const showBeatSheetEntry =
    Boolean(novelId) &&
    (projection?.status === "waiting_recovery" ||
      projection?.status === "blocked" ||
      projection?.status === "failed");

  // Generalized recovery-list: every navigation-type recovery action in the
  // projection becomes a "前往定位" entry that, when clicked, navigates with a
  // `focus` token so the destination auto-scrolls + highlights the exact card.
  // Command actions (continue/retry/cancel/auto_execute_range) are excluded —
  // they run in place and never navigate.
  const recoveryActions = useMemo(() => {
    const candidates: DirectorBookAutomationAction[] = [];
    const primary = projection?.primaryAction ?? null;
    const secondary = projection?.secondaryActions ?? [];
    for (const action of [primary, ...secondary]) {
      if (!action) continue;
      if (isDirectorContinuationAction(action)) continue;
      if (resolveRecoveryFocusKey(action) === null) continue;
      candidates.push(action);
    }
    return candidates;
  }, [projection]);

  const handleOpenBeatSheet = () => {
    if (!novelId) return;
    navigate(`/novels/${novelId}/edit?stage=structured&focus=beat-sheet`);
  };

  const handleAction = (action: DirectorBookAutomationAction) => {
    // `open_details` stays a host-side side effect (open the Task Center drawer),
    // exactly as before; every other action flows through the single executor.
    if (action.type === "open_details") {
      onOpenTaskCenter();
      return;
    }
    return executor(action);
  };

  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-foreground">AI 推进状态</div>
      {attention ? (
        <DirectorAttentionCenter state={attention} variant="card" onAction={handleAction} />
      ) : (
        <div className="rounded-xl border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
          {fallbackSummary?.trim() || "当前没有需要处理的导演状态。"}
        </div>
      )}
      {showBeatSheetEntry ? (
        <div className="space-y-2">
          {recoveryActions.map((action) => (
            <div key={`recovery-${action.type}-${action.label}`} className="space-y-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="w-full"
                onClick={() => handleAction(action)}
              >
                <MapPin className="h-4 w-4" />
                前往定位 · {action.label}
              </Button>
              <p className="px-1 text-xs leading-5 text-muted-foreground">
                已为你自动定位到需要操作的位置。
              </p>
            </div>
          ))}
          <div className="space-y-1">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="w-full"
              onClick={handleOpenBeatSheet}
            >
              <ListTree className="h-4 w-4" />
              重生成节奏板
            </Button>
            <p className="px-1 text-xs leading-5 text-muted-foreground">
              进入后在「当前卷节奏」卡片右上角点「重新生成当前卷节奏板」。
            </p>
          </div>
        </div>
      ) : null}
      {onSwitchToProjectNav ? (
        <Button type="button" size="sm" variant="ghost" className="w-full" onClick={onSwitchToProjectNav}>
          <LayoutDashboard className="h-4 w-4" />
          项目导航
        </Button>
      ) : null}
    </div>
  );
}
