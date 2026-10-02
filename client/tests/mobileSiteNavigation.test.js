import test from "node:test";
import assert from "node:assert/strict";
import {
  MOBILE_ROUTE_PATTERNS,
  getMobileNavGroupForPath,
  getMobilePageTitle,
  getMobilePrimaryNavItems,
  getMobileMoreNavGroups,
  getMobileRouteClassName,
} from "../src/components/layout/mobile/mobileSiteNavigation.ts";

const routedPaths = [
  "/",
  "/novels",
  "/novels/create",
  "/novels/demo/preview",
  "/novels/demo/edit",
  "/creative-hub",
  "/chat-legacy",
  "/book-analysis",
  "/assets",
  "/market-radar",
  "/tasks",
  "/knowledge",
  "/genres",
  "/story-modes",
  "/titles",
  "/settings/model-routes",
  "/settings/models",
  "/settings/director",
  "/settings/knowledge",
  "/settings/maintenance",
  "/settings",
  "/worlds",
  "/worlds/world-1/workspace",
  "/style-engine",
  "/anti-ai-rules",
  "/base-characters",
];

test("mobile route metadata covers every registered page", () => {
  assert.equal(MOBILE_ROUTE_PATTERNS.length, routedPaths.length);

  for (const path of routedPaths) {
    assert.notEqual(getMobilePageTitle(path), "更多功能");
    assert.match(getMobileNavGroupForPath(path), /^(home|novels|creation|tasks|more)$/);
    assert.match(getMobileRouteClassName(path), /^mobile-route-[a-z0-9-]+$/);
  }
});

test("mobile primary nav keeps core beginner actions visible", () => {
  assert.deepEqual(
    getMobilePrimaryNavItems().map((item) => [item.key, item.to, item.label]),
    [
      ["home", "/", "首页"],
      ["novels", "/novels", "小说"],
      ["creation", "/creative-hub", "创作"],
      ["tasks", "/tasks", "运行记录"],
      ["more", "", "更多"],
    ],
  );
});

test("mobile more menu contains all non-primary registered pages", () => {
  const morePaths = getMobileMoreNavGroups().flatMap((group) => group.items.map((item) => item.to));

  // The more menu is intentionally consolidated: legacy chat under 创作辅助,
  // the unified asset hub (/assets) under 资产库, and system settings.
  // Older feature pages (拆书/题材雷达/知识库等) were consolidated into the
  // asset hub and are no longer separate more-menu entries.
  assert.deepEqual(morePaths, ["/chat-legacy", "/assets", "/settings"]);
});
