import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Archive, ArrowRight, BookOpenCheck, Bot, Database } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import {
  getAPIKeySettings,
  getModelRoutes,
  getRagSettings,
  getStyleEngineRuntimeSettings,
  testModelRouteConnectivity,
} from "@/api/settings";
import { queryKeys } from "@/api/queryKeys";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import SettingsReadinessCard, { buildSettingsReadinessItems } from "../components/SettingsReadinessCard";
import { SettingsShell } from "../components/SettingsShell";

interface SettingsOverviewSummaryContext {
  configuredProviderName: string | null;
  configuredProviderModel: string | null;
  routeCount: number;
  ragEnabled: boolean;
  ragEmbeddingModel: string | null;
}

const entries: Array<{
  to: string;
  title: string;
  description: string;
  icon: LucideIcon;
  summary: (context: SettingsOverviewSummaryContext) => string;
}> = [
  {
    to: "/settings/models",
    title: "模型与供应商",
    description: "接一个能写正文的模型，并指定哪些创作步骤用它。",
    icon: Bot,
    summary: (context) => {
      if (!context.configuredProviderName) {
        return "还没接上模型，接上就能开始写";
      }
      const base = `${context.configuredProviderName} · ${context.configuredProviderModel || "未选择模型"}`;
      return context.routeCount > 0 ? `${base} · 已指定 ${context.routeCount} 个创作步骤` : base;
    },
  },
  {
    to: "/settings/director",
    title: "自动导演",
    description: "安排问题处理、确认偏好与提醒方式。",
    icon: BookOpenCheck,
    summary: () => "设置确认偏好、问题处理和通知方式",
  },
  {
    to: "/settings/knowledge",
    title: "知识库与写法",
    description: "让资料和写法偏好参与后续创作。",
    icon: Database,
    summary: (context) => (context.ragEnabled
      ? `资料检索已开启 · ${context.ragEmbeddingModel || "未选择向量模型"}`
      : "可选增强，暂不影响开始创作"),
  },
  {
    to: "/settings/maintenance",
    title: "数据与备份",
    description: "需要备份或迁移数据时，查看要保留哪些文件。",
    icon: Archive,
    summary: () => "更新由部署环境处理，数据文件需要自己保留",
  },
];

export default function SettingsOverviewPage() {
  const providersQuery = useQuery({ queryKey: queryKeys.settings.apiKeys, queryFn: getAPIKeySettings });
  const routesQuery = useQuery({ queryKey: queryKeys.settings.modelRoutes, queryFn: getModelRoutes });
  const connectivityQuery = useQuery({
    queryKey: queryKeys.settings.modelRouteConnectivity,
    queryFn: testModelRouteConnectivity,
    enabled: routesQuery.isSuccess,
    refetchOnWindowFocus: false,
  });
  const ragQuery = useQuery({ queryKey: queryKeys.settings.rag, queryFn: getRagSettings });
  const styleQuery = useQuery({ queryKey: queryKeys.settings.styleEngineRuntime, queryFn: getStyleEngineRuntimeSettings });
  const items = useMemo(() => buildSettingsReadinessItems({
    providers: providersQuery.data?.data ?? [],
    modelRoutes: routesQuery.data?.data,
    modelRouteConnectivity: connectivityQuery.data?.data,
    ragSettings: ragQuery.data?.data,
    styleSettings: styleQuery.data?.data,
    isModelRoutesChecking: connectivityQuery.isPending || connectivityQuery.isFetching,
    isStyleSettingsLoaded: styleQuery.isSuccess,
  }), [connectivityQuery.data?.data, connectivityQuery.isFetching, connectivityQuery.isPending, providersQuery.data?.data, ragQuery.data?.data, routesQuery.data?.data, styleQuery.data?.data, styleQuery.isSuccess]);
  const configuredProvider = providersQuery.data?.data?.find((item) => item.isConfigured && item.isActive);
  const routeCount = routesQuery.data?.data?.routes.filter((route) => route.provider && route.model).length ?? 0;
  const rag = ragQuery.data?.data;
  const summaryContext: SettingsOverviewSummaryContext = {
    configuredProviderName: configuredProvider?.name ?? null,
    configuredProviderModel: configuredProvider?.currentModel ?? null,
    routeCount,
    ragEnabled: Boolean(rag?.enabled),
    ragEmbeddingModel: rag?.embeddingModel ?? null,
  };

  return (
    <SettingsShell title="系统设置" description="查看创作环境状态，并进入需要调整的设置。">
      <SettingsReadinessCard items={items} />
      <div className="grid gap-4 md:grid-cols-2">
        {entries.map(({ to, title, description, icon: Icon, summary }) => {
          return (
            <Card key={to} className="min-w-0">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><Icon className="h-4 w-4" />{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
              <CardContent className="flex items-end justify-between gap-3">
                <p className="text-sm text-muted-foreground">{summary(summaryContext)}</p>
                <Button asChild variant="outline" size="sm" className="shrink-0"><Link to={to}>打开<ArrowRight className="h-4 w-4" /></Link></Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </SettingsShell>
  );
}
