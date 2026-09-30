import type {
  NovelWorkflowLane,
  NovelWorkflowMilestone,
  NovelWorkflowMilestoneType,
  NovelWorkflowResumeTarget,
} from "@ai-novel/shared/types/novelWorkflow";
import { getNovelWorkflowLaneDescriptor } from "@ai-novel/shared/types/novelWorkflow";

export function buildNovelCreateResumeTarget(taskId: string, mode: "director" | null = null): NovelWorkflowResumeTarget {
  return {
    route: "/novels/create",
    lane: mode === "director" ? "auto_director" : "manual_create",
    taskId,
    mode,
  };
}

export function buildCreationStudioResumeTarget(taskId: string): NovelWorkflowResumeTarget {
  return {
    route: "/create",
    taskId,
    lane: "creation_studio",
  };
}

export function buildShortStoryResumeTarget(novelId: string, taskId?: string | null): NovelWorkflowResumeTarget {
  return {
    route: "/novels/:id/story",
    novelId,
    taskId: taskId ?? null,
    lane: "creation_studio",
  };
}

export function buildNovelEditResumeTarget(params: {
  novelId: string;
  taskId?: string | null;
  lane?: NovelWorkflowResumeTarget["lane"];
  stage: NovelWorkflowResumeTarget["stage"];
  chapterId?: string | null;
  volumeId?: string | null;
}): NovelWorkflowResumeTarget {
  return composeResumeTarget({
    lane: params.lane ?? "auto_director",
    novelId: params.novelId,
    taskId: params.taskId,
    stage: params.stage,
    chapterId: params.chapterId,
    volumeId: params.volumeId,
  });
}

export function composeResumeTarget(input: {
  lane: NovelWorkflowLane;
  route?: NovelWorkflowResumeTarget["route"];
  novelId?: string | null;
  taskId?: string | null;
  workspaceTaskId?: string | null;
  directorTaskId?: string | null;
  stage?: NovelWorkflowResumeTarget["stage"] | null;
  chapterId?: string | null;
  volumeId?: string | null;
  mode?: "director" | null;
}): NovelWorkflowResumeTarget {
  const descriptor = getNovelWorkflowLaneDescriptor(input.lane);
  const taskId =
    input.taskId
    ?? (descriptor.taskQueryKey === "workspaceTaskId" ? input.workspaceTaskId : null)
    ?? (descriptor.taskQueryKey === "directorTaskId" ? input.directorTaskId : null)
    ?? null;
  return {
    route: input.route ?? "/novels/:id/edit",
    lane: input.lane,
    novelId: input.novelId ?? null,
    taskId,
    stage: input.stage ?? undefined,
    chapterId: input.chapterId ?? null,
    volumeId: input.volumeId ?? null,
    mode: input.mode ?? null,
  };
}

export function resumeTargetToRoute(target: NovelWorkflowResumeTarget | null | undefined): string {
  if (!target) {
    return "/tasks";
  }
  if (target.route === "/create") {
    return target.taskId ? `/create?taskId=${encodeURIComponent(target.taskId)}` : "/create";
  }
  if (target.route === "/novels/create") {
    if (target.mode === "director") {
      const searchParams = new URLSearchParams();
      if (target.taskId) {
        searchParams.set("taskId", target.taskId);
      }
      const query = searchParams.toString();
      return query ? `/novels/auto-director?${query}` : "/novels/auto-director";
    }
    const searchParams = new URLSearchParams();
    if (target.taskId) {
      searchParams.set("workflowTaskId", target.taskId);
    }
    if (target.mode) {
      searchParams.set("mode", target.mode);
    }
    const query = searchParams.toString();
    return query ? `/novels/create?${query}` : "/novels/create";
  }

  if (!target.novelId) {
    return "/tasks";
  }

  if (target.route === "/novels/:id/story") {
    return `/novels/${target.novelId}/story`;
  }

  const searchParams = new URLSearchParams();
  if (target.stage) {
    searchParams.set("stage", target.stage);
  }
  if (target.taskId) {
    if (target.lane === "manual_create") {
      searchParams.set("workspaceTaskId", target.taskId);
    } else {
      searchParams.set("directorTaskId", target.taskId);
    }
  }
  if (target.chapterId) {
    searchParams.set("chapterId", target.chapterId);
  }
  if (target.volumeId) {
    searchParams.set("volumeId", target.volumeId);
  }
  const query = searchParams.toString();
  return query ? `/novels/${target.novelId}/edit?${query}` : `/novels/${target.novelId}/edit`;
}

export function parseMilestones(value: string | null | undefined): NovelWorkflowMilestone[] {
  if (!value?.trim()) {
    return [];
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((item): item is NovelWorkflowMilestone => (
        Boolean(item)
        && typeof item === "object"
        && typeof (item as NovelWorkflowMilestone).checkpointType === "string"
        && typeof (item as NovelWorkflowMilestone).summary === "string"
        && typeof (item as NovelWorkflowMilestone).createdAt === "string"
      ));
  } catch {
    return [];
  }
}

export function appendMilestone(
  existing: string | null | undefined,
  checkpointType: NovelWorkflowMilestoneType,
  summary: string,
): string {
  const next = [
    ...parseMilestones(existing).filter((item) => item.checkpointType !== checkpointType),
    {
      checkpointType,
      summary,
      createdAt: new Date().toISOString(),
    },
  ];
  return JSON.stringify(next);
}

export function parseResumeTarget(value: string | null | undefined): NovelWorkflowResumeTarget | null {
  if (!value?.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as NovelWorkflowResumeTarget;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function stringifyResumeTarget(value: NovelWorkflowResumeTarget | null | undefined): string | null {
  return value ? JSON.stringify(value) : null;
}

export function parseSeedPayload<T>(value: string | null | undefined): T | null {
  if (!value?.trim()) {
    return null;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

export function mergeSeedPayload<T extends Record<string, unknown>>(
  existing: string | null | undefined,
  patch: Partial<T>,
): string {
  const current = parseSeedPayload<T>(existing) ?? {} as T;
  return JSON.stringify({
    ...current,
    ...patch,
  });
}

export function defaultWorkflowTitle(input: {
  lane: NovelWorkflowLane;
  title?: string | null;
  novelTitle?: string | null;
}): string {
  const novelTitle = input.novelTitle?.trim() || input.title?.trim();
  if (novelTitle) {
    return novelTitle;
  }
  return getNovelWorkflowLaneDescriptor(input.lane).defaultTitle;
}
