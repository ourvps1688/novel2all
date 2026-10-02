import type { ReactNode } from "react";
import type {
  DirectorBookAutomationAction,
  DirectorBookAutomationProjection,
} from "@ai-novel/shared/types/directorRuntime";
import { getDirectorNodeDisplayLabel } from "@ai-novel/shared/types/directorRuntime";
import {
  Activity,
  ChevronDown,
  Database,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import BookAutomationStatusBar from "./BookAutomationStatusBar";

export interface AICockpitProps {
  projection?: DirectorBookAutomationProjection | null;
  mode?: "focusedNovel";
  fallbackSummary?: string | null;
  fallbackStatusLabel?: string | null;
  isActionPending?: boolean;
  showDetailsAction?: boolean;
  onAction?: (projection: DirectorBookAutomationProjection, action: DirectorBookAutomationAction) => void;
  onOpenDetails?: (projection: DirectorBookAutomationProjection) => void;
  onOpenNovel?: (projection: DirectorBookAutomationProjection) => void;
  onOpenFallbackDetails?: () => void;
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "暂无";
  }
  return date.toLocaleString();
}

function formatTokenCount(value: number | null | undefined): string {
  const count = Math.max(0, Math.round(Number(value ?? 0)));
  return count.toLocaleString();
}

function formatDuration(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  const seconds = Math.round(value / 1000);
  if (seconds <= 0) {
    return "<1 秒";
  }
  if (seconds < 60) {
    return `${seconds} 秒`;
  }
  const minutes = Math.floor(seconds / 60);
  const restSeconds = seconds % 60;
  return restSeconds > 0 ? `${minutes} 分 ${restSeconds} 秒` : `${minutes} 分`;
}

function formatUsageLine(usage: {
  llmCallCount: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  durationMs?: number | null;
}): string {
  const duration = formatDuration(usage.durationMs);
  return [
    `${formatTokenCount(usage.llmCallCount)} 次调用`,
    `输入 ${formatTokenCount(usage.promptTokens)}`,
    `输出 ${formatTokenCount(usage.completionTokens)}`,
    `总计 ${formatTokenCount(usage.totalTokens)} Tokens`,
    duration ? `累计调用耗时 ${duration}` : null,
  ].filter(Boolean).join(" · ");
}

function artifactTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    book_contract: "书级约定",
    story_macro: "故事规划",
    character_cast: "角色",
    volume_strategy: "分卷",
    chapter_task_sheet: "任务单",
    chapter_draft: "正文",
    audit_report: "审校",
    repair_ticket: "修复",
    reader_promise: "读者承诺",
    character_governance_state: "角色状态",
    world_skeleton: "世界框架",
    source_knowledge_pack: "资料包",
    chapter_retention_contract: "留存约定",
    continuity_state: "连续性",
    rolling_window_review: "近期复盘",
  };
  return labels[type] ?? type;
}

function recoveryActionLabel(
  action: NonNullable<DirectorBookAutomationProjection["circuitBreaker"]>["recoveryAction"],
): string | null {
  const labels: Record<string, string> = {
    retry: "重试当前步骤",
    resume_after_review: "查看原因后继续",
    switch_model: "切换模型后继续",
    confirm_protected_content: "确认保护内容边界",
    manual_repair: "先处理章节问题",
  };
  return action ? labels[action] ?? null : null;
}

function workerStateLabel(
  state: NonNullable<DirectorBookAutomationProjection["workerHealth"]>["derivedState"],
): string {
  const labels: Record<NonNullable<DirectorBookAutomationProjection["workerHealth"]>["derivedState"], string> = {
    idle: "还没开始自动写作",
    queued_waiting_worker: "马上接着写",
    leased_starting: "正在开始写",
    running_step: "正在自动写作",
    waiting_gate: "等你确认后继续",
    auto_recovering: "正在接着上次没写完的写",
    cancelled: "已停止自动写作",
    failed_recoverable: "遇到问题，会自己重试",
    failed_hard: "需要你处理一下",
    succeeded: "已完成",
  };
  return labels[state] ?? state;
}

function workerStateDetail(health: NonNullable<DirectorBookAutomationProjection["workerHealth"]>): string {
  if (health.message?.trim()) {
    return health.message.trim();
  }
  if (health.queuedCommandCount > 0) {
    return "前面还有几步，轮到这本书会继续写。";
  }
  if (health.runningCommandCount > 0 || health.leasedCommandCount > 0) {
    return "正在写当前内容，写完会自动往下推进。";
  }
  if (health.staleCommandCount > 0) {
    return "中途断掉的内容会从上次写到的地方接着写。";
  }
  return "当前没有正在自动写作的内容。";
}

function SummaryMetric(props: {
  label: string;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted-foreground">{props.label}</div>
      <div className={cn("mt-1 truncate text-sm font-medium text-foreground", props.className)}>
        {props.value}
      </div>
    </div>
  );
}

function DetailPanel(props: {
  title: string;
  summary?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="group rounded-2xl bg-muted/25">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-foreground [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 items-center gap-2">
          {props.icon ? <span className="shrink-0 text-muted-foreground">{props.icon}</span> : null}
          <span className="truncate">{props.title}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-xs font-normal text-muted-foreground">
          {props.summary}
          <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
        </span>
      </summary>
      <div className="px-4 pb-4 pt-1">
        {props.children}
      </div>
    </details>
  );
}

export default function AICockpit(props: AICockpitProps) {
  const {
    fallbackStatusLabel,
    isActionPending = false,
    showDetailsAction = true,
    onAction,
    onOpenDetails,
    onOpenNovel,
    onOpenFallbackDetails,
  } = props;
  const focusProjection = props.projection ?? null;

  if (!focusProjection) {
    return (
      <BookAutomationStatusBar
        variant="banner"
        projection={null}
        fallbackSummary={props.fallbackSummary ?? null}
        fallbackStatusLabel={fallbackStatusLabel}
        onOpenFallbackDetails={onOpenFallbackDetails}
      />
    );
  }

  const recentItems = focusProjection.timeline.slice(0, 3);
  const artifactRows = focusProjection.artifactSummary.byType?.slice(0, 3) ?? [];
  const usageSummary = focusProjection.usageSummary ?? null;
  const stepUsage = focusProjection.stepUsage?.slice(0, 2) ?? [];
  const promptUsage = focusProjection.promptUsage?.slice(0, 6) ?? [];
  const circuitBreaker = focusProjection.circuitBreaker?.status === "open" ? focusProjection.circuitBreaker : null;
  const circuitRecovery = recoveryActionLabel(circuitBreaker?.recoveryAction ?? null);
  const workerHealth = focusProjection.workerHealth ?? null;
  const artifactInsightLines = [
    focusProjection.artifactSummary.affectedChapterCount
      ? `影响 ${focusProjection.artifactSummary.affectedChapterCount} 个章节`
      : null,
    focusProjection.artifactSummary.recentStaleArtifacts?.length
      ? `${focusProjection.artifactSummary.recentStaleArtifacts.length} 个产物需复核`
      : null,
    focusProjection.artifactSummary.recentRepairArtifacts?.length
      ? `${focusProjection.artifactSummary.recentRepairArtifacts.length} 条修复记录`
      : null,
    focusProjection.artifactSummary.recentVersionedArtifacts?.length
      ? `${focusProjection.artifactSummary.recentVersionedArtifacts.length} 个产物有新版本`
      : null,
  ].filter((line): line is string => Boolean(line));

  return (
    <div className="space-y-4">
      <BookAutomationStatusBar
        variant="banner"
        projection={focusProjection}
        isActionPending={isActionPending}
        showDetailsAction={showDetailsAction}
        onAction={onAction}
        onOpenDetails={onOpenDetails}
        onOpenNovel={onOpenNovel}
        fallbackSummary={props.fallbackSummary ?? null}
        fallbackStatusLabel={fallbackStatusLabel}
      />

      {circuitBreaker ? (
        <section className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm leading-6 text-destructive">
          <div className="font-medium">自动推进已暂停</div>
          <div className="mt-1">{circuitBreaker.message || "系统检测到继续自动推进可能反复失败。"}</div>
          {circuitRecovery ? <div className="mt-1">建议：{circuitRecovery}。</div> : null}
        </section>
      ) : null}

      {workerHealth ? (
        <section className="rounded-2xl bg-muted/25 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Database className="h-4 w-4 text-muted-foreground" />
              自动写作状态
            </div>
            <span className="text-xs text-muted-foreground">{workerStateLabel(workerHealth.derivedState)}</span>
          </div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">{workerStateDetail(workerHealth)}</div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <SummaryMetric label="待写内容" value={workerHealth.queuedCommandCount} />
            <SummaryMetric label="正在写" value={workerHealth.runningCommandCount + workerHealth.leasedCommandCount} />
          </div>
          {workerHealth.oldestQueuedWaitMs ? (
            <div className="mt-2 text-[11px] text-muted-foreground">
              已等待 {formatDuration(workerHealth.oldestQueuedWaitMs) ?? "<1 秒"}
            </div>
          ) : null}
        </section>
      ) : null}

      {artifactRows.length > 0 ? (
        <section className="rounded-2xl bg-muted/25 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Database className="h-4 w-4 text-muted-foreground" />
              产物记录
            </div>
            {artifactInsightLines.length > 0 ? (
              <span className="text-xs text-muted-foreground">{artifactInsightLines[0]}</span>
            ) : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-xs text-muted-foreground">
            {artifactRows.map((item) => (
              <span key={item.artifactType}>
                <span className="font-medium text-foreground">{artifactTypeLabel(String(item.artifactType))}</span>
                <span className="ml-1">{item.activeCount}/{item.totalCount}</span>
              </span>
            ))}
          </div>
          {artifactInsightLines.length > 1 ? (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              {artifactInsightLines.slice(1).map((line) => (
                <span key={line}>{line}</span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {usageSummary ? (
        <DetailPanel
          title="AI 用量"
          summary={`${formatTokenCount(usageSummary.llmCallCount)} 次 · ${formatTokenCount(usageSummary.totalTokens)} Tokens`}
          icon={<Activity className="h-4 w-4" />}
        >
          <div className="space-y-3 text-xs leading-5 text-muted-foreground">
            <div>{formatUsageLine(usageSummary)}</div>
            {promptUsage.length > 0 ? (
              <div className="space-y-1">
                <div className="font-medium text-foreground">阶段用量</div>
                <div className="divide-y divide-border/60">
                  {promptUsage.map((item) => (
                    <div key={`${item.promptAssetKey}:${item.promptVersion ?? ""}:${item.nodeKey ?? ""}`} className="grid gap-1 py-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                      <span className="min-w-0 truncate text-foreground">
                        {getDirectorNodeDisplayLabel({ label: item.label ?? item.promptAssetKey, nodeKey: item.nodeKey })}
                      </span>
                      <span>{formatUsageLine(item)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {stepUsage.length > 0 ? (
              <div className="space-y-1">
                <div className="font-medium text-foreground">推进步骤</div>
                <div className="divide-y divide-border/60">
                  {stepUsage.map((item) => (
                    <div key={item.stepIdempotencyKey} className="grid gap-1 py-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                      <span className="min-w-0 truncate text-foreground">
                        {getDirectorNodeDisplayLabel({ label: item.label, nodeKey: item.nodeKey })}
                      </span>
                      <span>{formatUsageLine(item)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </DetailPanel>
      ) : null}

      {recentItems.length > 0 ? (
        <DetailPanel
          title="自动化记录"
          summary={`${recentItems.length} 条`}
          icon={<History className="h-4 w-4" />}
        >
          <div className="divide-y divide-border/60 text-xs leading-5">
            {recentItems.map((item) => (
              <div key={item.id} className="py-2">
                <div className="line-clamp-2 text-foreground">{item.title}</div>
                {item.usage ? (
                  <div className="mt-1 text-muted-foreground">{formatUsageLine(item.usage)}</div>
                ) : item.durationMs ? (
                  <div className="mt-1 text-muted-foreground">耗时 {formatDuration(item.durationMs)}</div>
                ) : null}
                <div className="mt-1 text-muted-foreground">{formatDate(item.occurredAt)}</div>
              </div>
            ))}
          </div>
        </DetailPanel>
      ) : null}
    </div>
  );
}
