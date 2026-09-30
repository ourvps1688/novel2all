export type NovelWorkflowLane = "manual_create" | "auto_director" | "creation_studio";

export type NovelWorkflowStage =
  | "project_setup"
  | "creation_intent"
  | "short_story_plan"
  | "short_story_draft"
  | "short_story_review"
  | "auto_director"
  | "story_macro"
  | "world_setup"
  | "character_setup"
  | "volume_strategy"
  | "structured_outline"
  | "chapter_execution"
  | "quality_repair";

export type NovelWorkflowCheckpoint =
  | "candidate_selection_required"
  | "book_contract_ready"
  | "character_setup_required"
  | "volume_strategy_ready"
  | "production_experience_required"
  | "chapter_batch_ready"
  | "step_review_required"
  | "replan_required"
  | "workflow_completed";

// Runtime value arrays — single source of truth for the enums above.
// zod schemas and other runtime consumers derive from these instead of
// re-listing literals (T3-5: collapse hand-copied translation tables).
export const NOVEL_WORKFLOW_STAGE_VALUES = [
  "project_setup",
  "creation_intent",
  "short_story_plan",
  "short_story_draft",
  "short_story_review",
  "auto_director",
  "story_macro",
  "world_setup",
  "character_setup",
  "volume_strategy",
  "structured_outline",
  "chapter_execution",
  "quality_repair",
] as const;

// Canonical stage → human label. Single source of truth for all stage labels
// (T3-5c). Server NOVEL_WORKFLOW_STAGE_LABELS consumers and the client tab/step
// lists derive their labels from this so the text cannot drift.
export const NOVEL_WORKFLOW_STAGE_LABELS: Record<NovelWorkflowStage, string> = {
  project_setup: "项目设定",
  creation_intent: "理解创作想法",
  short_story_plan: "规划短篇",
  short_story_draft: "生成完整作品",
  short_story_review: "全篇审校",
  auto_director: "AI 自动导演",
  story_macro: "故事宏观规划",
  world_setup: "世界观准备",
  character_setup: "角色准备",
  volume_strategy: "卷战略 / 卷骨架",
  structured_outline: "节奏 / 拆章",
  chapter_execution: "章节执行",
  quality_repair: "质量修复",
};

export const NOVEL_WORKFLOW_STAGE_PROGRESS: Record<NovelWorkflowStage, number> = {
  project_setup: 0.08,
  creation_intent: 0.08,
  short_story_plan: 0.2,
  short_story_draft: 0.35,
  short_story_review: 0.9,
  auto_director: 0.15,
  story_macro: 0.26,
  world_setup: 0.34,
  character_setup: 0.42,
  volume_strategy: 0.5,
  structured_outline: 0.68,
  chapter_execution: 0.84,
  quality_repair: 0.94,
};

export const NOVEL_WORKFLOW_CHECKPOINT_VALUES = [
  "candidate_selection_required",
  "book_contract_ready",
  "character_setup_required",
  "volume_strategy_ready",
  "production_experience_required",
  "chapter_batch_ready",
  "step_review_required",
  "replan_required",
  "workflow_completed",
] as const;

export const NOVEL_WORKFLOW_LANE_VALUES = [
  "manual_create",
  "auto_director",
  "creation_studio",
] as const;

// The director HTTP API only accepts this subset of workflow stages.
// Keep in sync with the route surface in novelWorkflows.ts.
export const DIRECTOR_API_STAGE_VALUES = [
  "project_setup",
  "auto_director",
  "story_macro",
  "world_setup",
  "character_setup",
  "volume_strategy",
  "structured_outline",
  "chapter_execution",
  "quality_repair",
] as const;

// Workspace flow tabs — the single canonical Tab namespace shared by the
// director lock scope, takeover entry step, and workspace navigation (T3-5b).
export const NOVEL_WORKSPACE_FLOW_TABS = [
  "basic",
  "story_macro",
  "world",
  "character",
  "outline",
  "structured",
  "chapter",
  "pipeline",
] as const;

export type NovelWorkspaceFlowTab = typeof NOVEL_WORKSPACE_FLOW_TABS[number];

export type NovelWorkspaceTab = NovelWorkspaceFlowTab | "history";

export type NovelWorkflowMilestoneType =
  | NovelWorkflowCheckpoint
  | "rewrite_snapshot_created";

export interface NovelWorkflowMilestone {
  checkpointType: NovelWorkflowMilestoneType;
  summary: string;
  createdAt: string;
}

export interface NovelWorkflowResumeTarget {
  route: "/create" | "/novels/create" | "/novels/:id/edit" | "/novels/:id/simple" | "/novels/:id/story";
  novelId?: string | null;
  taskId?: string | null;
  lane: NovelWorkflowLane;
  stage?: NovelWorkspaceFlowTab;
  chapterId?: string | null;
  volumeId?: string | null;
  mode?: "director" | null;
}

export interface NovelWorkflowLaneDescriptor {
  lane: NovelWorkflowLane;
  defaultTitle: string;
  initialStage: NovelWorkflowStage;
  initialItemKey: string;
  initialItemLabel: string;
  taskQueryKey: "workspaceTaskId" | "directorTaskId" | "taskId";
}

export const NOVEL_WORKFLOW_LANE_DESCRIPTORS: Record<NovelWorkflowLane, NovelWorkflowLaneDescriptor> = {
  manual_create: {
    lane: "manual_create",
    defaultTitle: "小说流程任务",
    initialStage: "project_setup",
    initialItemKey: "project_setup",
    initialItemLabel: "等待创建项目",
    taskQueryKey: "workspaceTaskId",
  },
  auto_director: {
    lane: "auto_director",
    defaultTitle: "AI 自动导演小说",
    initialStage: "auto_director",
    initialItemKey: "auto_director",
    initialItemLabel: "等待生成候选方向",
    taskQueryKey: "directorTaskId",
  },
  creation_studio: {
    lane: "creation_studio",
    defaultTitle: "把想法写成作品",
    initialStage: "creation_intent",
    initialItemKey: "creation_intent",
    initialItemLabel: "正在理解你的想法",
    taskQueryKey: "taskId",
  },
};

export function getNovelWorkflowLaneDescriptor(lane: NovelWorkflowLane): NovelWorkflowLaneDescriptor {
  return NOVEL_WORKFLOW_LANE_DESCRIPTORS[lane];
}

export type NovelProductionExperience = "simple" | "professional";

export interface NovelProductionExperienceSelectionResponse {
  experience: NovelProductionExperience;
  workflowTaskId: string;
  novelId: string;
  targetRoute: `/novels/${string}/simple` | `/novels/${string}/edit`;
  backgroundStarted: boolean;
  commandId?: string | null;
}

export interface BookContract {
  id: string;
  novelId: string;
  readingPromise: string;
  protagonistFantasy: string;
  coreSellingPoint: string;
  chapter3Payoff: string;
  chapter10Payoff: string;
  chapter30Payoff: string;
  escalationLadder: string;
  relationshipMainline: string;
  absoluteRedLines: string[];
  createdAt: string;
  updatedAt: string;
}

export interface BookContractDraft {
  readingPromise: string;
  protagonistFantasy: string;
  coreSellingPoint: string;
  chapter3Payoff: string;
  chapter10Payoff: string;
  chapter30Payoff: string;
  escalationLadder: string;
  relationshipMainline: string;
  absoluteRedLines: string[];
}
