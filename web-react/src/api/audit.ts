/**
 * 审计日志 hooks（admin only）
 */

import { useQuery } from '@tanstack/react-query';

import { get } from './client';
import { AuditLogSchema, type AuditEvent } from './types';

export const auditKeys = {
  all: (filters: { event_type?: string; user_id?: number; limit?: number }) =>
    ['audit', filters] as const,
};

export interface AuditFilters {
  event_type?: string;
  user_id?: number;
  limit?: number;
}

/** 查询审计日志（admin only） */
export function useAuditLog(filters: AuditFilters = {}, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: auditKeys.all(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.event_type) params.set('event_type', filters.event_type);
      if (filters.user_id != null) params.set('user_id', String(filters.user_id));
      params.set('limit', String(filters.limit ?? 100));
      const data = await get<unknown>(`/api/auth/audit?${params.toString()}`);
      return AuditLogSchema.parse(data);
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
  });
}

export type { AuditEvent };
