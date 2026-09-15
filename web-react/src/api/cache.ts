/**
 * Cache 统计相关 React Query hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { postForm, get } from './client';
import { CacheRecommendSchema, CacheStatsSchema, PromptPrefixStatsSchema } from './types';
import type { CacheRecommend, CacheStats, PromptPrefixStats } from './types';

export const cacheKeys = {
  stats: ['cache', 'stats'] as const,
  prompt: ['cache', 'prompt-stats'] as const,
  recommend: ['cache', 'recommend'] as const,
};

/** 整体 cache 统计（含 prompt_prefix 子字段） */
export function useCacheStats(options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: cacheKeys.stats,
    queryFn: async () => {
      const data = await get<unknown>('/api/cache/stats');
      return CacheStatsSchema.parse(data);
    },
    refetchInterval: options?.refetchInterval,
    staleTime: 30_000,
  });
}

/** prompt prefix cache 统计 */
export function usePromptCacheStats(options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: cacheKeys.prompt,
    queryFn: async () => {
      const data = await get<unknown>('/api/cache/prompt-stats');
      return PromptPrefixStatsSchema.parse(data);
    },
    refetchInterval: options?.refetchInterval,
    staleTime: 30_000,
  });
}

/** cache 配置推荐 */
export function useCacheRecommend() {
  return useQuery({
    queryKey: cacheKeys.recommend,
    queryFn: async () => {
      const data = await get<unknown>('/api/cache/recommend');
      return CacheRecommendSchema.parse(data);
    },
    staleTime: 5 * 60_000,
  });
}

/** 重置 prompt cache 统计 */
export function useResetPromptCache() {
  const qc = useQueryClient();
  return useMutation<{ reset: boolean }, Error, void>({
    mutationFn: async () => {
      return await postForm<{ reset: boolean }>('/api/cache/prompt-stats/reset', {});
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: cacheKeys.prompt });
      void qc.invalidateQueries({ queryKey: cacheKeys.stats });
    },
  });
}

export type { CacheStats, PromptPrefixStats, CacheRecommend };
