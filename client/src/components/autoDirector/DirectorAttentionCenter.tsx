import { useState, type ReactNode } from "react";
import type {
  DirectorAttentionLevel,
  DirectorAttentionState,
} from "@ai-novel/shared/types/directorAttention";
import type { DirectorBookAutomationAction } from "@ai-novel/shared/types/directorRuntime";
import {
  Activity,
  AlertTriangle,
  Clock3,
  Loader2,
  PauseCircle,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useDirectorAttentionActionExecutor } from "@/lib/directorAttentionActions";

/**
 * Visual language shared by the three variants, reusing the surface/accent
 * classes already established in `AICockpit`. We never branch on
 * `checkpointType` — the server owns that logic and only sends `level` +
 * `primaryAction` / `fallbackActions`.
 */
const LEVEL_META: Record<DirectorAttentionLevel, { surface: string; accent: string; icon: ReactNode }> = {
  idle: {
    surface: "border-border/70 bg-muted/20",
    accent: "text-muted-foreground",
    icon: <ShieldCheck className="h-4 w-4" />,
  },
  running: {
    surface: "border-sky-500/25 bg-sky-500/10",
    accent: "text-sky-700 dark:text-sky-300",
    icon: <Activity className="h-4 w-4" />,
  },
  waiting_approval: {
    surface: "border-amber-500/25 bg-amber-500/10",
    accent: "text-amber-700 dark:text-amber-300",
    icon: <PauseCircle className="h-4 w-4" />,
  },
  auto_recovering: {
    surface: "border-indigo-500/25 bg-indigo-500/10",
    accent: "text-indigo-700 dark:text-indigo-300",
    icon: <Clock3 className="h-4 w-4" />,
  },
  needs_recovery: {
    surface: "border-destructive/30 bg-destructive/5",
    accent: "text-destructive",
    icon: <AlertTriangle className="h-4 w-4" />,
  },
};

function resolveActionVariant(
  emphasis?: DirectorBookAutomationAction["emphasis"],
): "default" | "secondary" | "destructive" {
  if (emphasis === "destructive") return "destructive";
  if (emphasis === "secondary") return "secondary";
  return "default";
}

export interface DirectorAttentionCenterProps {
  state: DirectorAttentionState;
  /** "banner" → top-of-page strip (hidden while `running`); "card" → drawer/list card. */
  variant?: "banner" | "card";
  /**
   * Optional external action handler. When omitted, the component binds the
   * action to the built-in `executeDirectorAttentionAction` executor. Provide it
   * when the host needs to run extra side effects (e.g. close a drawer).
   */
  onAction?: (action: DirectorBookAutomationAction) => void | Promise<void>;
  /** Optional dismiss control. */
  onDismiss?: () => void;
}

export function DirectorAttentionCenter({
  state,
  variant = "card",
  onAction,
  onDismiss,
}: DirectorAttentionCenterProps) {
  const executor = useDirectorAttentionActionExecutor();
  const [pendingActionType, setPendingActionType] = useState<string | null>(null);

  const meta = LEVEL_META[state.level];

  // `idle` is always inert.
  if (state.level === "idle") {
    if (variant === "card") {
      return (
        <div className="rounded-xl border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
          当前没有需要处理的导演状态。
        </div>
      );
    }
    return null;
  }

  // The top-of-page banner only shows for actionable (non-running) states; a
  // still-running novel is not a "you must do something" situation.
  if (variant === "banner" && state.level === "running") {
    return null;
  }

  const handleAction = async (action: DirectorBookAutomationAction) => {
    setPendingActionType(action.type);
    try {
      if (onAction) {
        await onAction(action);
      } else {
        await executor(action);
      }
    } finally {
      setPendingActionType(null);
    }
  };

  const primaryAction = state.primaryAction;
  const fallbackActions = state.fallbackActions ?? [];

  return (
    <section className={cn("rounded-xl border p-4 shadow-sm", meta.surface)}>
      <div className="flex items-start justify-between gap-3">
        <div className={cn("flex min-w-0 items-center gap-2 text-xs font-medium", meta.accent)}>
          <span className="shrink-0">{meta.icon}</span>
          <span className="truncate">{state.headline || "自动导演状态更新"}</span>
        </div>
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="shrink-0 text-xs text-muted-foreground transition-colors hover:text-foreground"
            aria-label="收起"
          >
            收起
          </button>
        ) : null}
      </div>

      {state.detail ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{state.detail}</p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {primaryAction ? (
          <Button
            type="button"
            size="sm"
            variant={resolveActionVariant(primaryAction.emphasis)}
            disabled={pendingActionType !== null}
            onClick={() => handleAction(primaryAction)}
          >
            {pendingActionType === primaryAction.type ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : null}
            {primaryAction.label || "继续处理"}
          </Button>
        ) : null}

        {fallbackActions.map((action) => {
          const variantValue = action.emphasis === "destructive" ? "destructive" : "outline";
          return (
            <Button
              key={`${action.type}:${action.label}`}
              type="button"
              size="sm"
              variant={variantValue}
              disabled={pendingActionType !== null}
              onClick={() => handleAction(action)}
            >
              {pendingActionType === action.type ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : null}
              {action.label}
            </Button>
          );
        })}
      </div>
    </section>
  );
}
