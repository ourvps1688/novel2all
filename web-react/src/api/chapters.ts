/**
 * 章节相关 React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { get, post, postForm } from './client';
import {
  ChapterContentSchema,
  ChapterInsertResponseSchema,
  ChapterRewriteResponseSchema,
  ChapterSaveResponseSchema,
  ChapterSchema,
  OutlineSchema,
  ReviewReportSchema,
  type Chapter,
  type ChapterContent,
  type ChapterInsertResponse,
  type ChapterRewriteResponse,
  type ChapterSaveResponse,
  type Outline,
  type ReviewReport,
} from './types';
import { newIdempotencyKey } from '../utils/idem';

const DEFAULT_PROJECT_ROOT = '.';

export const chapterKeys = {
  all: (projectRoot = DEFAULT_PROJECT_ROOT) => ['chapters', projectRoot] as const,
  detail: (chapter: number, projectRoot = DEFAULT_PROJECT_ROOT) =>
    ['chapter', chapter, projectRoot] as const,
  outlines: (projectRoot = DEFAULT_PROJECT_ROOT) => ['outlines', projectRoot] as const,
  review: (chapter: number) => ['review', chapter] as const,
};

/** 列出所有章节 */
export function useChapters(projectRoot = DEFAULT_PROJECT_ROOT) {
  return useQuery({
    queryKey: chapterKeys.all(projectRoot),
    queryFn: async () => {
      const data = await get<unknown>(`/api/chapters?project_root=${encodeURIComponent(projectRoot)}`);
      return z.array(ChapterSchema).parse(data);
    },
    staleTime: 60_000,
  });
}

/** 章节完整内容 */
export function useChapterContent(chapter: number | null, projectRoot = DEFAULT_PROJECT_ROOT) {
  return useQuery({
    queryKey: chapterKeys.detail(chapter ?? -1, projectRoot),
    queryFn: async () => {
      if (chapter == null) throw new Error('chapter is null');
      const data = await get<unknown>(
        `/api/chapter/${chapter}/content?project_root=${encodeURIComponent(projectRoot)}`,
      );
      return ChapterContentSchema.parse(data);
    },
    enabled: chapter != null,
    staleTime: 30_000,
  });
}

/** 列出所有细纲 */
export function useOutlines(projectRoot = DEFAULT_PROJECT_ROOT) {
  return useQuery({
    queryKey: chapterKeys.outlines(projectRoot),
    queryFn: async () => {
      const data = await get<unknown>(`/api/outlines?project_root=${encodeURIComponent(projectRoot)}`);
      return z.array(OutlineSchema).parse(data);
    },
    staleTime: 60_000,
  });
}

/** 保存章节（手动编辑后） */
export function useSaveChapter(projectRoot = DEFAULT_PROJECT_ROOT) {
  const qc = useQueryClient();
  return useMutation<
    ChapterSaveResponse,
    Error,
    { chapter: number; content: string }
  >({
    mutationFn: async ({ chapter, content }) => {
      const data = await postForm<unknown>(`/api/chapter/${chapter}/save`, {
        content,
        project_root: projectRoot,
      });
      return ChapterSaveResponseSchema.parse(data);
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: chapterKeys.detail(vars.chapter, projectRoot) });
      void qc.invalidateQueries({ queryKey: chapterKeys.all(projectRoot) });
    },
  });
}

/** AI 重写选中区段 */
export function useRewriteChapter(projectRoot = DEFAULT_PROJECT_ROOT) {
  return useMutation<
    ChapterRewriteResponse,
    Error,
    { chapter: number; start: number; end: number; instruction: string; model?: string }
  >({
    mutationFn: async ({ chapter, start, end, instruction, model }) => {
      const data = await postForm<unknown>(`/api/chapter/${chapter}/rewrite`, {
        start,
        end,
        instruction,
        project_root: projectRoot,
        model: model ?? '',
      });
      return ChapterRewriteResponseSchema.parse(data);
    },
  });
}

/** AI 在指定位置插入 */
export function useInsertChapter(projectRoot = DEFAULT_PROJECT_ROOT) {
  return useMutation<
    ChapterInsertResponse,
    Error,
    { chapter: number; position: number; instruction: string; model?: string }
  >({
    mutationFn: async ({ chapter, position, instruction, model }) => {
      const data = await postForm<unknown>(`/api/chapter/${chapter}/insert`, {
        position,
        instruction,
        project_root: projectRoot,
        model: model ?? '',
      });
      return ChapterInsertResponseSchema.parse(data);
    },
  });
}

/**
 * 4-agent review（带 Idempotency-Key）
 * 每次调用都生成新 uuid；同 key 5min 内重放会拿到缓存结果
 */
export function useReviewChapter(projectRoot = DEFAULT_PROJECT_ROOT) {
  const qc = useQueryClient();
  return useMutation<ReviewReport, Error, { chapter: number; idempotencyKey?: string }>({
    mutationFn: async ({ chapter, idempotencyKey }) => {
      const key = idempotencyKey ?? newIdempotencyKey();
      const data = await post<unknown, Record<string, never>>(
        `/api/chapter/${chapter}/review?project_root=${encodeURIComponent(projectRoot)}`,
        {},
        {
          headers: { 'Idempotency-Key': key },
        },
      );
      return ReviewReportSchema.parse(data);
    },
    onSuccess: (data, vars) => {
      qc.setQueryData(chapterKeys.review(vars.chapter), data);
    },
  });
}

/** 缓存已查询过的 review 结果（用于跨页共享） */
export function useCachedReview(chapter: number) {
  return useQuery({
    queryKey: chapterKeys.review(chapter),
    queryFn: () => null as unknown as ReviewReport,
    enabled: false, // 永不自动 fetch，仅 setQueryData 写入
    staleTime: Infinity,
  });
}

// ============ Type re-export ============
export type { Chapter, ChapterContent, Outline, ReviewReport };
