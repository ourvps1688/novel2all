import { useEffect, useMemo, useState } from "react";
import type { Chapter, ChapterStatus } from "@ai-novel/shared/types/novel";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, Check, Copy, Download, Edit3, List, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { downloadNovelExport, getNovelChapters, getNovelDetail } from "@/api/novel";
import { queryKeys } from "@/api/queryKeys";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function countWords(content: string | null | undefined): number {
  const text = content?.trim() ?? "";
  if (!text) return 0;
  const cjk = text.match(/[一-鿿]/g)?.length ?? 0;
  const words = text.replace(/[一-鿿]/g, " ").match(/[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*/g)?.length ?? 0;
  return cjk + words;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatChapterStatus(status?: ChapterStatus | null): string {
  switch (status) {
    case "completed": return "正文完成";
    case "pending_review": return "待审校";
    case "needs_repair": return "待修复";
    case "generating": return "生成中";
    case "pending_generation": return "待生成";
    case "unplanned": return "未规划";
    default: return "未标记";
  }
}

function chapterText(content: string | null | undefined): string {
  return content?.trim() ?? "";
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "true");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
  }
}

function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

function safeFileNamePart(value: string): string {
  return value.replace(/[\\/:*?"<>|]/g, "-").trim() || "小说";
}

export interface NovelPreviewDrawerProps {
  novelId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialChapterId?: string;
  onEditChapter?: (chapterId: string) => void;
}

export default function NovelPreviewDrawer({
  novelId,
  open,
  onOpenChange,
  initialChapterId,
  onEditChapter,
}: NovelPreviewDrawerProps) {
  const [selectedChapterId, setSelectedChapterId] = useState(initialChapterId ?? "");
  const [showChapters, setShowChapters] = useState(true);
  const [copied, setCopied] = useState(false);

  const novelQuery = useQuery({
    queryKey: queryKeys.novels.detail(novelId),
    queryFn: () => getNovelDetail(novelId),
    enabled: Boolean(novelId) && open,
  });
  const chaptersQuery = useQuery({
    queryKey: queryKeys.novels.chapters(novelId),
    queryFn: () => getNovelChapters(novelId),
    enabled: Boolean(novelId) && open,
  });

  const novel = novelQuery.data?.data ?? null;
  const chapters = useMemo(
    () => [...(chaptersQuery.data?.data ?? [])].sort((a, b) => a.order - b.order),
    [chaptersQuery.data?.data],
  );
  const generatedChapters = useMemo(() => chapters.filter((chapter) => chapterText(chapter.content)), [chapters]);
  const activeChapter = useMemo(
    () => chapters.find((chapter) => chapter.id === selectedChapterId) ?? generatedChapters[0] ?? chapters[0] ?? null,
    [chapters, generatedChapters, selectedChapterId],
  );
  const activeContent = chapterText(activeChapter?.content);
  const totalWordCount = useMemo(() => chapters.reduce((sum, chapter) => sum + countWords(chapter.content), 0), [chapters]);
  const downloadFullMutation = useMutation({
    mutationFn: () => downloadNovelExport(novelId, "txt", "full", novel?.title),
    onSuccess: ({ blob, fileName }) => {
      downloadBlob(blob, fileName);
      toast.success("整本正文下载已开始。");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "整本正文下载失败。"),
  });

  useEffect(() => {
    if (!activeChapter) return;
    setSelectedChapterId(activeChapter.id);
  }, [activeChapter]);

  const selectChapter = (chapter: Chapter) => {
    setSelectedChapterId(chapter.id);
    if (!window.matchMedia("(min-width: 1024px)").matches) {
      setShowChapters(false);
    }
  };

  const handleCopy = async () => {
    if (!activeContent) return toast.error("当前章节还没有正文。");
    try {
      await copyText(activeContent);
      setCopied(true);
      toast.success("正文已复制。");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("复制失败，请手动选择正文复制。");
    }
  };

  const handleDownloadChapter = () => {
    if (!activeChapter || !activeContent) return toast.error("当前章节还没有正文。");
    const title = safeFileNamePart(novel?.title ?? "小说");
    const chapterTitle = activeChapter.title?.trim() ? safeFileNamePart(activeChapter.title) : "";
    downloadBlob(
      new Blob(["﻿", `第 ${activeChapter.order} 章${chapterTitle ? ` ${chapterTitle}` : ""}\n\n${activeContent}`], { type: "text/plain;charset=utf-8" }),
      `${title}-第${activeChapter.order}章${chapterTitle ? `-${chapterTitle}` : ""}.txt`,
    );
    toast.success("本章正文下载已开始。");
  };

  const isLoading = novelQuery.isPending || chaptersQuery.isPending;
  const isError = novelQuery.isError || chaptersQuery.isError;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        id="novel-preview-panel"
        className="left-auto right-0 top-0 flex h-dvh max-h-dvh w-full max-w-[680px] translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-y-0 border-r-0 border-l bg-background p-0 sm:max-w-[680px]"
      >
        <DialogHeader className="border-b border-border/70 px-5 py-4">
          <div className="flex items-center justify-between gap-3 pr-9">
            <div className="min-w-0">
              <DialogTitle className="truncate">{novel?.title ?? "小说预览"}</DialogTitle>
              <DialogDescription className="truncate">
                {activeChapter ? `第 ${activeChapter.order} 章${activeChapter.title ? ` · ${activeChapter.title}` : ""}` : "阅读"}
                {chapters.length > 0 ? ` · ${formatCount(totalWordCount)} 字 · ${generatedChapters.length}/${chapters.length} 章已生成` : ""}
              </DialogDescription>
            </div>
            <div className="flex items-center gap-1">
              <Button type="button" variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground" onClick={handleDownloadChapter} disabled={!activeContent} title="下载本章" aria-label="下载本章">
                <Download className="h-4 w-4" /><span className="ml-1.5 hidden sm:inline">本章</span>
              </Button>
              <Button type="button" variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground" onClick={() => downloadFullMutation.mutate()} disabled={downloadFullMutation.isPending || generatedChapters.length === 0} title="下载整本" aria-label="下载整本">
                <BookOpen className="h-4 w-4" /><span className="ml-1.5 hidden sm:inline">整本</span>
              </Button>
              <Button type="button" variant="ghost" size="sm" className={cn("text-muted-foreground hover:text-foreground", showChapters && "bg-muted")} onClick={() => setShowChapters((value) => !value)} title="目录" aria-label="目录" aria-pressed={showChapters}>
                <List className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        {showChapters && chapters.length > 0 ? (
          <div className="max-h-[38vh] shrink-0 overflow-y-auto border-b border-border/70 px-3 py-3">
            <div className="mb-2 px-2 text-xs font-medium text-muted-foreground">
              目录 · {generatedChapters.length}/{chapters.length} 章
            </div>
            <nav className="space-y-1">
              {chapters.map((chapter) => {
                const hasContent = Boolean(chapterText(chapter.content));
                return (
                  <button key={chapter.id} type="button" className={cn("w-full rounded-md px-3 py-2.5 text-left transition hover:bg-muted/70", activeChapter?.id === chapter.id && "bg-muted")} onClick={() => selectChapter(chapter)}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium">第 {chapter.order} 章</span>
                      <span className="text-xs text-muted-foreground">{formatCount(countWords(chapter.content))} 字</span>
                    </div>
                    <div className="mt-0.5 truncate text-sm text-muted-foreground">{chapter.title || "未命名章节"}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{hasContent ? formatChapterStatus(chapter.chapterStatus) : "暂无正文"}</div>
                  </button>
                );
              })}
            </nav>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-20 pt-6 sm:px-8">
          {isError ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <p className="text-sm text-muted-foreground">当前无法打开这本作品。</p>
              <Button type="button" onClick={() => { void novelQuery.refetch(); void chaptersQuery.refetch(); }}>重新加载</Button>
            </div>
          ) : isLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">正在打开作品...</div>
          ) : chapters.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <BookOpen className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
              <p className="text-sm text-muted-foreground">这本作品还没有可阅读的章节。</p>
            </div>
          ) : (
            <div className="mx-auto max-w-2xl">
              <div className="mb-10 text-center">
                <div className="text-xs tracking-[0.22em] text-muted-foreground">{novel?.status === "published" ? "PUBLISHED" : "DRAFT"}</div>
                <h1 className="mt-4 text-2xl font-semibold tracking-normal text-foreground sm:text-3xl">{novel?.title ?? "小说预览"}</h1>
                <p className="mt-3 text-sm text-muted-foreground">{formatCount(totalWordCount)} 字 · {generatedChapters.length}/{chapters.length} 章已生成</p>
              </div>

              <article className="whitespace-pre-wrap text-[16px] leading-[2.1] text-foreground sm:text-[17px]">
                {activeContent || "本章还没有正文。"}
              </article>

              <footer className="mt-16 flex items-center justify-center gap-2 border-t border-border/70 pt-6">
                <Button type="button" variant="ghost" size="sm" className="text-muted-foreground" onClick={() => void handleCopy()} disabled={!activeContent}>
                  {copied ? <Check className="mr-1.5 h-4 w-4" /> : <Copy className="mr-1.5 h-4 w-4" />}
                  {copied ? "已复制" : "复制本章"}
                </Button>
                {activeChapter ? (
                  onEditChapter ? (
                    <Button type="button" variant="ghost" size="sm" className="text-muted-foreground" onClick={() => onEditChapter(activeChapter.id)}>
                      <Edit3 className="mr-1.5 h-4 w-4" />编辑本章
                    </Button>
                  ) : (
                    <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
                      <Link to={`/novels/${novelId}/chapters/${activeChapter.id}`}><Edit3 className="mr-1.5 h-4 w-4" />编辑本章</Link>
                    </Button>
                  )
                ) : null}
              </footer>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-border/70 px-5 py-3">
          <span className="truncate text-xs text-muted-foreground">{novel?.title ?? "小说预览"}</span>
          <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            <X className="mr-1.5 h-4 w-4" />关闭
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
