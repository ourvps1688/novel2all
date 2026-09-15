/**
 * 项目状态 / Skills / Roles 相关 hooks
 */

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { get } from './client';
import { ProjectStatusSchema, RoleSchema, SkillSchema } from './types';
import type { ProjectStatus, Role, Skill } from './types';

const DEFAULT_PROJECT_ROOT = '.';

export const projectKeys = {
  status: (projectRoot = DEFAULT_PROJECT_ROOT) => ['status', projectRoot] as const,
  skills: ['skills'] as const,
  roles: ['roles'] as const,
};

/** 项目状态（未初始化返回 {initialized: false}） */
export function useProjectStatus(projectRoot = DEFAULT_PROJECT_ROOT) {
  return useQuery({
    queryKey: projectKeys.status(projectRoot),
    queryFn: async () => {
      const data = await get<unknown>(`/api/status?project_root=${encodeURIComponent(projectRoot)}`);
      return ProjectStatusSchema.parse(data);
    },
    staleTime: 60_000,
    retry: false, // 404 (未初始化) 不重试
  });
}

/** Skills 列表（13 个） */
export function useSkills() {
  return useQuery({
    queryKey: projectKeys.skills,
    queryFn: async () => {
      const data = await get<unknown>('/api/skills');
      return z.array(SkillSchema).parse(data);
    },
    staleTime: 5 * 60_000,
  });
}

/** Roles 列表（7 个） */
export function useRoles() {
  return useQuery({
    queryKey: projectKeys.roles,
    queryFn: async () => {
      const data = await get<unknown>('/api/roles');
      return z.array(RoleSchema).parse(data);
    },
    staleTime: 5 * 60_000,
  });
}

export type { ProjectStatus, Skill, Role };
