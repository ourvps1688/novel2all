import type { NovelWorkflowCheckpoint } from "./novelWorkflow.js";
import type { TaskStatus, UnifiedTaskDetail } from "./task.js";
import type {
  AutoDirectorAffectedScope,
  AutoDirectorAttentionSection,
  AutoDirectorValidationResult,
  AutoDirectorValidationRequiredAction,
} from "./autoDirectorValidation.js";

export const AUTO_DIRECTOR_ATTENTION_REASONS = [
  "manual_recovery_required",
  "runtime_failed",
  "candidate_selection_required",
  "replan_required",
  "runtime_cancelled",
  "chapter_batch_execution_pending",
  "quality_repair_pending",
  "auto_progress_running",
  "auto_approval_completed",
  "runtime_replaced",
  "validation_required",
] as const;

export type AutoDirectorAttentionReason = (typeof AUTO_DIRECTOR_ATTENTION_REASONS)[number];

export type AutoDirectorAttentionPriority = "P0" | "P1" | "P2";

export type AutoDirectorActionRiskLevel = "low" | "medium" | "high";

export type AutoDirectorMutationActionCode =
  | "continue_auto_execution"
  | "continue_generic"
  | "auto_backfill_structured_outline"
  | "retry_with_task_model"
  | "retry_with_route_model"
  | "safe_fix_validation";

export type AutoDirectorNavigationActionCode =
  | "go_replan"
  | "go_candidate_selection"
  | "open_detail";

export type AutoDirectorActionCode = AutoDirectorMutationActionCode | AutoDirectorNavigationActionCode;

export interface AutoDirectorAction {
  code: AutoDirectorActionCode;
  kind: "mutation" | "navigation";
  label: string;
  riskLevel: AutoDirectorActionRiskLevel;
  requiresConfirm: boolean;
  executorActionCode?: AutoDirectorMutationActionCode;
  targetUrl?: string;
  deepLink?: string;
}

export interface AutoDirectorAttentionResolverInput {
  status: TaskStatus;
  checkpointType?: NovelWorkflowCheckpoint | null;
  pendingManualRecovery?: boolean;
  executionScopeLabel?: string | null;
  replacementTaskId?: string | null;
  validationResult?: AutoDirectorValidationResult | null;
}

export interface AutoDirectorResolvedAttentionReason {
  reason: AutoDirectorAttentionReason;
  reasonLabel: string;
  priority: AutoDirectorAttentionPriority;
  availableActions: AutoDirectorAction[];
  batchActionCodes: AutoDirectorMutationActionCode[];
  supportsBatch: boolean;
}

export type AutoDirectorCountersByReason = Record<AutoDirectorAttentionReason, number>;

export type AutoDirectorCountersBySection = Record<AutoDirectorAttentionSection, number>;

export interface AutoDirectorAttentionValidationSummary {
  blockingReasons: string[];
  warnings: string[];
  requiredActions: AutoDirectorValidationRequiredAction[];
  affectedScope: AutoDirectorAffectedScope | null;
  nextAction: string | null;
}

export interface AutoDirectorAttentionItem {
  itemType: "task" | "auto_approval_record";
  directorTaskId: string;
  /** @deprecated Use directorTaskId for auto director attention state. */
  taskId: string;
  autoApprovalRecordId?: string;
  novelId: string | null;
  novelTitle: string;
  taskTitle: string;
  lane: "auto_director";
  status: TaskStatus;
  currentStage: string | null;
  checkpointType: NovelWorkflowCheckpoint | null;
  reason: AutoDirectorAttentionReason;
  section: AutoDirectorAttentionSection;
  reasonLabel: string;
  priority: AutoDirectorAttentionPriority;
  attentionSummary: string;
  blockingReason: string | null;
  validationSummary?: AutoDirectorAttentionValidationSummary | null;
  executionScope: string | null;
  currentModel: string | null;
  availableActions: AutoDirectorAction[];
  batchActionCodes: AutoDirectorMutationActionCode[];
  supportsBatch: boolean;
  pendingManualRecovery: boolean;
  lastMilestoneAt: string | null;
  updatedAt: string;
}

export interface AutoDirectorAttentionMilestone {
  label: string;
  at: string;
  status: TaskStatus;
  summary?: string | null;
}

export interface AutoDirectorAttentionDetail {
  directorTaskId: string;
  /** @deprecated Use directorTaskId for auto director attention state. */
  taskId: string;
  reasonLabel: string;
  priority: AutoDirectorAttentionPriority;
  attentionSummary: string;
  checkpointSummary: string | null;
  blockingReason: string | null;
  nextStepSuggestion: string | null;
  validationSummary: AutoDirectorAttentionValidationSummary | null;
  currentModel: string | null;
  riskNote: string | null;
  originDetailUrl: string;
  replanUrl: string | null;
  candidateSelectionUrl: string | null;
  availableActions: AutoDirectorAction[];
  milestones: AutoDirectorAttentionMilestone[];
  task: UnifiedTaskDetail;
}

export interface AutoDirectorAttentionOverview {
  totalCount: number;
  countersByReason: AutoDirectorCountersByReason;
  countersBySection: AutoDirectorCountersBySection;
}

export interface AutoDirectorAttentionSummaryCounters {
  recoveredToday: number;
  completedToday: number;
}

export interface AutoDirectorAttentionAvailableFilters {
  sections: AutoDirectorAttentionSection[];
  reasons: AutoDirectorAttentionReason[];
  statuses: TaskStatus[];
}

export interface AutoDirectorAttentionPagination {
  page: number;
  pageSize: number;
  total: number;
}

export interface AutoDirectorAttentionListResponse {
  items: AutoDirectorAttentionItem[];
  countersByReason: AutoDirectorCountersByReason;
  countersBySection: AutoDirectorCountersBySection;
  summaryCounters: AutoDirectorAttentionSummaryCounters;
  availableFilters: AutoDirectorAttentionAvailableFilters;
  pagination: AutoDirectorAttentionPagination;
}

export interface AutoDirectorAttentionListInput {
  section?: AutoDirectorAttentionSection;
  reason?: AutoDirectorAttentionReason;
  status?: TaskStatus;
  novelId?: string;
  supportsBatch?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AutoDirectorActionRequest {
  directorTaskId?: string;
  /** @deprecated Use directorTaskId when the caller is auto-director-specific. */
  taskId: string;
  actionCode: AutoDirectorMutationActionCode;
  source: "web";
  operatorId: string;
  idempotencyKey: string;
  metadata?: Record<string, unknown>;
}

export const AUTO_DIRECTOR_ACTION_RESULT_CODES = [
  "executed",
  "already_processed",
  "state_changed",
  "forbidden",
  "failed",
] as const;

export type AutoDirectorActionResultCode = (typeof AUTO_DIRECTOR_ACTION_RESULT_CODES)[number];

export interface AutoDirectorActionExecutionResult {
  directorTaskId?: string;
  /** @deprecated Use directorTaskId when present. */
  taskId: string;
  actionCode: AutoDirectorMutationActionCode;
  code: AutoDirectorActionResultCode;
  message: string;
  task?: UnifiedTaskDetail | null;
}

export interface AutoDirectorBatchActionRequest {
  actionCode: AutoDirectorMutationActionCode;
  taskIds: string[];
  source: "web";
  operatorId: string;
  batchRequestKey: string;
  metadata?: Record<string, unknown>;
}

export const AUTO_DIRECTOR_BATCH_RESULT_CODES = [
  "success",
  "partial_success",
  "failed",
  "skipped",
] as const;

export type AutoDirectorBatchResultCode = (typeof AUTO_DIRECTOR_BATCH_RESULT_CODES)[number];

export interface AutoDirectorBatchActionExecutionResult {
  code: AutoDirectorBatchResultCode;
  successCount: number;
  failureCount: number;
  skippedCount: number;
  itemResults: AutoDirectorActionExecutionResult[];
}
