import type {
  AutoDirectorMutationActionCode,
} from "./autoDirectorAttention.js";
import type {
  DirectorTakeoverEntryStep,
  DirectorTakeoverRequest,
} from "./novelDirector.js";
import type { NovelWorkflowCheckpoint } from "./novelWorkflow.js";
import type { TaskStatus } from "./task.js";

export type AutoDirectorValidationSource =
  | "takeover"
  | "continue"
  | "retry"
  | "follow_up_action"
  | "batch_action"
  | "web";

export type AutoDirectorAffectedScope =
  | {
      type: "book";
      label: string;
    }
  | {
      type: "chapter_range";
      label: string;
      startOrder: number;
      endOrder: number;
    }
  | {
      type: "volume";
      label: string;
      volumeOrder: number;
    };

export type AutoDirectorValidationRequiredActionCode =
  | "clear_checkpoint"
  | "clear_failure"
  | "create_rewrite_snapshot"
  | "cancel_replaced_tasks"
  | "reset_downstream_state"
  | "revalidate_assets"
  | "auto_backfill_structured_outline";

export interface AutoDirectorValidationRequiredAction {
  code: AutoDirectorValidationRequiredActionCode;
  label: string;
  riskLevel: "low" | "medium" | "high";
  safeToAutoFix: boolean;
}

export interface AutoDirectorValidationResult {
  allowed: boolean;
  blockingReasons: string[];
  warnings: string[];
  requiredActions: AutoDirectorValidationRequiredAction[];
  affectedScope: AutoDirectorAffectedScope;
  nextCheckpoint?: NovelWorkflowCheckpoint | null;
  nextAction?: string | null;
}

export interface AutoDirectorValidationAssetSnapshot {
  hasProjectSetup?: boolean;
  hasStoryMacroPlan?: boolean;
  hasBookContract?: boolean;
  characterCount?: number;
  volumeCount?: number;
  hasVolumeStrategyPlan?: boolean;
  hasStructuredOutline?: boolean;
  plannedChapterCount?: number | null;
  totalChapterCount?: number | null;
  volumeChapterRanges?: Array<{
    volumeOrder: number;
    startOrder: number;
    endOrder: number;
  }>;
  structuredOutlineChapterOrders?: number[];
}

export interface AutoDirectorTakeoverValidationInput {
  source: AutoDirectorValidationSource;
  request: Pick<DirectorTakeoverRequest, "novelId" | "entryStep" | "strategy" | "autoExecutionPlan" | "runMode">;
  assets: AutoDirectorValidationAssetSnapshot;
}

export interface AutoDirectorActionValidationTaskSnapshot {
  id: string;
  lane?: string | null;
  status: TaskStatus | string;
  checkpointType?: NovelWorkflowCheckpoint | string | null;
  pendingManualRecovery?: boolean | null;
  novelId?: string | null;
  seedPayload?: {
    autoExecution?: {
      enabled?: boolean;
      scopeLabel?: string | null;
      startOrder?: number;
      endOrder?: number;
      volumeOrder?: number;
      volumeTitle?: string | null;
    } | null;
  } | null;
}

export interface AutoDirectorActionValidationInput {
  source: AutoDirectorValidationSource;
  actionCode: AutoDirectorMutationActionCode;
  task: AutoDirectorActionValidationTaskSnapshot;
}

export const AUTO_DIRECTOR_ATTENTION_SECTIONS = [
  "needs_validation",
  "exception",
  "pending",
  "auto_progress",
  "replaced",
] as const;

export type AutoDirectorAttentionSection = (typeof AUTO_DIRECTOR_ATTENTION_SECTIONS)[number];

export interface AutoDirectorAttentionSectionInput {
  status: TaskStatus | string;
  checkpointType?: NovelWorkflowCheckpoint | string | null;
  pendingManualRecovery?: boolean | null;
  replacementTaskId?: string | null;
  validationResult?: AutoDirectorValidationResult | null;
}

export const AUTO_DIRECTOR_TAKEOVER_ENTRY_ORDER: Record<DirectorTakeoverEntryStep, number> = {
  basic: 1,
  story_macro: 2,
  world: 3,
  character: 4,
  outline: 5,
  structured: 6,
  chapter: 7,
  pipeline: 8,
};
