import { useCallback, useEffect, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { bootstrapNovelWorkflow } from "@/api/novelWorkflow";
import { normalizeNovelWorkspaceTab } from "../novelWorkspaceNavigation";
import {
  readNovelEditWorkflowTaskIds,
  withNovelEditDirectorTaskId,
  withNovelEditWorkspaceTaskId,
} from "./novelEditWorkflowParams";

export function useNovelEditWorkflow(novelId: string) {
  const [searchParams, setSearchParams] = useSearchParams();

  const { directorTaskId, workspaceTaskId: workflowTaskId } = readNovelEditWorkflowTaskIds(searchParams);
  const selectedVolumeId = searchParams.get("volumeId") ?? "";
  const taskPanelOpen = searchParams.get("taskPanel") === "1";

  useEffect(() => {
    const canonicalDirectorTaskId = searchParams.get("directorTaskId")?.trim() ?? "";
    const legacyDirectorTaskId = searchParams.get("taskId")?.trim() ?? "";
    if (!legacyDirectorTaskId) {
      return;
    }
    setSearchParams((prev) => withNovelEditDirectorTaskId(prev, canonicalDirectorTaskId || legacyDirectorTaskId), {
      replace: true,
    });
  }, [searchParams, setSearchParams]);

  const bootstrapMutation = useMutation({
    mutationFn: () => bootstrapNovelWorkflow({
      workflowTaskId: workflowTaskId || undefined,
      novelId,
      lane: "manual_create",
      seedPayload: {
        entry: "novel_edit",
        stage: normalizeNovelWorkspaceTab(searchParams.get("stage")),
      },
    }),
    onSuccess: (response) => {
      const nextTaskId = response.data?.id;
      if (!nextTaskId || nextTaskId === workflowTaskId) {
        return;
      }
      setSearchParams((prev) => {
        const next = withNovelEditWorkspaceTaskId(prev, nextTaskId);
        if (!next.get("stage")) {
          next.set("stage", normalizeNovelWorkspaceTab(searchParams.get("stage")));
        }
        return next;
      }, { replace: true });
    },
  });

  useEffect(() => {
    if (!novelId) {
      return;
    }
    bootstrapMutation.mutate();
  }, [novelId, workflowTaskId]);

  const activeTab = useMemo(
    () => normalizeNovelWorkspaceTab(searchParams.get("stage")),
    [searchParams],
  );
  const selectedChapterId = useMemo(
    () => searchParams.get("chapterId") ?? "",
    [searchParams],
  );
  const editorOpen = searchParams.get("editor") === "1";
  const previewOpen = searchParams.get("preview") === "1";
  const assetsDrawerOpen = searchParams.get("assets") === "1";

  const setActiveTab = (value: string) => {
    const nextTab = normalizeNovelWorkspaceTab(value);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("stage", nextTab);
      // Switching the workspace tab closes any open chapter-editor partition
      // and the preview overlay so returning to a tab shows a clean panel.
      next.delete("editor");
      next.delete("preview");
      next.delete("assets");
      return next;
    }, { replace: true });
  };

  const openChapterEditor = useCallback((chapterId: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("stage", "chapter");
      next.set("chapterId", chapterId);
      next.set("editor", "1");
      // Opening the chapter-editor partition closes the preview overlay so the
      // two overlays never show at the same time.
      next.delete("preview");
      next.delete("assets");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const closeChapterEditor = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("editor");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const openPreview = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      // Opening the preview overlay closes the chapter-editor partition so the
      // two overlays never show at the same time.
      next.delete("editor");
      next.delete("assets");
      next.set("preview", "1");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const closePreview = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("preview");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const openAssetsDrawer = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      // Opening the assets drawer closes the chapter-editor partition and the
      // preview overlay so the overlays never show at the same time.
      next.delete("editor");
      next.delete("preview");
      next.set("assets", "1");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const closeAssetsDrawer = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("assets");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setSelectedChapterId = (value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set("chapterId", value);
      } else {
        next.delete("chapterId");
      }
      return next;
    }, { replace: true });
  };

  const setSelectedVolumeId = (value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set("volumeId", value);
      } else {
        next.delete("volumeId");
      }
      return next;
    }, { replace: true });
  };

  const setDirectorTaskId = useCallback((value: string) => {
    setSearchParams((prev) => {
      return withNovelEditDirectorTaskId(prev, value);
    }, { replace: true });
  }, [setSearchParams]);

  const clearTaskPanelOpen = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("taskPanel");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  return {
    activeTab,
    setActiveTab,
    directorTaskId,
    setDirectorTaskId,
    selectedChapterId,
    setSelectedChapterId,
    selectedVolumeId,
    setSelectedVolumeId,
    workflowTaskId,
    taskPanelOpen,
    clearTaskPanelOpen,
    editorOpen,
    openChapterEditor,
    closeChapterEditor,
    previewOpen,
    openPreview,
    closePreview,
    assetsDrawerOpen,
    openAssetsDrawer,
    closeAssetsDrawer,
  };
}
