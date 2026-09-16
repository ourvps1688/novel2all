/**
 * Skill API 层 hooks (React Query)
 *
 * 提供 4 个核心 hook：
 *   - useSkills()       - GET /api/skills              列表
 *   - useSkill(name)    - GET /api/skills (client 过滤) 单个
 *   - useExecuteSkill() - POST /api/skills/{name}/execute 启动 task
 *   - useSkillStatus()  - GET /api/skills/{name}/status    状态查询 (polling 兜底)
 *
 * 设计要点：
 *   - 全部走 axios + zod runtime 校验 (api/types.ts 的 SkillSchema)
 *   - 复用 api/projects.ts 的 useSkills（避免重复 queryKey）
 *   - useExecuteSkill 返回 mutation (符合 React Query 习惯)
 *   - useSkillStatus 仅在 polling 降级时启用（避免常态请求）
 */

import { useMutation, useQuery, type UseQueryResult } from '@tanstack/react-query';
import { z } from 'zod';

import { get, postForm } from './client';
import { SkillSchema, type Skill } from './types';
import {
  SkillExecuteResponseSchema,
  SkillStatusResponseSchema,
  type SkillExecuteResponse,
  type SkillStatusResponse,
} from '../types/skills';
import type { SkillInfo } from '../types/skills';
import { CATEGORY_MAP } from '../data/skillCategories';

// ============ Query Keys ============

export const skillKeys = {
  all: ['skills'] as const,
  detail: (name: string) => ['skills', 'detail', name] as const,
  status: (name: string, taskId: string) => ['skills', 'status', name, taskId] as const,
};

// ============ useSkills (复用 projects.ts 的同名 hook，叠加元数据) ============

/**
 * 列出全部 skill, 叠加前端硬编码元数据 (category/icon/inputSchema)
 *
 * 注意：与 api/projects.ts 的 useSkills 共享 queryKey ['skills']
 * 任何组件调用 useSkills() 都会命中同一缓存
 */
export function useSkills(): UseQueryResult<SkillInfo[], Error> {
  return useQuery({
    queryKey: skillKeys.all,
    queryFn: async (): Promise<SkillInfo[]> => {
      const data = await get<unknown>('/api/skills');
      const skills = z.array(SkillSchema).parse(data);
      return skills.map(toSkillInfo);
    },
    staleTime: 5 * 60_000, // 5 分钟 (skill 列表不会频繁变)
    retry: 1,
  });
}

// ============ useSkill (单 skill) ============

/**
 * 取单个 skill 元信息 (从 useSkills 缓存过滤; 若未加载则触发 fetch)
 */
export function useSkill(name: string | undefined): SkillInfo | null {
  const result = useQuery({
    queryKey: skillKeys.detail(name ?? ''),
    queryFn: async (): Promise<SkillInfo | null> => {
      if (!name) return null;
      const data = await get<unknown>('/api/skills');
      const skills = z.array(SkillSchema).parse(data);
      const found = skills.find((s) => s.name === name);
      return found ? toSkillInfo(found) : null;
    },
    enabled: Boolean(name),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  return result.data ?? null;
}

// ============ useExecuteSkill ============

export interface ExecuteSkillVariables {
  /** Skill 调用参数 (与 inputSchema 对齐) */
  params: Record<string, unknown>;
  /** 项目根 (默认 ".") */
  projectRoot?: string;
  /** 幂等键 (避免重复扣费); 不传则自动生成 */
  idempotencyKey?: string;
}

/**
 * 启动 skill 执行
 *
 * 返回 task_id, 后续通过 useSkillStream 订阅 SSE
 */
export function useExecuteSkill(skillName: string) {
  return useMutation<SkillExecuteResponse, Error, ExecuteSkillVariables>({
    mutationFn: async (vars) => {
      const data = await postForm<unknown>(`/api/skills/${encodeURIComponent(skillName)}/execute`, {
        params: JSON.stringify(vars.params ?? {}),
        project_root: vars.projectRoot ?? '.',
        idempotency_key: vars.idempotencyKey ?? '',
      });
      return SkillExecuteResponseSchema.parse(data);
    },
  });
}

// ============ useSkillStatus (polling 兜底) ============

/**
 * 查询 skill task 状态 (用于 SSE 降级后的 polling, 或外部调试)
 *
 * 默认禁用（enabled=false），由 useSkillStream 在降级时启用
 */
export function useSkillStatus(
  skillName: string | undefined,
  taskId: string | undefined,
  options: { enabled?: boolean; refetchInterval?: number } = {},
): UseQueryResult<SkillStatusResponse, Error> {
  const { enabled = false, refetchInterval = 0 } = options;
  return useQuery({
    queryKey: skillKeys.status(skillName ?? '', taskId ?? ''),
    queryFn: async (): Promise<SkillStatusResponse> => {
      if (!skillName || !taskId) {
        throw new Error('skillName and taskId required');
      }
      const data = await get<unknown>(
        `/api/skills/${encodeURIComponent(skillName)}/status?task_id=${encodeURIComponent(taskId)}`,
      );
      return SkillStatusResponseSchema.parse(data);
    },
    enabled: enabled && Boolean(skillName) && Boolean(taskId),
    refetchInterval: refetchInterval > 0 ? refetchInterval : false,
    retry: 1,
  });
}

// ============ 内部: 叠加前端元数据 ============

/**
 * 把后端 Skill (api/types.ts) 转成 UI 层 SkillInfo (types/skills.ts)
 * 缺失字段全部从 CATEGORY_MAP 兜底
 */
function toSkillInfo(s: Skill): SkillInfo {
  const meta = CATEGORY_MAP[s.name];
  return {
    name: s.name,
    description: s.description ?? meta?.label ?? s.name,
    userInvocable: s.user_invocable ?? meta?.category !== '内部',
    modelInvocable: s.model_invocable ?? false,
    category: meta?.category ?? '工具类',
    icon: meta?.icon ?? 'Extension',
    emoji: meta?.emoji ?? '🛠️',
    version: meta?.version ?? '1.0',
    inputSchema: meta?.inputSchema,
    defaultInput: meta?.defaultInput ?? '',
  };
}

// ============ Re-export ============

export type { SkillInfo };
export type { SkillExecuteResponse, SkillStatusResponse };