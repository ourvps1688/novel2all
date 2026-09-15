/**
 * 鉴权相关 React Query hooks
 *
 * 注意：
 *  - 真正的 user 状态由 zustand authStore 管理（AuthProvider 同步）
 *  - 此处 useMe() 仅用于触发首次验证（onMount 时 call 一次）
 *  - login / logout 是 mutation，调用后手动 invalidate ['auth','me']
 */

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { get, postForm, setUnauthorizedHandler } from './client';
import { AuthMeSchema, LoginResponseSchema, type AuthMe, type LoginResponse, type User } from './types';

// ============ Query Keys ============

export const authKeys = {
  me: ['auth', 'me'] as const,
};

// ============ Hooks ============

/**
 * 当前用户信息（每次 invalidate 后 refetch）
 * 注：未登录时也返回 {user: null, authenticated: false}，不算 error
 */
export function useMe(options?: { enabled?: boolean }): UseQueryResult<AuthMe> {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: async () => {
      const data = await get<unknown>('/api/auth/me');
      return AuthMeSchema.parse(data);
    },
    enabled: options?.enabled ?? true,
    staleTime: Infinity, // 仅在显式 invalidate 时重新拉取
    retry: false, // 401 不重试
  });
}

/**
 * 登录 mutation（成功后 onSuccess 设 store）
 */
export function useLoginMutation() {
  const qc = useQueryClient();
  return useMutation<LoginResponse, Error, { username: string; password: string }>({
    mutationFn: async ({ username, password }) => {
      const data = await postForm<unknown>('/api/auth/login', { username, password });
      return LoginResponseSchema.parse(data);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: authKeys.me });
    },
  });
}

/**
 * 注销 mutation
 */
export function useLogoutMutation() {
  const qc = useQueryClient();
  return useMutation<{ message: string }, Error, void>({
    mutationFn: async () => {
      return await postForm<{ message: string }>('/api/auth/logout', {});
    },
    onSuccess: () => {
      qc.clear(); // 清空所有 cache（含章节、缓存统计等）
      void qc.invalidateQueries({ queryKey: authKeys.me });
    },
  });
}

/** 注册 401 全局回调（仅 AuthProvider mount 时调一次） */
export { setUnauthorizedHandler };
