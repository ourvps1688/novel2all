import { Suspense } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ASSET_TABS, getAssetTab, type AssetTab } from "./assetHub.config";

export default function AssetHubPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const active = getAssetTab(searchParams.get("tab"));

  // 内联渲染时直接渲染目标页面组件即可：组件自身通过 useSearchParams 读取真实
  // URL（/assets?tab=…&其它业务参数），无需合成 location。合成 location 会让
  // <Routes location> 的 pathname（如 /genres）不以父路由基址（/assets）开头，
  // 触发 React Router 的 invariant 而整页白屏，故此处直接渲染。

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
            {active.component ? <active.component /> : null}
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
