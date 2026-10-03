import type { PrismaClient } from "@prisma/client";
import type { NovelWorkflowService } from "../../workflow/NovelWorkflowService";
import { prisma as defaultPrisma } from "../../../../db/prisma";
import { parseSeedPayload } from "../../workflow/novelWorkflow.shared";
import {
  resolveAutopilotWaitingCheckpoint,
  isAutopilotCheckpointPaused,
  type AutopilotCheckpointResolverDeps,
} from "./autopilotCheckpointResolver";

const DEFAULT_INTERVAL_MS = 60000;

export interface AutopilotCheckpointWatchdogDeps {
  prisma?: PrismaClient;
  resolve?: (taskId: string) => Promise<void>;
  workflowService?: AutopilotCheckpointResolverDeps["workflowService"];
  commandService?: AutopilotCheckpointResolverDeps["commandService"];
  productionExperienceService?: AutopilotCheckpointResolverDeps["productionExperienceService"];
}

/**
 * 独立看门狗：定时扫描任务表，把所有处于 `waiting_approval` 的 full_book_autopilot 任务
 * 交给 resolveAutopilotWaitingCheckpoint 程序化解析，确保没有任何人工关卡能死锁全自动运行。
 *
 * 镜像 NovelPipelineRuntimeService.startWatchdog 的设计：
 *  - 防重复启动（timer 已存在则直接返回）
 *  - setInterval + .unref?.()
 *  - 单次扫描异常仅 console.warn，不影响后续 tick
 */
export class AutopilotCheckpointWatchdog {
  private timer: NodeJS.Timeout | null = null;
  private resolveImpl: ((taskId: string) => Promise<void>) | null = null;

  constructor(private readonly deps: AutopilotCheckpointWatchdogDeps = {}) {}

  private getPrisma(): PrismaClient {
    return this.deps.prisma ?? defaultPrisma;
  }

  private getResolve(): (taskId: string) => Promise<void> {
    if (this.deps.resolve) {
      return this.deps.resolve;
    }
    if (this.resolveImpl) {
      return this.resolveImpl;
    }
    // 延迟加载具体服务，避免模块加载期的循环依赖 / 重型依赖链在测试环境中被触发。
    // 生产环境下只有未注入 resolve 时才会走到这里。
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { NovelWorkflowService } = require("../../workflow/NovelWorkflowService") as typeof import("../../workflow/NovelWorkflowService");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { DirectorCommandService } = require("../commands/DirectorCommandService") as typeof import("../commands/DirectorCommandService");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { DirectorProductionExperienceService } = require("../commands/DirectorProductionExperienceService") as typeof import("../commands/DirectorProductionExperienceService");
    const resolverDeps: AutopilotCheckpointResolverDeps = {
      workflowService: this.deps.workflowService ?? new NovelWorkflowService(),
      commandService: this.deps.commandService ?? new DirectorCommandService(),
      productionExperienceService:
        this.deps.productionExperienceService ?? new DirectorProductionExperienceService(),
    };
    this.resolveImpl = (taskId: string) => resolveAutopilotWaitingCheckpoint(resolverDeps, taskId);
    return this.resolveImpl;
  }

  /** 执行一次扫描：返回被成功解析的任务 id 列表。 */
  async scanOnce(): Promise<string[]> {
    const rows = await this.getPrisma().novelWorkflowTask.findMany({
      where: {
        lane: "auto_director",
        status: "waiting_approval",
        pendingManualRecovery: false,
      },
    });
    const resolved: string[] = [];
    for (const row of rows) {
      // T3.3: a paused autopilot run (waiting_approval + pendingManualRecovery) must never be
      // auto-resolved. The findMany query already filters pendingManualRecovery:false, but we
      // guard here as well so any caller handing in rows is also protected.
      if (isAutopilotCheckpointPaused(row)) {
        continue;
      }
      const runMode = parseSeedPayload<{ runMode?: string }>(row.seedPayloadJson)?.runMode;
      if (runMode !== "full_book_autopilot") {
        continue;
      }
      try {
        await this.getResolve()(row.id);
        resolved.push(row.id);
      } catch (error) {
        console.warn(`Autopilot checkpoint resolver failed for task ${row.id}.`, error);
      }
    }
    return resolved;
  }

  startWatchdog({ intervalMs }: { intervalMs?: number } = {}): void {
    if (this.timer) {
      return;
    }
    const interval = intervalMs ?? DEFAULT_INTERVAL_MS;
    this.timer = setInterval(() => {
      void this.scanOnce().catch((error) => {
        console.warn("Autopilot checkpoint watchdog tick failed.", error);
      });
    }, interval);
    this.timer.unref?.();
  }

  stopWatchdog(): void {
    if (!this.timer) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
  }
}
