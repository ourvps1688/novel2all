import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  MarketCreativeBrief,
  MarketInfluenceMode,
  MarketRadarSignal,
} from "@ai-novel/shared/types/marketRadar";
import { createMarketCreativeBrief, getLatestMarketRadarScan } from "@/api/marketRadar";
import { queryKeys } from "@/api/queryKeys";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<MarketRadarSignal["kind"], string> = {
  genre: "热门题材",
  protagonist: "主角身份",
  advantage: "金手指",
  opening: "开局爆点",
  relationship: "关系卖点",
  title_pattern: "标题句式",
  opportunity: "差异化机会",
  crowding: "拥挤套路",
};

const MODE_LABELS: Record<MarketInfluenceMode, string> = {
  follow_hot: "跟随热门",
  differentiate: "热门中求差异",
  light: "弱化市场",
};

function recommendedSignalIds(report: { signals: MarketRadarSignal[] }): string[] {
  const recommended = report.signals.filter((signal) => signal.recommended);
  const opportunity = recommended.find((signal) => signal.kind === "opportunity");
  return [opportunity, ...recommended.filter((signal) => signal.id !== opportunity?.id)]
    .filter(Boolean)
    .slice(0, 4)
    .map((signal) => signal!.id);
}

interface MarketRadarInlinePanelProps {
  /** 当前简报；用于预选已勾选信号。无简报时按榜单推荐预选。 */
  brief: MarketCreativeBrief | null;
  /** 生成新简报后回调，由父组件写回 URL 的 ?marketBriefId= 以完成往返。 */
  onBriefCreated: (briefId: string) => void;
  onClose: () => void;
}

export default function MarketRadarInlinePanel({
  brief,
  onBriefCreated,
  onClose,
}: MarketRadarInlinePanelProps) {
  const latestScanQuery = useQuery({
    queryKey: queryKeys.marketRadar.latest,
    queryFn: getLatestMarketRadarScan,
  });
  const report = latestScanQuery.data?.data?.report ?? null;
  const signals = useMemo(() => report?.signals ?? [], [report]);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [influenceMode, setInfluenceMode] = useState<MarketInfluenceMode>(
    brief?.influenceMode ?? "differentiate",
  );

  // 预选：优先沿用当前简报已勾选信号，否则按榜单推荐预选。
  useEffect(() => {
    if (signals.length === 0) return;
    if (brief?.selectedSignals?.length) {
      setSelectedIds(brief.selectedSignals.map((signal) => signal.id));
    } else if (report) {
      setSelectedIds(recommendedSignalIds(report));
    }
    // 仅当榜单报告或简报切换时重新预选
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.id, brief?.id]);

  const toggle = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id],
    );
  };

  const createBriefMutation = useMutation({
    mutationFn: () =>
      createMarketCreativeBrief({ reportId: report!.id, signalIds: selectedIds, influenceMode }),
    onSuccess: (response) => {
      if (response.data) {
        toast.success("已生成新的市场创作方向。");
        onBriefCreated(response.data.id);
        onClose();
      }
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "生成市场创作简报失败。"),
  });

  if (latestScanQuery.isPending) {
    return (
      <div className="mt-3 rounded-lg bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        正在读取热门题材榜单…
      </div>
    );
  }

  if (!report || signals.length === 0) {
    return (
      <div className="mt-3 flex items-center justify-between gap-3 rounded-lg bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <span>市场简报暂时无法读取，仍可继续按你的想法开书。</span>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          收起
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg bg-muted/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-foreground">挑选想参考的热门信号</div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">市场策略</span>
          <select
            value={influenceMode}
            onChange={(event) => setInfluenceMode(event.target.value as MarketInfluenceMode)}
            className="rounded-md border border-border bg-background px-2 py-1 text-sm"
          >
            {(Object.keys(MODE_LABELS) as MarketInfluenceMode[]).map((mode) => (
              <option key={mode} value={mode}>
                {MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {signals.map((signal) => {
          const active = selectedIds.includes(signal.id);
          return (
            <button
              key={signal.id}
              type="button"
              onClick={() => toggle(signal.id)}
              aria-pressed={active}
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-foreground hover:bg-muted",
              )}
            >
              <span className="mr-1 text-xs opacity-70">{KIND_LABELS[signal.kind]}</span>
              {signal.label}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between gap-3 pt-1">
        <span className="text-xs text-muted-foreground">已选 {selectedIds.length} 项信号</span>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={selectedIds.length === 0 || createBriefMutation.isPending}
            onClick={() => createBriefMutation.mutate()}
          >
            {createBriefMutation.isPending ? "生成中…" : "用这些信号开书"}
          </Button>
        </div>
      </div>
    </div>
  );
}
