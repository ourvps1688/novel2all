import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  PauseCircle,
  ShieldCheck,
} from "lucide-react";
import type { DirectorAttentionLevel } from "@ai-novel/shared/types/directorAttention";
import type {
  DirectorBookAutomationAction,
  DirectorBookAutomationDisplayState,
} from "@ai-novel/shared/types/directorRuntime";

/**
 * Single source of truth for how a `DirectorBookAutomationProjection`'s
 * `displayState` is rendered. Every surface that shows the book-automation
 * status — the novel-list cockpit, the workspace sidebar card, the attention
 * center — reads from here so the palette can never drift between components.
 *
 * The attention layer keys the same states by `DirectorAttentionLevel`; the
 * `ATTENTION_LEVEL_TO_DISPLAY_STATE` map is the only place the two enums are
 * correlated.
 */
export interface DisplayStateMeta {
  label: string;
  badgeVariant: "default" | "secondary" | "outline" | "destructive";
  surface: string;
  accent: string;
  icon: ReactNode;
  softSurface: string;
}

export const displayStateMeta: Record<DirectorBookAutomationDisplayState, DisplayStateMeta> = {
  processing: {
    label: "AI 正在处理",
    badgeVariant: "default",
    surface: "border-sky-500/25 bg-sky-500/10",
    accent: "text-sky-700 dark:text-sky-300",
    icon: <Activity className="h-4 w-4" />,
    softSurface: "bg-sky-500/10",
  },
  needs_confirmation: {
    label: "等你确认",
    badgeVariant: "outline",
    surface: "border-amber-500/25 bg-amber-500/10",
    accent: "text-amber-700 dark:text-amber-300",
    icon: <PauseCircle className="h-4 w-4" />,
    softSurface: "bg-amber-500/10",
  },
  paused: {
    label: "已暂停",
    badgeVariant: "outline",
    surface: "border-indigo-500/25 bg-indigo-500/10",
    accent: "text-indigo-700 dark:text-indigo-300",
    icon: <Clock3 className="h-4 w-4" />,
    softSurface: "bg-indigo-500/10",
  },
  needs_attention: {
    label: "出错需处理",
    badgeVariant: "destructive",
    surface: "border-destructive/30 bg-destructive/5",
    accent: "text-destructive",
    icon: <AlertTriangle className="h-4 w-4" />,
    softSurface: "bg-destructive/5",
  },
  completed: {
    label: "已完成",
    badgeVariant: "secondary",
    surface: "border-emerald-500/25 bg-emerald-500/10",
    accent: "text-emerald-700 dark:text-emerald-300",
    icon: <CheckCircle2 className="h-4 w-4" />,
    softSurface: "bg-emerald-500/10",
  },
  idle: {
    label: "未开启",
    badgeVariant: "secondary",
    surface: "border-border/70 bg-muted/20",
    accent: "text-muted-foreground",
    icon: <ShieldCheck className="h-4 w-4" />,
    softSurface: "bg-muted/20",
  },
};

export const ATTENTION_LEVEL_TO_DISPLAY_STATE: Record<DirectorAttentionLevel, DirectorBookAutomationDisplayState> = {
  idle: "idle",
  running: "processing",
  waiting_approval: "needs_confirmation",
  auto_recovering: "paused",
  needs_recovery: "needs_attention",
};

export function displayStateForAttentionLevel(level: DirectorAttentionLevel): DirectorBookAutomationDisplayState {
  return ATTENTION_LEVEL_TO_DISPLAY_STATE[level];
}

export function fallbackProjectionReason(fallbackSummary?: string | null): string {
  return fallbackSummary?.trim() || "没有需要你处理的 AI 自动推进任务。";
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无";
  return date.toLocaleString();
}

/**
 * The primary-action label. Confirmation states rephrase the raw
 * `continue` / `auto_execute_range` action as "确认并继续" so the user knows
 * the step will resume after their go-ahead.
 */
export function renderActionLabel(
  action: DirectorBookAutomationAction,
  displayState?: DirectorBookAutomationDisplayState,
): string {
  if (
    displayState === "needs_confirmation"
    && (action.type === "continue" || action.type === "auto_execute_range")
  ) {
    return "确认并继续";
  }
  return action.label || "继续处理";
}
