/**
 * api/skills hooks 单元测试
 *
 * 验证：
 *   - useSkills 拉取 + zod 校验
 *   - useExecuteSkill 调用 postForm
 *   - useSkillStatus 校验 queryKey
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';

vi.mock('../src/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  get: vi.fn(),
  post: vi.fn(),
  postForm: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

import { useSkills, useSkill, useExecuteSkill, useSkillStatus, skillKeys } from '../src/api/skills';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children);
  };
}

describe('useSkills', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches and parses skill list with category metadata', async () => {
    const { get } = await import('../src/api/client');
    (get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { name: 'story-setup', description: 'A', user_invocable: true, model_invocable: false },
      { name: 'browser-cdp', description: 'B', user_invocable: false, model_invocable: true },
    ]);
    const { result } = renderHook(() => useSkills(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const skills = result.current.data ?? [];
    expect(skills).toHaveLength(2);
    expect(skills[0]?.category).toBe('创作类');
    expect(skills[1]?.category).toBe('内部');
  });
});

describe('useSkill', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns null when name is undefined', async () => {
    const { result } = renderHook(() => useSkill(undefined), { wrapper: makeWrapper() });
    expect(result.current).toBeNull();
  });

  it('returns null when skill not found', async () => {
    const { get } = await import('../src/api/client');
    (get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { name: 'story-setup', description: 'A', user_invocable: true, model_invocable: false },
    ]);
    const { result } = renderHook(() => useSkill('nonexistent'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current).toBeNull());
  });

  it('finds the requested skill by name', async () => {
    const { get } = await import('../src/api/client');
    (get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { name: 'story-setup', description: 'A', user_invocable: true, model_invocable: false },
      { name: 'story-long-write', description: 'B', user_invocable: true, model_invocable: false },
    ]);
    const { result } = renderHook(() => useSkill('story-long-write'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current?.name).toBe('story-long-write'));
  });
});

describe('useExecuteSkill', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls postForm and parses response', async () => {
    const { postForm } = await import('../src/api/client');
    (postForm as ReturnType<typeof vi.fn>).mockResolvedValue({
      task_id: 't-001',
      status: 'queued',
      started_at: Date.now(),
    });
    const { result } = renderHook(() => useExecuteSkill('story-setup'), { wrapper: makeWrapper() });
    await result.current.mutateAsync({ params: { project_name: '测试' } });
    expect(postForm).toHaveBeenCalledWith(
      '/api/skills/story-setup/execute',
      expect.objectContaining({ project_root: '.' }),
    );
  });
});

describe('useSkillStatus', () => {
  it('is disabled by default', () => {
    const { result } = renderHook(
      () => useSkillStatus('story-setup', 't-1'),
      { wrapper: makeWrapper() },
    );
    expect(result.current.isFetching).toBe(false);
  });
});

describe('skillKeys', () => {
  it('builds stable query keys', () => {
    expect(skillKeys.all).toEqual(['skills']);
    expect(skillKeys.detail('story-setup')).toEqual(['skills', 'detail', 'story-setup']);
    expect(skillKeys.status('story-setup', 't-1')).toEqual(['skills', 'status', 'story-setup', 't-1']);
  });
});