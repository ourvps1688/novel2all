import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { DirectorBookAutomationAction } from "@ai-novel/shared/types/directorRuntime";
import { continueDirectorRuntime } from "@/api/novelDirector";
import {
  getDirectorContinuationMode,
  isDirectorContinuationAction,
} from "@/lib/directorContinuationActions";
import { queryKeys } from "@/api/queryKeys";
import { toast } from "@/components/ui/toast";

type NavigateFn = (href: string) => void;
type InvalidateFn = () => void | Promise<void>;

/**
 * The single allowed normalization point for Phase 5-B (T4).
 *
 * It maps a `DirectorBookAutomationActionType` to the project's *existing*
 * recovery handlers (`continueDirectorRuntime`, `approveDirectorGate`) and their
 * shared helpers (`isDirectorContinuationAction`,
 * `getDirectorContinuationMode`). Action types without a headless handler
 * fall back to the deep link the server already prepared in
 * `action.target.href`. No new ad-hoc fetch path or string→branch table is
 * introduced here.
 */
export async function executeDirectorAttentionAction(
  navigate: NavigateFn,
  invalidate: InvalidateFn,
  action: DirectorBookAutomationAction,
): Promise<void> {
  const taskId = action.commandPayload?.taskId ?? action.target.taskId ?? null;

  if (taskId && isDirectorContinuationAction(action)) {
    await continueDirectorRuntime(taskId, {
      continuationMode: getDirectorContinuationMode(action) ?? "resume",
    });
    await invalidate();
    return;
  }

  const href = action.target.href?.trim();
  if (href) {
    if (/^https?:\/\//i.test(href)) {
      window.location.assign(href);
    } else {
      navigate(href);
    }
    return;
  }

  toast.error("该操作没有可用的处理方式，请打开小说查看详情。");
}

/**
 * Hook that returns a bound executor suitable for `DirectorAttentionCenter`'s
 * `onAction` / primary-action binding. It ties the normalized action mapping to
 * the app router and query cache so recovery commands refresh the attention UI.
 */
export function useDirectorAttentionActionExecutor() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  return useCallback(
    (action: DirectorBookAutomationAction) => {
      const invalidate = () => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.directorAttentions.all });
      };
      return executeDirectorAttentionAction(navigate, invalidate, action).catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : "操作执行失败。");
      });
    },
    [navigate, queryClient],
  );
}
