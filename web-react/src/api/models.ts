/**
 * 模型选择相关 hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { get, postForm } from './client';
import {
  CurrentModelSchema,
  ModelSchema,
  ModelSwitchResponseSchema,
  type CurrentModel,
  type Model,
  type ModelSwitchResponse,
} from './types';

export const modelKeys = {
  all: ['models'] as const,
  current: ['model', 'current'] as const,
};

/** 所有可用模型 */
export function useModels() {
  return useQuery({
    queryKey: modelKeys.all,
    queryFn: async () => {
      const data = await get<unknown>('/api/models');
      return z.array(ModelSchema).parse(data);
    },
    staleTime: 5 * 60_000,
  });
}

/** 当前模型 */
export function useCurrentModel() {
  return useQuery({
    queryKey: modelKeys.current,
    queryFn: async () => {
      const data = await get<unknown>('/api/model/current');
      return CurrentModelSchema.parse(data);
    },
    staleTime: Infinity, // 仅 invalidate 时重读
  });
}

/** 切换模型 */
export function useSwitchModel() {
  const qc = useQueryClient();
  return useMutation<ModelSwitchResponse, Error, string>({
    mutationFn: async (model) => {
      const data = await postForm<unknown>('/api/model/switch', { model });
      return ModelSwitchResponseSchema.parse(data);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: modelKeys.current });
    },
  });
}

export type { Model, CurrentModel };
