/**
 * Dashboard 测试
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { DashboardPage } from '../src/pages/DashboardPage';
import { AuthProvider } from '../src/auth/AuthProvider';

vi.mock('../src/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    postForm: vi.fn(),
    delete: vi.fn(),
  },
  setUnauthorizedHandler: vi.fn(),
}));

function renderDashboard() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage', () => {
  it('shows onboarding wizard when project not initialized', async () => {
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes('/api/auth/me'))
        return Promise.resolve({
          user: { id: 1, username: 'admin', role: 'admin', created_at: Date.now() / 1000, disabled: false },
          authenticated: true,
        });
      if (url.includes('/api/status')) return Promise.resolve({ initialized: false });
      return Promise.resolve({});
    });

    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 novel2all/)).toBeInTheDocument();
    });
  });

  it('shows 4 dashboard cards when project initialized', async () => {
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes('/api/auth/me'))
        return Promise.resolve({
          user: { id: 1, username: 'admin', role: 'admin', created_at: Date.now() / 1000, disabled: false },
          authenticated: true,
        });
      if (url.includes('/api/status')) return Promise.resolve({
        initialized: true,
        project_name: '测试小说',
        total_chapters_target: 50,
        character_count: 10,
        active_foreshadowing_count: 3,
        timeline_count: 25,
      });
      if (url.includes('/api/chapters')) return Promise.resolve([]);
      if (url.includes('/api/cache/stats')) return Promise.resolve({
        enabled: true,
        backend: 'memory',
        size: 1000,
        max_size: 10000,
        hits: 80,
        misses: 20,
        hit_rate: 0.8,
        ttl_seconds: 3600,
        persist_path: null,
        lock_backend: 'threading',
        prompt_prefix: {
          prefix_hits: 50,
          prefix_misses: 10,
          total: 60,
          hit_rate: 0.83,
          unique_sys_prompts: 5,
          cost_saved_cny: 12.5,
          potential_savings_cny: 30,
          enabled: true,
          model: null,
        },
      });
      return Promise.resolve({});
    });

    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('当前章节')).toBeInTheDocument();
      expect(screen.getByText('项目进度')).toBeInTheDocument();
      expect(screen.getByText('Cache 状态')).toBeInTheDocument();
      expect(screen.getByText('今日节省')).toBeInTheDocument();
    });
  });
});
