import { useMemo } from "react";
import type {
  DirectorBookAutomationAction,
  DirectorBookAutomationProjection,
} from "@ai-novel/shared/types/directorRuntime";
import { LayoutDashboard } from "lucide-react";
import { DirectorAttentionCenter } from "./DirectorAttentionCenter";
import { Button } from "@/components/ui/button";
import { mapProjectionToAttention } from "@/lib/mapProjectionToAttention";
import { useDirectorAttentionActionExecutor } from "@/lib/directorAttentionActions";

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
      {onSwitchToProjectNav ? (
        <Button type="button" size="sm" variant="ghost" className="w-full" onClick={onSwitchToProjectNav}>
          <LayoutDashboard className="h-4 w-4" />
          项目导航
        </Button>
      ) : null}
    </div>
  );
}
