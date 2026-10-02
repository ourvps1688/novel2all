import { lazy, useEffect } from "react";
import type { RouteObject } from "react-router-dom";
import { Navigate, useNavigate, useParams, useRoutes } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";
import { featureFlags } from "@/config/featureFlags";
import { useIsMobileViewport } from "@/components/layout/mobile/useIsMobileViewport";
import { getLastNovelId } from "@/lib/lastNovel";

const Home = lazy(() => import("@/pages/Home"));
const NovelList = lazy(() => import("@/pages/novels/NovelList"));
const NovelCreate = lazy(() => import("@/pages/novels/NovelCreate"));
const CreationStudioPage = lazy(() => import("@/pages/creationStudio/CreationStudioPage"));
const ShortStoryStudioPage = lazy(() => import("@/pages/shortStory/ShortStoryStudioPage"));
const AutoDirectorCreatePage = lazy(() => import("@/pages/novels/autoDirector/AutoDirectorCreatePage"));
const SimpleNovelShelfPage = lazy(() => import("@/pages/novels/simpleCreation/SimpleNovelShelfPage"));
const NarrativeFormNovelEditRoute = lazy(() => import("@/pages/novels/NarrativeFormNovelEditRoute"));
const CreativeHubPage = lazy(() => import("@/pages/creativeHub/CreativeHubPage"));
const ChatPage = lazy(() => import("@/pages/chat/ChatPage"));
const BookAnalysisPage = lazy(() => import("@/pages/bookAnalysis/BookAnalysisPage"));
const MarketRadarPage = lazy(() => import("@/pages/marketRadar/MarketRadarPage"));
const TaskCenterPage = lazy(() => import("@/pages/tasks/TaskCenterPage"));
const KnowledgePage = lazy(() => import("@/pages/knowledge/KnowledgePage"));
const GenreManagementPage = lazy(() => import("@/pages/genres/GenreManagementPage"));
const StoryModeManagementPage = lazy(() => import("@/pages/storyModes/StoryModeManagementPage"));
const TitleStudioPage = lazy(() => import("@/pages/titles/TitleStudioPage"));
const AntiAiRulesPage = lazy(() => import("@/pages/antiAiRules/AntiAiRulesPage"));
const SettingsOverviewPage = lazy(() => import("@/pages/settings/views/SettingsOverviewPage"));
const ModelsSettingsPage = lazy(() => import("@/pages/settings/views/ModelsSettingsPage"));
const ModelRoutesSettingsPage = lazy(() => import("@/pages/settings/views/ModelRoutesSettingsPage"));
const DirectorSettingsPage = lazy(() => import("@/pages/settings/views/DirectorSettingsPage"));
const KnowledgeSettingsPage = lazy(() => import("@/pages/settings/views/KnowledgeSettingsPage"));
const MaintenanceSettingsPage = lazy(() => import("@/pages/settings/views/MaintenanceSettingsPage"));
const AppearanceSettingsPage = lazy(() => import("@/pages/settings/views/AppearanceSettingsPage"));
const WorldList = lazy(() => import("@/pages/worlds/WorldList"));
const WorldWorkspace = lazy(() => import("@/pages/worlds/WorldWorkspace"));
const WritingFormulaPage = lazy(() => import("@/pages/writingFormula/WritingFormulaPage"));
const CharacterLibrary = lazy(() => import("@/pages/characters/CharacterLibrary"));
const AssetHubPage = lazy(() => import("@/pages/assets/AssetHubPage"));

// The standalone chapter-editor route is absorbed into the workspace as a
// partition (NovelEditView renders ChapterEditorShell when ?stage=chapter&
// chapterId=<id>&editor=1). This redirect keeps any legacy deep links working.
function ChapterEditorPartitionRedirect() {
  const params = useParams();
  const navigate = useNavigate();
  useEffect(() => {
    const novelId = params.id;
    const chapterId = params.chapterId;
    if (novelId && chapterId) {
      navigate(
        `/novels/${novelId}/edit?stage=chapter&chapterId=${encodeURIComponent(chapterId)}&editor=1`,
        { replace: true },
      );
    } else {
      navigate("/novels", { replace: true });
    }
  }, [navigate, params.id, params.chapterId]);
  return null;
}

// The standalone preview route is absorbed into the workspace as a right-side
// drawer overlay (NovelEditView renders NovelPreviewDrawer when ?preview=1). This
// redirect keeps any legacy deep links working.
function PreviewPartitionRedirect() {
  const params = useParams();
  const navigate = useNavigate();
  useEffect(() => {
    const novelId = params.id;
    if (novelId) {
      navigate(`/novels/${novelId}/edit?preview=1`, { replace: true });
    } else {
      navigate("/novels", { replace: true });
    }
  }, [navigate, params.id]);
  return null;
}

// The /assets hub is now reachable as a right-side drawer inside the novel
// workspace (?assets=1). On desktop we redirect to the last-opened novel's
// workspace so the drawer opens there; on mobile we keep the full hub page
// (the drawer is desktop-only). If no novel was opened recently, fall back to
// the novel list so the user can pick one.
function AssetsHubRedirect() {
  const isMobile = useIsMobileViewport();
  if (isMobile) {
    return <AssetHubPage />;
  }
  const lastNovelId = getLastNovelId();
  if (lastNovelId) {
    return <Navigate to={`/novels/${encodeURIComponent(lastNovelId)}/edit?assets=1`} replace />;
  }
  return <Navigate to="/novels" replace />;
}

// Legacy deep link /novels/:id/assets -> workspace drawer.
function NovelAssetsPartitionRedirect() {
  const params = useParams();
  const navigate = useNavigate();
  useEffect(() => {
    const novelId = params.id;
    if (novelId) {
      navigate(`/novels/${novelId}/edit?assets=1`, { replace: true });
    } else {
      navigate("/novels", { replace: true });
    }
  }, [navigate, params.id]);
  return null;
}

const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: "novels", element: <NovelList /> },
      { path: "create", element: <CreationStudioPage /> },
      { path: "novels/create", element: <NovelCreate /> },
      { path: "novels/auto-director", element: <AutoDirectorCreatePage /> },
      { path: "novels/:id/simple", element: <SimpleNovelShelfPage /> },
      { path: "novels/:id/story", element: <ShortStoryStudioPage /> },
      { path: "novels/:id/preview", element: <PreviewPartitionRedirect /> },
      { path: "novels/:id/edit", element: <NarrativeFormNovelEditRoute /> },
      { path: "novels/:id/chapters/:chapterId", element: <ChapterEditorPartitionRedirect /> },
      { path: "novels/:id/assets", element: <NovelAssetsPartitionRedirect /> },
      { path: "creative-hub", element: <CreativeHubPage /> },
      { path: "chat-legacy", element: <ChatPage /> },
      { path: "chat", element: <Navigate to="/creative-hub" replace /> },
      { path: "book-analysis", element: <BookAnalysisPage /> },
      { path: "market-radar", element: <MarketRadarPage /> },
      { path: "tasks", element: <TaskCenterPage /> },
      { path: "knowledge", element: <KnowledgePage /> },
      { path: "assets", element: <AssetsHubRedirect /> },
      { path: "genres", element: <GenreManagementPage /> },
      { path: "story-modes", element: <StoryModeManagementPage /> },
      { path: "titles", element: <TitleStudioPage /> },
      { path: "anti-ai-rules", element: <AntiAiRulesPage /> },
      { path: "settings/model-routes", element: <ModelRoutesSettingsPage /> },
      { path: "settings/models", element: <ModelsSettingsPage /> },
      { path: "settings/director", element: <DirectorSettingsPage /> },
      { path: "settings/knowledge", element: <KnowledgeSettingsPage /> },
      { path: "settings/maintenance", element: <MaintenanceSettingsPage /> },
      { path: "settings/appearance", element: <AppearanceSettingsPage /> },
      { path: "settings", element: <SettingsOverviewPage /> },
      { path: "worlds", element: <WorldList /> },
      {
        path: "worlds/:id/workspace",
        element: featureFlags.worldWorkspaceEnabled ? <WorldWorkspace /> : <Navigate to="/worlds" replace />,
      },
      { path: "style-engine", element: <WritingFormulaPage /> },
      { path: "writing-formula", element: <Navigate to="/style-engine" replace /> },
      { path: "base-characters", element: <CharacterLibrary /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];

export default function AppRouter() {
  return useRoutes(routes);
}
