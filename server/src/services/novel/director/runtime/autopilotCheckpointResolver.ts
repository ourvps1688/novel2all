import type { NovelWorkflowService } from "../../workflow/NovelWorkflowService";
import type { DirectorCommandService } from "../commands/DirectorCommandService";
import type { DirectorProductionExperienceService } from "../commands/DirectorProductionExperienceService";

export interface AutopilotCheckpointResolverDeps {
  workflowService: Pick<NovelWorkflowService, "getTaskById">;
  commandService: Pick<DirectorCommandService, "enqueueContinueCommand">;
  productionExperienceService: Pick<DirectorProductionExperienceService, "autoPassForAutopilot">;
}

/**
 * T3.3 global pause control (zero migration).
 *
 * A paused full_book_autopilot run is encoded as a `waiting_approval` task that also
 * carries `pendingManualRecovery === true` (set by the `pause_autopilot` control command).
 * Such a task must NEVER be auto-resolved by the checkpoint watchdog/resolver, otherwise
 * the watchdog would immediately resume a run the operator just paused.
 */
export function isAutopilotCheckpointPaused(task: {
  status?: string | null;
  pendingManualRecovery?: boolean | null;
}): boolean {
  return task.status === "waiting_approval" && task.pendingManualRecovery === true;
}

/**
 * 在 full_book_autopilot 下，所有 `waiting_approval` 关卡都必须可被程序化解析，
 * 否则会死锁整条全自动流水线。本映射确保每一种关卡都能落入「自动通过」或「入队 continue」，
 * 绝不会递归调用 continueTask。
 */
const AUTO_EXECUTE_RANGE_CHECKPOINTS = new Set<string>([
  "chapter_batch_ready",
  "step_review_required",
  "book_contract_ready",
  "candidate_selection_required",
  "character_setup_required",
  "volume_strategy_ready",
]);

export async function resolveAutopilotWaitingCheckpoint(
  deps: AutopilotCheckpointResolverDeps,
  taskId: string,
): Promise<void> {
  const task = await deps.workflowService.getTaskById(taskId);
  if (!task) {
    return;
  }
  // T3.3: a paused autopilot run must not be auto-resolved by the watchdog.
  if (isAutopilotCheckpointPaused(task)) {
    return;
  }
  const checkpointType = task.checkpointType;

  if (checkpointType === "production_experience_required") {
    await deps.productionExperienceService.autoPassForAutopilot(taskId);
    return;
  }

  if (checkpointType === "replan_required") {
    await deps.commandService.enqueueContinueCommand(taskId, {
      continuationMode: "skip_quality_repair",
      forceResume: true,
    });
    return;
  }

  if (checkpointType && AUTO_EXECUTE_RANGE_CHECKPOINTS.has(checkpointType)) {
    await deps.commandService.enqueueContinueCommand(taskId, {
      continuationMode: "auto_execute_range",
      forceResume: true,
    });
    return;
  }

  // workflow_completed | quality_repair | 其它 / 缺失类型 → 无需操作
}
