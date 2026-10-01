import { prisma } from "../../../db/prisma";
import type { DirectorAttentionState, DirectorAttentionLevel } from "@ai-novel/shared/types/directorAttention";
import type { DirectorBookAutomationProjection } from "@ai-novel/shared/types/directorRuntime";
import { DirectorBookAutomationProjectionService } from "./projections/DirectorBookAutomationProjectionService";

// Normalize the projection into a single client-facing attention state.
// Level is derived ONLY from task-derived fields (status / requiresUserAction /
// workerHealth.derivedState), never from the dead DirectorRuntimeInstance.status.
function mapAttentionLevel(projection: DirectorBookAutomationProjection): DirectorAttentionLevel {
  const status = projection.status;
  const derivedState = projection.workerHealth?.derivedState;
  if (status === "waiting_approval") return "waiting_approval";
  if (status === "waiting_recovery" || status === "blocked" || status === "failed") return "needs_recovery";
  if (derivedState === "auto_recovering") return "auto_recovering";
  if (status === "running" || status === "queued") return "running";
  return "idle";
}

export function mapProjectionToAttention(projection: DirectorBookAutomationProjection): DirectorAttentionState {
  const level = mapAttentionLevel(projection);
  return {
    novelId: projection.novelId,
    novelTitle: projection.focusNovel?.title ?? null,
    level,
    headline: projection.headline,
    detail: projection.detail ?? projection.blockedReason ?? null,
    requiresUserAction: projection.requiresUserAction,
    primaryAction: projection.primaryAction ?? null,
    fallbackActions: projection.secondaryActions ?? [],
    updatedAt: projection.updatedAt,
  };
}

export class DirectorAttentionService {
  constructor(
    private readonly projectionService: DirectorBookAutomationProjectionService = new DirectorBookAutomationProjectionService(),
  ) {}

  async getAttention(novelId: string): Promise<DirectorAttentionState | null> {
    const novel = await prisma.novel.findUnique({ where: { id: novelId }, select: { id: true } });
    if (!novel) return null;
    const projection = await this.projectionService.getProjection(novelId);
    return mapProjectionToAttention(projection);
  }

  async listAttentions(limit = 50): Promise<DirectorAttentionState[]> {
    // `pendingManualRecovery: true` is the strongest "needs recovery" signal on the
    // task row itself; the projection promotes it to status "waiting_recovery"
    // regardless of the base task status, so it MUST be included here even though
    // "waiting_recovery" is not a valid NovelWorkflowTaskStatus enum value.
    const rows = await prisma.novelWorkflowTask.findMany({
      where: {
        lane: "auto_director",
        OR: [
          { status: { in: ["queued", "running", "waiting_approval", "failed"] } },
          { pendingManualRecovery: true },
        ],
      },
      orderBy: { updatedAt: "desc" },
      take: 200,
      select: { novelId: true, updatedAt: true },
    });
    const latestByNovel = new Map<string, Date>();
    for (const row of rows) {
      if (!row.novelId) continue;
      const existing = latestByNovel.get(row.novelId);
      if (!existing || row.updatedAt.getTime() > existing.getTime()) {
        latestByNovel.set(row.novelId, row.updatedAt);
      }
    }
    const novelIds = [...latestByNovel.keys()].slice(0, limit);
    const attentions: DirectorAttentionState[] = [];
    for (const novelId of novelIds) {
      const projection = await this.projectionService.getProjection(novelId);
      const attention = mapProjectionToAttention(projection);
      if (attention.level !== "idle") {
        attentions.push(attention);
      }
    }
    return attentions;
  }
}

export const directorAttentionService = new DirectorAttentionService();
