/**
 * SkillHistory 单元测试
 *
 * 验证：
 *   - 空状态显示
 *   - 折叠/展开切换
 *   - 历史记录渲染
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { SkillHistory } from '../src/components/skill/SkillHistory';
import { useSkillExecutionStore } from '../src/store/skillExecutionStore';

function resetStore(): void {
  useSkillExecutionStore.setState({ history: {}, current: {} });
}

describe('SkillHistory', () => {
  beforeEach(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.clear();
    }
    resetStore();
  });

  it('renders header', () => {
    render(<SkillHistory skillName="story-setup" />);
    expect(screen.getByText(/最近执行/)).toBeInTheDocument();
  });

  it('shows empty state when no history', async () => {
    render(<SkillHistory skillName="story-setup" defaultCollapsed={false} />);
    expect(screen.getByText('暂无执行记录')).toBeInTheDocument();
  });

  it('renders history rows after startRun', () => {
    useSkillExecutionStore.getState().startRun('story-setup', '测试输入');
    useSkillExecutionStore.getState().finishRun('story-setup', useSkillExecutionStore.getState().history['story-setup']![0]!.taskId, 'success', '输出');
    render(<SkillHistory skillName="story-setup" defaultCollapsed={false} limit={5} />);
    expect(screen.getByText('成功')).toBeInTheDocument();
    expect(screen.getByText(/输入: 测试输入/)).toBeInTheDocument();
  });

  it('collapses/expands on button click', () => {
    render(<SkillHistory skillName="story-setup" defaultCollapsed={true} />);
    // Collapse 隐藏时元素还在 DOM 中, 用 toBeVisible 判断
    expect(screen.queryByText('暂无执行记录')).not.toBeVisible();
    fireEvent.click(screen.getByLabelText('展开历史'));
    expect(screen.getByText('暂无执行记录')).toBeVisible();
  });
});