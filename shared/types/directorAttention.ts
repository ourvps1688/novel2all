import type { DirectorBookAutomationAction } from "./directorRuntime.js";

export type DirectorAttentionLevel =
  | "idle"
  | "running"
  | "waiting_approval"
  | "auto_recovering"
  | "needs_recovery";

export interface DirectorAttentionState {
  novelId: string;
  novelTitle: string | null;
  level: DirectorAttentionLevel;
  headline: string;
  detail: string | null;
  requiresUserAction: boolean;
  primaryAction: DirectorBookAutomationAction | null;
  fallbackActions: DirectorBookAutomationAction[];
  updatedAt: string;
}
