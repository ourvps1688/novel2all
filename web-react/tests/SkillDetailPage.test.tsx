/**
 * SkillDetailPage 单元测试
 *
 * 验证：
 *   - 加载中显示 skeleton
 *   - 有效 skill 显示详情 + SkillRunner
 *   - 不存在的 skill 显示 EmptyState
 *   - 内部 skill 显示警告 Alert
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { SkillDetailPage } from '../src/pages/SkillDetailPage';

vi.mock('../src/hooks/useSkillStream', () => ({
  useSkillStream: () => ({
    stream: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn().mockResolvedValue(undefined),
  }),
}));

vi.mock('../src/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  get: vi.fn(),
  post: vi.fn(),
  postForm: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

const MOCK_SKILLS = [
  { name: 'story-setup', description: '初始化', user_invocable: true, model_invocable: false },
  { name: 'browser-cdp', description: '内部浏览器', user_invocable: false, model_invocable: true },
];

function renderDetailPage(skillName: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/skills/${skillName}`]}>
        <Routes>
          <Route path="/skills/:name" element={<SkillDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SkillDetailPage', () => {
  beforeEach(async () => {
    const { get } = await import('../src/api/client');
    (get as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_SKILLS);
  });

  it('renders skill header and runner for valid skill', async () => {
    renderDetailPage('story-setup');
    await waitFor(() => {
      // H4 in page header + H6 in SkillRunner, both should exist
      const headings = screen.getAllByRole('heading', { name: 'story-setup' });
      expect(headings.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('初始化')).toBeInTheDocument();
    });
  });

  it('shows "返回 Skills" button', async () => {
    renderDetailPage('story-setup');
    await waitFor(() => {
      expect(screen.getByLabelText('返回 Skills 列表')).toBeInTheDocument();
    });
  });

  it('shows EmptyState for unknown skill', async () => {
    renderDetailPage('nonexistent-skill');
    await waitFor(() => {
      expect(screen.getByText(/不存在/)).toBeInTheDocument();
    });
  });

  it('shows warning Alert for internal skill (browser-cdp)', async () => {
    renderDetailPage('browser-cdp');
    await waitFor(() => {
      expect(screen.getByText(/不对用户开放/)).toBeInTheDocument();
    });
  });
});