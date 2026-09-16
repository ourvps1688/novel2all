/**
 * Auth hooks: useMe / useLoginMutation / useLogoutMutation
 * + admin 用户项目列表 (useUserProjects)
 */

import { useMutation, useQuery } from '@tanstack/react-query';

import { get, postForm } from './client';
import {
  AuthMeSchema,
  LoginResponseSchema,
  UserProjectsSchema,
  type LoginResponse,
} from './types';
import type { ProjectEntry } from './types';

export const authKeys = {
  me: ['auth', 'me'] as const,
  userProjects: (userId: number | string) => ['auth', 'user-projects', userId] as const,
};

/** 当前登录用户（AuthMeSchema: { user, authenticated }） */
export function useMe(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: async () => {
      const data = await get<unknown>('/api/auth/me');
      return AuthMeSchema.parse(data);
    },
    staleTime: Infinity,
    retry: false,
    enabled: options?.enabled ?? true,
  });
}

/** 登录 mutation */
export function useLoginMutation() {
  return useMutation<LoginResponse, Error, { username: string; password: string }>({
    mutationFn: async (creds) => {
      const data = await postForm<unknown>('/api/auth/login', creds);
      return LoginResponseSchema.parse(data);
    },
  });
}

/** 登出 mutation */
export function useLogoutMutation() {
  return useMutation<{ message: string }, Error, void>({
    mutationFn: async () => {
      return await postForm<{ message: string }>('/api/auth/logout', {});
    },
  });
}

/** 列出指定用户的所有项目（admin only，GET /api/auth/users/{user_id}/projects） */
export function useUserProjects(userId: number | string | null | undefined) {
  return useQuery({
    queryKey: authKeys.userProjects(userId ?? -1),
    queryFn: async () => {
      const data = await get<unknown>(`/api/auth/users/${userId}/projects`);
      return UserProjectsSchema.parse(data);
    },
    enabled: userId != null && userId !== '',
    staleTime: 30_000,
  });
}

export type { ProjectEntry };
