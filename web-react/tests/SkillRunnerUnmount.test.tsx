/**
 * SkillRunner 卸载取消 in-flight task 测试 (V1.5.1 已知问题 #2)
 *
 * 验证场景：
 *   - 用户点击执行 → task 启动 → 用户导航离开（unmount）
 *   - cleanup 必须取消当前 task（不是首次渲染时的 null）
 *
 * Bug 背景（旧实现）：
 *   - useEffect `[]` deps，cleanup 捕获首次渲染时的 taskId=null
 *   - 卸载看到旧值（null），无法取消 in-flight task → 后端 pipeline orphan
 *
 * Fix：用 ref 跟踪最新 taskId，cleanup 读 ref.current
 *
 * 测试方法：
 *   - vi.hoisted 把 mock 函数 hoist 到 vi.mock factory 之前
 *   - 用 postForm 返回 mock 响应（task_id）
 *   - fireEvent.click 后 unmount → cancel 应被调
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { SkillRunner } from '../src/components/skill/SkillRunner';
import type { SkillInfo } from '../src/types/skills';

// vi.hoisted: 把 mock 函数 hoist 到 vi.mock factory 之前（vitest 要求）
const mocks = vi.hoisted(() => ({
  cancel: vi.fn().mockResolvedValue(undefined),
  stream: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../src/hooks/useSkillStream', () => ({
  useSkillStream: () => ({
    stream: mocks.stream,
    cancel: mocks.cancel,
  }),
}));

vi.mock('../src/api/client', () => ({
  apiClient: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
  postForm: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

const mockSkill: SkillInfo = {
  name: 'story-long-write',
  description: '长篇写作',
  userInvocable: true,
  modelInvocable: false,
  category: '创作类',
  icon: 'Edit',
  emoji: '✍️',
  version: '1.0',
  defaultInput: '林雷觉醒血脉',
};

function renderRunner() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <SkillRunner skill={mockSkill} />
    </QueryClientProvider>,
  );
}

describe('SkillRunner unmount cancel (V1.5.1 已知问题 #2)', () => {
  beforeEach(async () => {
    mocks.cancel.mockClear();
    mocks.stream.mockClear();
    // 默认：postForm 返回 in-flight task
    // 注意 status 必须是 SkillExecuteResponseSchema 的合法值（'running' / 'queued' / 'done' / 'failed' / 'cancelled'）
    const { postForm } = await import('../src/api/client');
    (postForm as ReturnType<typeof vi.fn>).mockResolvedValue({
      task_id: 'in-flight-task-id',
      status: 'running',
    });
  });

  it('unmount 时 cancel 被调用（in-flight task）', async () => {
    // Act: 渲染组件 + 点击执行
    const { unmount } = renderRunner();
    fireEvent.click(screen.getByTestId('execute-story-long-write'));

    // 等待 phase → running + taskId 已设置
    // 注意：取消按钮在 phase='preparing' 或 'running' 都显示；
    // 但 taskId 必须在 setTaskId 后才设置。
    // 我们等 onDone 之前的稳定状态（按钮显示 + 几个微任务）。
    await waitFor(
      () => {
        expect(screen.getByLabelText('取消执行')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    // 等多个 microtask 确保 taskId 已通过 ref sync 设置
    await new Promise((resolve) => setTimeout(resolve, 50));

    // 模拟用户导航离开 → unmount
    unmount();

    // Assert: cleanup 调 cancel(taskId)
    expect(mocks.cancel).toHaveBeenCalled();
    const callArg = mocks.cancel.mock.calls[0]?.[0];
    expect(callArg).toBeTruthy();
    expect(typeof callArg).toBe('string');
    expect(callArg).toBe('in-flight-task-id');
  });

  it('unmount without execute: cancel 不被调用（无 in-flight task）', () => {
    // Act: 不点执行，直接 unmount
    const { unmount } = renderRunner();
    unmount();

    // Assert
    expect(mocks.cancel).not.toHaveBeenCalled();
  });

  it('ref 捕获最新 taskId（旧实现 bug 是捕获首次 null）', async () => {
    // 验证核心 fix：ref.current 在 unmount 时是最新 taskId，不是首次的 null
    const { postForm } = await import('../src/api/client');
    (postForm as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      task_id: 'ref-test-task-123',
      status: 'running',
    });

    const { unmount } = renderRunner();
    fireEvent.click(screen.getByTestId('execute-story-long-write'));

    // 等 phase=running
    await waitFor(() => {
      expect(screen.getByLabelText('取消执行')).toBeInTheDocument();
    });

    unmount();

    expect(mocks.cancel).toHaveBeenCalledWith('ref-test-task-123');
  });
});