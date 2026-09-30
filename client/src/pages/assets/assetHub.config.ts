import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import {
  Database,
  Globe2,
  ScanSearch,
  ShieldCheck,
  SquarePen,
  Tags,
  UsersRound,
  WandSparkles,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type AssetTabKey =
  | "genres"
  | "story-modes"
  | "titles"
  | "knowledge"
  | "worlds"
  | "style-engine"
  | "anti-ai-rules"
  | "base-characters"
  | "book-analysis";

/**
 * 渲染模式：
 * - "inline"：在枢纽内联渲染既有页面组件（经由合成 location，使其表现得像在自己的原路由上）。
 * - "link"：该页会在壳内改写 ?tab=，会冲掉枢纽自身的 ?tab= 选择器，
 *            因此不内联渲染，改为一条跳转到原路由的入口（契约 §4.4 兜底路径）。
 */
export type AssetTabRenderMode = "inline" | "link";

export interface AssetTab {
  key: AssetTabKey;
  label: string;
  icon: LucideIcon;
  /** 该 tab 对应的规范路由；用于合成 location 与 link 兜底跳转。 */
  originalPath: string;
  /** 内联渲染用的页面组件；link 模式为 null。 */
  component: LazyExoticComponent<ComponentType> | null;
  mode: AssetTabRenderMode;
}

/**
 * 纯声明式渲染映射，不是分支派发表。
 * 注意：本文件不得引入按资源类型分派的键名或 switch 派发逻辑（契约 §5 硬约束），只用上面的声明式数组。
 */
export const ASSET_TABS: AssetTab[] = [
  {
    key: "genres",
    label: "题材基底库",
    icon: Tags,
    originalPath: "/genres",
    component: lazy(() => import("@/pages/genres/GenreManagementPage")),
    mode: "inline",
  },
  {
    key: "story-modes",
    label: "推进模式库",
    icon: Workflow,
    originalPath: "/story-modes",
    component: lazy(() => import("@/pages/storyModes/StoryModeManagementPage")),
    mode: "inline",
  },
  {
    key: "titles",
    label: "标题工坊",
    icon: SquarePen,
    originalPath: "/titles",
    component: lazy(() => import("@/pages/titles/TitleStudioPage")),
    mode: "inline",
  },
  {
    key: "knowledge",
    label: "知识库",
    icon: Database,
    originalPath: "/knowledge",
    component: null,
    mode: "link",
  },
  {
    key: "worlds",
    label: "世界样本库",
    icon: Globe2,
    originalPath: "/worlds",
    component: lazy(() => import("@/pages/worlds/WorldList")),
    mode: "inline",
  },
  {
    key: "style-engine",
    label: "写法引擎",
    icon: WandSparkles,
    originalPath: "/style-engine",
    component: null,
    mode: "link",
  },
  {
    key: "anti-ai-rules",
    label: "反 AI 规则",
    icon: ShieldCheck,
    originalPath: "/anti-ai-rules",
    component: lazy(() => import("@/pages/antiAiRules/AntiAiRulesPage")),
    mode: "inline",
  },
  {
    key: "base-characters",
    label: "基础角色库",
    icon: UsersRound,
    originalPath: "/base-characters",
    component: lazy(() => import("@/pages/characters/CharacterLibrary")),
    mode: "inline",
  },
  {
    key: "book-analysis",
    label: "拆书分析",
    icon: ScanSearch,
    originalPath: "/book-analysis",
    component: lazy(() => import("@/pages/bookAnalysis/BookAnalysisPage")),
    mode: "inline",
  },
];

export const DEFAULT_ASSET_TAB: AssetTabKey = "genres";

/** 按 ?tab= 取值；未知值（如其它页内部的 ?tab=）回退到默认 tab，避免 R3 冲突（契约 §4）。 */
export function getAssetTab(key: string | null | undefined): AssetTab {
  return ASSET_TABS.find((tab) => tab.key === key) ?? ASSET_TABS[0];
}
