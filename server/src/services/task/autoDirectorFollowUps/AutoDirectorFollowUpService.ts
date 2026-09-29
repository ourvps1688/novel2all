import type {
  AutoDirectorFollowUpDetail,
  AutoDirectorFollowUpItem,
  AutoDirectorFollowUpListInput,
  AutoDirectorFollowUpListResponse,
  AutoDirectorFollowUpOverview,
} from "@ai-novel/shared/types/autoDirectorFollowUp";
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
  compareFollowUpItems,
  decorateDetailActions,
  getReplacementTaskId,
  matchesItemFilters,
  matchesRowScopeFilters,
  normalizeWorkflowRow,
  projectAutoApprovalRecordItem,
  projectFollowUpItem,
  type FollowUpWorkflowRow,
  type RawFollowUpWorkflowRow,
} from "./autoDirectorFollowUpProjection";
import { loadRecentAutoDirectorAutoApprovalRecords } from "./autoDirectorAutoApprovalAudit";

export class AutoDirectorFollowUpService {
  readonly workflowService = new NovelWorkflowService();

  private readonly workflowTaskAdapter = new NovelWorkflowTaskAdapter();

  async getOverview(): Promise<AutoDirectorFollowUpOverview> {
    const rows = await this.loadRows({ heal: false });
    const knownTaskIds = new Set(rows.map((row) => row.id));
    const taskById = new Map(rows.map((row) => [row.id, row]));
    const taskItems = rows
      .map((row) => projectFollowUpItem(row, knownTaskIds))
      .filter((item): item is AutoDirectorFollowUpItem => Boolean(item));
    const autoApprovalItems = await this.loadAutoApprovalItems(rows, taskById);
    const items = taskItems.concat(autoApprovalItems);

    return {
      totalCount: items.length,
      countersByReason: buildCounters(items),
      countersBySection: buildSectionCounters(items),
    };
  }

  async list(input: AutoDirectorFollowUpListInput = {}): Promise<AutoDirectorFollowUpListResponse> {
    const rows = await this.loadRows();
    const knownTaskIds = new Set(rows.map((row) => row.id));
    const taskById = new Map(rows.map((row) => [row.id, row]));
    const scopedRows = rows.filter((row) => matchesRowScopeFilters(row, input));
    const scopedTaskItems = scopedRows
      .map((row) => projectFollowUpItem(row, knownTaskIds))
      .filter((item): item is AutoDirectorFollowUpItem => Boolean(item));
    const scopedItems = scopedTaskItems.concat(await this.loadAutoApprovalItems(scopedRows, taskById));
    const filteredItems = scopedItems
      .filter((item) => matchesItemFilters(item, input))
      .sort(compareFollowUpItems);

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

  async getDetail(taskId: string, options: { heal?: boolean } = {}): Promise<AutoDirectorFollowUpDetail | null> {
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
    }) as RawFollowUpWorkflowRow | null;
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
    const item = projectFollowUpItem(row, knownTaskIds);
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
      followUpSummary: item.followUpSummary,
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
    rows: FollowUpWorkflowRow[],
    taskById: ReadonlyMap<string, FollowUpWorkflowRow>,
  ): Promise<AutoDirectorFollowUpItem[]> {
    const novelIds = rows
      .map((row) => row.novelId)
      .filter((novelId): novelId is string => Boolean(novelId?.trim()));
    const records = await loadRecentAutoDirectorAutoApprovalRecords(novelIds);
    return records.map((record) => projectAutoApprovalRecordItem({
      ...record,
      novel: taskById.get(record.taskId)?.novel ?? null,
    }, taskById));
  }

  private async loadRows(options: { heal?: boolean } = {}): Promise<FollowUpWorkflowRow[]> {
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

  private async fetchRows(archivedIds: string[]): Promise<FollowUpWorkflowRow[]> {
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
    }) as RawFollowUpWorkflowRow[];

    return rawRows
      .map((row) => normalizeWorkflowRow(row))
      .filter((row): row is FollowUpWorkflowRow => Boolean(row));
  }
}
