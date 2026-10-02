import { useState } from "react";
import type {
  DirectorBookAutomationAction,
  DirectorBookAutomationProjection,
} from "@ai-novel/shared/types/directorRuntime";
import { ExternalLink, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useDirectorAttentionActionExecutor } from "@/lib/directorAttentionActions";
import { resolveRecoveryFocusKey } from "@/lib/recoveryFocus";
import {
  displayStateMeta,
  fallbackProjectionReason,
  formatDateTime,
  renderActionLabel,
} from "./bookAutomationStatusMeta";

type BookAutomationStatusBarVariant = "banner" | "card";

export interface BookAutomationStatusBarProps {
  projection?: DirectorBookAutomationProjection | null;
  /** "banner" → rich top-of-page strip (novel cockpit); "card" → compact sidebar/drawer card. */
  variant?: BookAutomationStatusBarVariant;
  isActionPending?: boolean;
  showDetailsAction?: boolean;
  /** Optional external action handler. When omitted, actions bind to the built-in executor. */
  onAction?: (projection: DirectorBookAutomationProjection, action: DirectorBookAutomationAction) => void;
  onOpenDetails?: (projection: DirectorBookAutomationProjection) => void;
  onOpenNovel?: (projection: DirectorBookAutomationProjection) => void;
  fallbackSummary?: string | null;
  fallbackStatusLabel?: string | null;
  onOpenFallbackDetails?: () => void;
}

function recoveryLabel(action: DirectorBookAutomationAction): string {
  const label = renderActionLabel(action);
  const focus = resolveRecoveryFocusKey(action);
  return focus ? `前往定位 · ${label}` : label;
}

function actionVariant(
  emphasis?: DirectorBookAutomationAction["emphasis"],
): "default" | "secondary" | "outline" | "destructive" {
  if (emphasis === "destructive") return "destructive";
  if (emphasis === "secondary") return "secondary";
  return "default";
}

/**
 * The single projection-driven status bar. The novel cockpit (banner) and the
 * workspace sidebar card both render through this one component, so the status
 * language, icons and action wiring can never diverge between surfaces.
 *
 * Cancelled projections read as inert (mirrors the old `DirectorBookAutomationCard`
 * `mapProjectionToAttention(null)` behaviour).
 */
export default function BookAutomationStatusBar(props: BookAutomationStatusBarProps) {
  const {
    variant = "banner",
    isActionPending = false,
    showDetailsAction = true,
    onAction,
    onOpenDetails,
    onOpenNovel,
    fallbackSummary,
    fallbackStatusLabel,
    onOpenFallbackDetails,
  } = props;

  const rawProjection = props.projection ?? null;
  const projection = rawProjection && rawProjection.status !== "cancelled" ? rawProjection : null;
  const executor = useDirectorAttentionActionExecutor();
  const [pendingType, setPendingType] = useState<string | null>(null);

  if (!projection) {
    if (variant === "card") {
      return (
        <div className="rounded-xl border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
          {fallbackSummary?.trim() || "当前没有需要处理的导演状态。"}
        </div>
      );
    }
    return (
      <div className="rounded-2xl bg-muted/25 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-start gap-2">
            <span className="mt-0.5 shrink-0 text-muted-foreground">{displayStateMeta.idle.icon}</span>
            <div className="min-w-0">
              <div className="text-xs leading-5 text-muted-foreground">{fallbackProjectionReason(fallbackSummary ?? null)}</div>
            </div>
          </div>
          <Badge variant="secondary" className="shrink-0">{fallbackStatusLabel ?? "还没开始自动写作"}</Badge>
        </div>
        {onOpenFallbackDetails ? (
          <Button type="button" size="sm" variant="outline" className="mt-3 w-full" onClick={onOpenFallbackDetails}>
            查看
          </Button>
        ) : null}
      </div>
    );
  }

  const displayState = projection.displayState;
  const meta = displayStateMeta[displayState];
  const primaryAction = projection.primaryAction ?? null;
  const secondaryActions = projection.secondaryActions ?? [];
  const detailAction = secondaryActions.find((item) => item.type === "open_details") ?? null;
  const canOpenDetails = showDetailsAction && Boolean(onOpenDetails || (detailAction && onAction));
  const reason =
    projection.userReason?.trim()
    || projection.blockedReason?.trim()
    || projection.detail?.trim()
    || projection.automationSummary?.trim()
    || fallbackProjectionReason(fallbackSummary ?? null);
  const statusHeadline = projection.userHeadline?.trim() || projection.headline?.trim() || meta.label;
  const statusDetail =
    reason === statusHeadline
      ? projection.progressSummary?.trim() || "AI 会在这里汇总本书自动推进的最新状态。"
      : reason;
  const latestRecordText = projection.timeline?.[0] ? formatDateTime(projection.timeline[0].occurredAt) : "暂无";

  const runAction = async (action: DirectorBookAutomationAction) => {
    setPendingType(action.type);
    try {
      if (onAction) {
        await onAction(projection, action);
        return;
      }
      await executor(action);
    } finally {
      setPendingType(null);
    }
  };

  const handlePrimary = () => {
    if (primaryAction && onAction) {
      void runAction(primaryAction);
      return;
    }
    onOpenNovel?.(projection);
  };

  const handleDetails = () => {
    if (detailAction && onAction) {
      void runAction(detailAction);
      return;
    }
    onOpenDetails?.(projection);
  };

  if (variant === "card") {
    return (
      <section className={cn("rounded-xl border p-4 shadow-sm", meta.surface)}>
        <div className={cn("flex min-w-0 items-center gap-2 text-xs font-medium", meta.accent)}>
          <span className="shrink-0">{meta.icon}</span>
          <span className="truncate">{meta.label}</span>
        </div>
        <h3 className="mt-2 text-sm font-semibold leading-6 text-foreground">{statusHeadline}</h3>
        {statusDetail ? (
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{statusDetail}</p>
        ) : null}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {primaryAction ? (
            <Button
              type="button"
              size="sm"
              variant={actionVariant(primaryAction.emphasis)}
              disabled={isActionPending || pendingType !== null}
              onClick={handlePrimary}
            >
              {pendingType === primaryAction.type ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
              {renderActionLabel(primaryAction, displayState)}
            </Button>
          ) : null}
          {secondaryActions
            .filter((action) => action.type !== "open_details")
            .map((action) => (
              <Button
                key={`${action.type}:${action.label}`}
                type="button"
                size="sm"
                variant={action.emphasis === "destructive" ? "destructive" : "outline"}
                disabled={isActionPending || pendingType !== null}
                onClick={() => void runAction(action)}
              >
                {pendingType === action.type ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                {recoveryLabel(action)}
              </Button>
            ))}
        </div>
      </section>
    );
  }

  // banner variant (novel cockpit header)
  return (
    <section className={cn("rounded-2xl p-5 shadow-sm", meta.softSurface)}>
      <div className="flex items-center justify-between gap-3">
        <div className={cn("flex min-w-0 items-center gap-2 text-xs font-medium", meta.accent)}>
          <span className="shrink-0">{meta.icon}</span>
          <span className="truncate">{meta.label}</span>
        </div>
        <span className="min-w-0 max-w-[52%] truncate rounded-full bg-background/60 px-2.5 py-1 text-xs text-muted-foreground">
          {projection.focusNovel.title}
        </span>
      </div>

      <div className="mt-4 max-w-[46rem]">
        <h3 className="text-base font-semibold leading-7 text-foreground">{statusHeadline}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{statusDetail}</p>
      </div>

      <div className="mt-5 grid gap-3 rounded-xl bg-background/60 p-3 sm:grid-cols-3">
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">当前状态</div>
          <div className={cn("mt-1 truncate text-sm font-medium", meta.accent)}>{meta.label}</div>
        </div>
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">推进概览</div>
          <div className="mt-1 truncate text-sm font-medium text-foreground">{projection.progressSummary || "暂无进度摘要"}</div>
        </div>
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">最近记录</div>
          <div className="mt-1 truncate text-sm font-medium text-foreground">{latestRecordText}</div>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">下一步</div>
          <div className="mt-1 text-sm font-medium leading-5 text-foreground">
            {projection.nextActionLabel || "打开小说查看当前内容"}
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <Button type="button" size="sm" onClick={handlePrimary} disabled={isActionPending}>
            {isActionPending ? "处理中..." : renderActionLabel(primaryAction ?? {
              type: "open_novel",
              label: "打开小说",
              target: { novelId: projection.novelId },
            }, displayState)}
          </Button>
          {canOpenDetails ? (
            <Button type="button" size="sm" variant="secondary" onClick={handleDetails}>
              <ExternalLink className="h-4 w-4" />
              执行详情
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
