import { Suspense, useMemo } from "react";
import { Link, Route, Routes, useSearchParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ASSET_TABS, getAssetTab, type AssetTab } from "./assetHub.config";

export default function AssetHubPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const active = getAssetTab(searchParams.get("tab"));

  // 业务参数透传：把除 hub 自身 ?tab= 之外的所有 query 原样喂给被渲染组件，
  // 绝不吞掉 / 改写 / 重排任何业务参数（契约 §5）。
  const passthrough = useMemo(() => {
    const next = new URLSearchParams(searchParams);
    next.delete("tab");
    const serialized = next.toString();
    return serialized ? `?${serialized}` : "";
  }, [searchParams]);

  // 合成 location：让内联渲染的页面组件表现得像在自己的原路由上（R3 化解，契约 §4.4）。
  const syntheticLocation = `${active.originalPath}${passthrough}`;

  const selectTab = (key: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", key);
    setSearchParams(next);
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">创作资产</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          这里集中管理写书时反复用到的素材与基底：题材、推进模式、标题、知识、世界观、写法、防 AI
          痕迹、基础角色，以及参考小说的拆书结果。点开任意一个分类即可查看或继续完善。
        </p>
      </header>

      <nav className="flex flex-wrap gap-2" aria-label="创作资产分类">
        {ASSET_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.key === active.key;
          return (
            <button
              key={tab.key}
              type="button"
              aria-current={isActive ? "page" : undefined}
              onClick={() => selectTab(tab.key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/60 text-foreground hover:bg-muted",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <section className="min-h-[40vh]">
        {active.mode === "link" ? (
          <LinkEntryCard tab={active} />
        ) : (
          <Suspense
            fallback={
              <div className="py-10 text-center text-sm text-muted-foreground">加载中…</div>
            }
          >
            <Routes location={syntheticLocation}>
              <Route
                path={active.originalPath}
                element={active.component ? <active.component /> : null}
              />
            </Routes>
          </Suspense>
        )}
      </section>
    </div>
  );
}

function LinkEntryCard({ tab }: { tab: AssetTab }) {
  const Icon = tab.icon;
  return (
    <div className="flex flex-col items-center gap-4 rounded-xl bg-muted/40 px-6 py-10 text-center">
      <Icon className="h-8 w-8 text-muted-foreground" />
      <p className="max-w-md text-sm leading-6 text-muted-foreground">
        「{tab.label}」包含多个子模块，在独立页面里查看与编辑更顺手。点击下方即可进入。
      </p>
      <Link
        to={tab.originalPath}
        className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        打开{tab.label}
      </Link>
    </div>
  );
}
