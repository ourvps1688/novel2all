import type {
  AutoDirectorAttentionDetail,
  AutoDirectorAttentionItem,
  AutoDirectorAttentionListInput,
  AutoDirectorAttentionListResponse,
  AutoDirectorAttentionOverview,
} from "@ai-novel/shared/types/autoDirectorAttention";
import { prisma } from "../../../db/prisma";
import { NovelWorkflowService } from "../../novel/workflow/NovelWorkflowService";
import { NovelWorkflowTaskAdapter } from "../adapters/NovelWorkflowTaskAdapter";
import {
  getArchivedTaskIds,
  isTaskArchived,
} from "../taskArchive";
import {
  buildAvailableReasons,
  buildAvailableSections,
  buildAvailableStatuses,
  buildCounters,
  buildMilestones,
  buildSectionCounters,
  buildSummaryCounters,
  compareAttentionItems,
  decorateDetailActions,
  getReplacementTaskId,
  matchesItemFilters,
  matchesRowScopeFilters,
  normalizeWorkflowRow,
  projectAutoApprovalRecordItem,
  projectAttentionItem,
  type AttentionWorkflowRow,
  type RawAttentionWorkflowRow,
} from "./autoDirectorAttentionProjection";
import { loadRecentAutoDirectorAutoApprovalRecords } from "./autoDirectorAutoApprovalAudit";

export class AutoDirectorAttentionService {
  readonly workflowService = new NovelWorkflowService();

  private readonly workflowTaskAdapter = new NovelWorkflowTaskAdapter();

  async getOverview(): Promise<AutoDirectorAttentionOverview> {
    const rows = await this.loadRows({ heal: false });
    const knownTaskIds = new Set(rows.map((row) => row.id));
    const taskById = new Map(rows.map((row) => [row.id, row]));
    const taskItems = rows
      .map((row) => projectAttentionItem(row, knownTaskIds))
      .filter((item): item is AutoDirectorAttentionItem => Boolean(item));
    const autoApprovalItems = await this.loadAutoApprovalItems(rows, taskById);
    const items = taskItems.concat(autoApprovalItems);

    return {
      totalCount: items.length,
      countersByReason: buildCounters(items),
      countersBySection: buildSectionCounters(items),
    };
  }

  async list(input: AutoDirectorAttentionListInput = {}): Promise<AutoDirectorAttentionListResponse> {
    const rows = await this.loadRows();
    const knownTaskIds = new Set(rows.map((row) => row.id));
    const taskById = new Map(rows.map((row) => [row.id, row]));
    const scopedRows = rows.filter((row) => matchesRowScopeFilters(row, input));
    const scopedTaskItems = scopedRows
      .map((row) => projectAttentionItem(row, knownTaskIds))
      .filter((item): item is AutoDirectorAttentionItem => Boolean(item));
    const scopedItems = scopedTaskItems.concat(await this.loadAutoApprovalItems(scopedRows, taskById));
    const filteredItems = scopedItems
      .filter((item) => matchesItemFilters(item, input))
      .sort(compareAttentionItems);

    const page = Math.max(1, input.page ?? 1);
    const pageSize = Math.max(1, input.pageSize ?? 20);
    const start = (page - 1) * pageSize;

    return {
      items: filteredItems.slice(start, start + pageSize),
      countersByReason: buildCounters(filteredItems),
      countersBySection: buildSectionCounters(filteredItems),
      summaryCounters: buildSummaryCounters(scopedRows, filteredItems),
      availableFilters: {
        sections: buildAvailableSections(scopedItems),
        reasons: buildAvailableReasons(filteredItems),
        statuses: buildAvailableStatuses(filteredItems),
      },
      pagination: {
        page,
        pageSize,
        total: filteredItems.length,
      },
    };
  }

  async getDetail(taskId: string, options: { heal?: boolean } = {}): Promise<AutoDirectorAttentionDetail | null> {
    if (await isTaskArchived("novel_workflow", taskId)) {
      return null;
    }

    if (options.heal !== false) {
      await this.workflowService.healAutoDirectorTaskState(taskId);
    }

    const rawRow = await prisma.novelWorkflowTask.findUnique({
      where: { id: taskId },
      include: {
        novel: {
          select: {
            title: true,
          },
        },
      },
    }) as RawAttentionWorkflowRow | null;
    const row = rawRow ? normalizeWorkflowRow(rawRow) : null;
    if (!row) {
      return null;
    }

    const knownTaskIds = new Set([row.id]);
    const replacementTaskId = getReplacementTaskId(row.seedPayloadJson);
    if (replacementTaskId) {
      const replacement = await prisma.novelWorkflowTask.findUnique({
        where: { id: replacementTaskId },
        select: { id: true },
      });
      if (replacement) {
        knownTaskIds.add(replacement.id);
      }
    }
    const item = projectAttentionItem(row, knownTaskIds);
    if (!item) {
      return null;
    }

    const task = await this.workflowTaskAdapter.detail(taskId, {
      heal: options.heal,
    });
    if (!task) {
      return null;
    }

    const originDetailUrl = `/tasks?kind=novel_workflow&id=${taskId}`;
    const candidateSelectionUrl = item.availableActions.some((action) => action.code === "go_candidate_selection")
      ? task.sourceRoute
      : null;
    const replanUrl = item.availableActions.some((action) => action.code === "go_replan")
      ? task.sourceRoute
      : null;

    return {
      directorTaskId: taskId,
      taskId,
      reasonLabel: item.reasonLabel,
      priority: item.priority,
      attentionSummary: item.attentionSummary,
      checkpointSummary: row.checkpointSummary,
      blockingReason: item.blockingReason,
      nextStepSuggestion: task.nextActionLabel ?? task.resumeAction ?? item.availableActions[0]?.label ?? null,
      validationSummary: item.validationSummary ?? null,
      currentModel: item.currentModel,
      riskNote: null,
      originDetailUrl,
      replanUrl,
      candidateSelectionUrl,
      availableActions: decorateDetailActions({
        actions: item.availableActions,
        originDetailUrl,
        candidateSelectionUrl,
        replanUrl,
      }),
      milestones: buildMilestones(row),
      task,
    };
  }

  private async loadAutoApprovalItems(
    rows: AttentionWorkflowRow[],
    taskById: ReadonlyMap<string, AttentionWorkflowRow>,
  ): Promise<AutoDirectorAttentionItem[]> {
    const novelIds = rows
      .map((row) => row.novelId)
      .filter((novelId): novelId is string => Boolean(novelId?.trim()));
    const records = await loadRecentAutoDirectorAutoApprovalRecords(novelIds);
    return records.map((record) => projectAutoApprovalRecordItem({
      ...record,
      novel: taskById.get(record.taskId)?.novel ?? null,
    }, taskById));
  }

  private async loadRows(options: { heal?: boolean } = {}): Promise<AttentionWorkflowRow[]> {
    const archivedIds = await getArchivedTaskIds("novel_workflow");
    const rows = await this.fetchRows(archivedIds);
    if (options.heal === false) {
      return rows;
    }
    const healed = await Promise.all(
      rows.map((row) => this.workflowService.healAutoDirectorTaskState(row.id, row)),
    );
    if (!healed.some(Boolean)) {
      return rows;
    }
    return this.fetchRows(archivedIds);
  }

  private async fetchRows(archivedIds: string[]): Promise<AttentionWorkflowRow[]> {
    const rawRows = await prisma.novelWorkflowTask.findMany({
      where: {
        lane: "auto_director",
        ...(archivedIds.length > 0
          ? {
            id: {
              notIn: archivedIds,
            },
          }
          : {}),
      },
      select: {
        id: true,
        novelId: true,
        lane: true,
        title: true,
        status: true,
        currentStage: true,
        currentItemKey: true,
        currentItemLabel: true,
        checkpointType: true,
        checkpointSummary: true,
        resumeTargetJson: true,
        seedPayloadJson: true,
        milestonesJson: true,
        pendingManualRecovery: true,
        attemptCount: true,
        lastError: true,
        finishedAt: true,
        updatedAt: true,
        novel: {
          select: {
            title: true,
          },
        },
      },
      orderBy: [{ updatedAt: "desc" }, { id: "desc" }],
    }) as RawAttentionWorkflowRow[];

    return rawRows
      .map((row) => normalizeWorkflowRow(row))
      .filter((row): row is AttentionWorkflowRow => Boolean(row));
  }
}
