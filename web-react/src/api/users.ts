/**
 * Admin 用户管理 hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { del, get, postForm } from './client';
import { UserSchema, UsersListSchema, type User } from './types';

export const userKeys = {
  all: ['users'] as const,
};

/** 列出所有用户（admin only，GET /api/auth/users） */
export function useUsers(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: userKeys.all,
    queryFn: async () => {
      const data = await get<unknown>('/api/auth/users');
      return UsersListSchema.parse(data);
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
  });
}

/** 创建用户（admin only） */
export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation<User, Error, { username: string; password: string; role: 'admin' | 'editor' | 'viewer' }>({
    mutationFn: async ({ username, password, role }) => {
      const data = await postForm<unknown>('/api/auth/users', { username, password, role });
      return UserSchema.parse((data as { user: unknown }).user);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

/** 删除用户（admin only） */
export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation<{ deleted: number }, Error, number>({
    mutationFn: async (userId) => {
      return await del<{ deleted: number }>(`/api/auth/users/${userId}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}
