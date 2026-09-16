/**
 * SkillRunner 单元测试 (轻量版)
 *
 * 验证：
 *   - 渲染 skill name + 输入框 + 执行按钮
 *   - 点击执行按钮触发 mutation
 *   - 错误状态显示 Alert
 *
 * 注：完整 SSE + 进度流测试在 useSkillStream.test.ts
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { SkillRunner } from '../src/components/skill/SkillRunner';
import type { SkillInfo } from '../src/types/skills';

const mockSkill: SkillInfo = {
  name: 'story-setup',
  description: '初始化项目',
  userInvocable: true,
  modelInvocable: false,
  category: '创作类',
  icon: 'Settings',
  emoji: '⚙️',
  version: '1.0',
  defaultInput: '默认输入',
};

// Mock api/client (used by useExecuteSkill → postForm)
vi.mock('../src/api/client', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
  },
  postForm: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

// Mock useSkillStream (避免 EventSource 复杂性)
vi.mock('../src/hooks/useSkillStream', () => ({
  useSkillStream: () => ({
    stream: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn().mockResolvedValue(undefined),
  }),
}));

function renderRunner(skill: SkillInfo = mockSkill) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <SkillRunner skill={skill} />
    </QueryClientProvider>,
  );
}

describe('SkillRunner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders skill name and version', () => {
    renderRunner();
    expect(screen.getByText('story-setup')).toBeInTheDocument();
    expect(screen.getByText(/v1\.0/)).toBeInTheDocument();
  });

  it('renders input textarea with defaultInput as value', () => {
    renderRunner();
    const textarea = screen.getByLabelText('skill 输入');
    expect(textarea).toHaveValue('默认输入');
  });

  it('renders execute button', () => {
    renderRunner();
    expect(screen.getByTestId('execute-story-setup')).toBeInTheDocument();
  });

  it('execute button is disabled when input is empty', () => {
    renderRunner({ ...mockSkill, defaultInput: '' });
    const button = screen.getByTestId('execute-story-setup');
    expect(button).toBeDisabled();
  });

  it('execute button is enabled when input is non-empty', () => {
    renderRunner();
    const button = screen.getByTestId('execute-story-setup');
    expect(button).not.toBeDisabled();
  });

  it('shows cancel button after clicking execute (loading state)', async () => {
    const { postForm } = await import('../src/api/client');
    (postForm as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        new Promise(() => {
          /* never resolve → keeps loading */
        }),
    );
    renderRunner();
    fireEvent.click(screen.getByTestId('execute-story-setup'));
    await waitFor(() => {
      expect(screen.getByLabelText('取消执行')).toBeInTheDocument();
    });
  });

  it('shows error Alert when execute fails', async () => {
    const { postForm } = await import('../src/api/client');
    (postForm as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('服务器异常 500'));
    renderRunner();
    fireEvent.click(screen.getByTestId('execute-story-setup'));
    await waitFor(() => {
      // 多个元素包含此文本 (Alert + SkillOutput errorMsg)
      expect(screen.getAllByText(/服务器异常/).length).toBeGreaterThan(0);
    });
  });
});