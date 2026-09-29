import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const mobileRoot = dirname(fileURLToPath(import.meta.url));
const clientSrcRoot = resolve(mobileRoot, "../..");

function readSource(relativePath) {
  return readFileSync(join(clientSrcRoot, relativePath), "utf8");
}

function readMobileSource(relativePath) {
  return readFileSync(join(mobileRoot, relativePath), "utf8");
}

function assertContains(source, expected, message) {
  assert.ok(source.includes(expected), message);
}

function assertImportsMobileContracts(source, message) {
  assertContains(source, "@/mobile/autoDirector", message);
}

test("auto-director mobile support is centralized under the mobile directory", () => {
  const contracts = readMobileSource("mobileSupportContracts.ts");

  assertContains(
    contracts,
    "AUTO_DIRECTOR_MOBILE_ROUTE_PATTERNS",
    "mobile full-width route opt-in should live in the auto-director mobile directory",
  );
  assertContains(
    contracts,
    "AUTO_DIRECTOR_MOBILE_CLASSES",
    "mobile layout/style contracts should live in the auto-director mobile directory",
  );
  [
    "/settings",
    "/novels/create",
    "/novels/auto-director",
    "/novels/:id/edit",
  ].forEach((routePattern) => {
    assertContains(
      contracts,
      routePattern,
      `${routePattern} should be opted into the centralized auto-director mobile route contract`,
    );
  });
});

test("auto-director app shell uses mobile contracts for single-column non-overflow layout", () => {
  const appLayout = readSource("components/layout/AppLayout.tsx");

  assertImportsMobileContracts(appLayout, "app layout should import mobile route contracts instead of owning route exceptions");
  assertContains(
    appLayout,
    "shouldUseAutoDirectorMobileFullWidthContent",
    "auto-director target routes should opt into mobile full-width content through the mobile directory",
  );
  assertContains(
    appLayout,
    "hidden md:block",
    "project/workspace side navigation should not squeeze auto-director target pages at phone width",
  );
  assertContains(
    appLayout,
    "AUTO_DIRECTOR_MOBILE_CLASSES.appMain",
    "app main mobile-safe sizing should be imported from the mobile directory",
  );
  assertContains(
    appLayout,
    "useMobileFullWidthContent ? AUTO_DIRECTOR_MOBILE_CLASSES.appMain : DEFAULT_APP_MAIN_CLASS_NAME",
    "auto-director mobile app main sizing should be route-scoped instead of changing every page shell",
  );

  const navbar = readSource("components/layout/Navbar.tsx");
  assertImportsMobileContracts(navbar, "navbar should import mobile shell contracts for auto-director target routes");
  assertContains(
    navbar,
    "shouldUseAutoDirectorMobileFullWidthContent",
    "navbar mobile shell changes should be scoped by the auto-director route opt-in",
  );
  assertContains(
    navbar,
    "AUTO_DIRECTOR_MOBILE_CLASSES.navbarModelSelector",
    "the global model selector should not force auto-director target pages wider than a phone viewport",
  );
  assertContains(
    navbar,
    "AUTO_DIRECTOR_MOBILE_CLASSES.navbarWorkspaceToggle",
    "workspace navigation toggle should not compete with mobile page actions at phone width",
  );
});

test("auto-director creation page exposes mobile-safe stages and reachable action areas through mobile contracts", () => {
  const createPage = readSource("pages/novels/autoDirector/AutoDirectorCreatePage.tsx");
  const basicStage = readSource("pages/novels/autoDirector/StageBasicSetup.tsx");
  const worldStage = readSource("pages/novels/autoDirector/StageWorldStyle.tsx");
  const modelStage = readSource("pages/novels/autoDirector/StageModelRun.tsx");
  const candidateBatches = readSource("pages/novels/components/NovelAutoDirectorCandidateBatches.tsx");
  const takeoverDialog = readSource("pages/novels/components/NovelExistingProjectTakeoverDialog.tsx");

  assertContains(
    createPage,
    "StageIdea",
    "new-book auto-director route should own stage components outside the old dialog flow",
  );
  assertImportsMobileContracts(basicStage, "new-book basic stage should import mobile text wrapping contracts");
  assertContains(
    basicStage,
    "AUTO_DIRECTOR_MOBILE_CLASSES.wrapText",
    "new-book basic stage helper text should wrap on phones",
  );
  assertImportsMobileContracts(worldStage, "new-book world/style stage should import mobile text wrapping contracts");
  assertContains(
    worldStage,
    "AUTO_DIRECTOR_MOBILE_CLASSES.wrapText",
    "new-book world/style stage helper text should wrap on phones",
  );
  assertImportsMobileContracts(modelStage, "new-book model/run stage should import mobile action contracts");
  assertContains(
    modelStage,
    "AUTO_DIRECTOR_MOBILE_CLASSES.wrapText",
    "new-book model/run stage copy should wrap on phones",
  );
  assertImportsMobileContracts(candidateBatches, "candidate batches should import mobile action contracts");
  assertContains(
    candidateBatches,
    "AUTO_DIRECTOR_MOBILE_CLASSES.fullWidthAction",
    "candidate actions should become full-width touch targets on mobile",
  );
  assertImportsMobileContracts(takeoverDialog, "takeover dialog should import mobile dialog contracts");
  assertContains(
    takeoverDialog,
    "AUTO_DIRECTOR_MOBILE_CLASSES.takeoverSubmitBar",
    "takeover submit area should remain reachable after long mobile content",
  );
});

test("auto-approval preference controls wrap labels and save actions on mobile through mobile contracts", () => {
  const multiSelect = readSource("components/autoDirector/AutoDirectorApprovalPointMultiSelect.tsx");
  const strategyPanel = readSource("components/autoDirector/AutoDirectorApprovalStrategyPanel.tsx");
  const settingsPage = readSource("pages/settings/SettingsPage.tsx");
  const preferenceCard = readSource("pages/settings/AutoDirectorApprovalPreferenceCard.tsx");
  const channelSettingsCard = readSource("pages/settings/AutoDirectorChannelSettingsCard.tsx");
  const settingsNavigationCards = readSource("pages/settings/components/SettingsNavigationCards.tsx");

  assertImportsMobileContracts(settingsPage, "settings route should import mobile settings contracts");
  assertContains(
    settingsPage,
    "AUTO_DIRECTOR_MOBILE_CLASSES.settingsPageRoot",
    "settings route should prevent neighboring settings cards from widening the auto-approval preference path on phones",
  );
  assertImportsMobileContracts(multiSelect, "approval point multiselect should import mobile wrapping contracts");
  assertContains(
    multiSelect,
    "AUTO_DIRECTOR_MOBILE_CLASSES.wrapText",
    "approval group and point labels should wrap instead of forcing horizontal scroll",
  );
  assertImportsMobileContracts(strategyPanel, "approval strategy panel should import mobile choice grid contracts");
  assertContains(
    strategyPanel,
    "AUTO_DIRECTOR_MOBILE_CLASSES.approvalStrategyGrid",
    "AI push/copilot choice cards should stay single-column at phone width",
  );
  assertImportsMobileContracts(preferenceCard, "preference card should import mobile settings action contracts");
  assertContains(
    preferenceCard,
    "AUTO_DIRECTOR_MOBILE_CLASSES.settingsActionRow",
    "settings save action should be full-width on phones and compact on desktop",
  );
  assertImportsMobileContracts(channelSettingsCard, "channel settings card should import mobile settings action contracts");
  assertContains(
    channelSettingsCard,
    "AUTO_DIRECTOR_MOBILE_CLASSES.channelSettingsActionRow",
    "channel settings actions should remain reachable while reviewing auto-approval preferences on phones",
  );
  assertImportsMobileContracts(settingsNavigationCards, "settings navigation cards should import mobile settings entry contracts");
  assertContains(
    settingsNavigationCards,
    "AUTO_DIRECTOR_MOBILE_CLASSES.settingsEntryActionRow",
    "settings entry cards should not push action buttons outside the phone viewport",
  );
});
