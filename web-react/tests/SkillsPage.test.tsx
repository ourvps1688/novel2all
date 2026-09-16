/**
 * SkillsPage 单元测试
 *
 * 验证：
 *   - 13 skill 卡片分组展示
 *   - 分类筛选 chip 工作
 *   - 搜索框工作
 *   - 内部 skill 不展示
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { SkillsPage } from '../src/pages/SkillsPage';

// ============ Mock ============

const MOCK_SKILLS = [
  { name: 'story', description: '智能路由', user_invocable: true, model_invocable: true },
  { name: 'story-setup', description: '初始化', user_invocable: true, model_invocable: false },
  { name: 'story-long-write', description: '长篇写作', user_invocable: true, model_invocable: false },
  { name: 'story-long-analyze', description: '长篇拆文', user_invocable: true, model_invocable: false },
  { name: 'story-long-scan', description: '长篇扫榜', user_invocable: true, model_invocable: false },
  { name: 'story-short-write', description: '短篇写作', user_invocable: true, model_invocable: false },
  { name: 'story-short-analyze', description: '短篇拆文', user_invocable: true, model_invocable: false },
  { name: 'story-short-scan', description: '短篇扫榜', user_invocable: true, model_invocable: false },
  { name: 'story-cover', description: '封面生成', user_invocable: true, model_invocable: false },
  { name: 'story-deslop', description: '去 AI 味', user_invocable: true, model_invocable: false },
  { name: 'story-review', description: '4 视角审查', user_invocable: true, model_invocable: false },
  { name: 'story-import', description: '导入', user_invocable: true, model_invocable: false },
  { name: 'browser-cdp', description: '内部浏览器', user_invocable: false, model_invocable: true },
];

vi.mock('../src/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  get: vi.fn(),
  post: vi.fn(),
  postForm: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

function renderSkillsPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SkillsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SkillsPage', () => {
  beforeEach(async () => {
    const { get } = await import('../src/api/client');
    (get as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_SKILLS);
  });

  it('renders header with skill count', async () => {
    renderSkillsPage();
    await waitFor(() => {
      expect(screen.getByText(/共 13 个能力/)).toBeInTheDocument();
    });
  });

  it('groups skills by category', async () => {
    renderSkillsPage();
    await waitFor(() => {
      expect(screen.getByTestId('skill-group-创作类')).toBeInTheDocument();
      expect(screen.getByTestId('skill-group-分析类')).toBeInTheDocument();
      expect(screen.getByTestId('skill-group-工具类')).toBeInTheDocument();
      expect(screen.getByTestId('skill-group-入口类')).toBeInTheDocument();
    });
  });

  it('hides internal skills (browser-cdp)', async () => {
    renderSkillsPage();
    await waitFor(() => {
      expect(screen.queryByTestId('skill-card-browser-cdp')).not.toBeInTheDocument();
    });
  });

  it('shows 12 visible cards (13 - 1 internal)', async () => {
    renderSkillsPage();
    await waitFor(() => {
      const cards = document.querySelectorAll('[data-testid^="skill-card-"]');
      expect(cards.length).toBe(12);
    });
  });

  it('filters by category chip', async () => {
    renderSkillsPage();
    await waitFor(() => screen.getByTestId('skill-group-工具类'));
    // 工具类只在 chip 上 click, 这里直接通过按钮 (role=button + name=工具类)
    // 注意: 由于 "工具类" 出现多次 (chip + section heading), 用 getAllByRole 然后选第一个
    const buttons = screen.getAllByRole('button', { name: '工具类' });
    fireEvent.click(buttons[0]!);
    await waitFor(() => {
      expect(screen.getByTestId('skill-group-工具类')).toBeInTheDocument();
      // 工具类只有 3 个 (deslop / review / import)
      const cards = screen.getByTestId('skill-group-工具类').querySelectorAll('[data-testid^="skill-card-"]');
      expect(cards.length).toBe(3);
    });
  });

  it('shows empty state when no match', async () => {
    renderSkillsPage();
    // 等加载完成 (search input 出现)
    await waitFor(() => screen.getByLabelText('搜索 skill'));
    const search = screen.getByLabelText('搜索 skill');
    fireEvent.change(search, { target: { value: 'zzzzz_no_match' } });
    await waitFor(() => {
      expect(screen.getByText(/没有匹配的 skill/)).toBeInTheDocument();
    });
  });
});