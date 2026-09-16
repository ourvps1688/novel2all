/**
 * SkillCard 单元测试
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #5）：
 *   - 新增 isInternal prop 测试
 *   - 验证 internal skill 显示 "内部工具" chip
 *   - 验证非 internal skill 不显示该 chip
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { SkillCard } from '../src/components/skill/SkillCard';
import type { SkillInfo, SkillExecutionHistoryEntry } from '../src/types/skills';

const mockSkill: SkillInfo = {
  name: 'story-long-write',
  description: '长篇 AI 续写',
  userInvocable: true,
  modelInvocable: false,
  category: '创作类',
  icon: 'Edit',
  emoji: '✍️',
  version: '1.0',
  defaultInput: '',
};

const mockInternalSkill: SkillInfo = {
  name: 'browser-cdp',
  description: '内部浏览器能力',
  userInvocable: false,
  modelInvocable: true,
  category: '内部',
  icon: 'Lock',
  emoji: '🌐',
  version: '1.0',
  defaultInput: 'URL',
};

const mockLastRun: SkillExecutionHistoryEntry = {
  skillName: 'story-long-write',
  taskId: 't-1',
  startedAt: Date.now() - 5000,
  finishedAt: Date.now(),
  status: 'success',
  inputPreview: '测试',
  outputPreview: '输出',
  durationMs: 5000,
};

describe('SkillCard', () => {
  it('renders skill name and description', () => {
    render(<SkillCard skill={mockSkill} onClick={() => {}} />);
    expect(screen.getByText('story-long-write')).toBeInTheDocument();
    expect(screen.getByText('长篇 AI 续写')).toBeInTheDocument();
  });

  it('renders version and category chip', () => {
    render(<SkillCard skill={mockSkill} onClick={() => {}} />);
    expect(screen.getByText(/v1\.0/)).toBeInTheDocument();
    expect(screen.getByText('创作类')).toBeInTheDocument();
  });

  it('fires onClick when card is clicked', () => {
    const onClick = vi.fn();
    render(<SkillCard skill={mockSkill} onClick={onClick} />);
    fireEvent.click(screen.getByText('story-long-write'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('renders last run chip when lastRun is provided', () => {
    render(<SkillCard skill={mockSkill} lastRun={mockLastRun} onClick={() => {}} />);
    expect(screen.getByText(/成功 ·/)).toBeInTheDocument();
  });

  it('renders "未运行" when no lastRun', () => {
    render(<SkillCard skill={mockSkill} onClick={() => {}} />);
    expect(screen.getByText('未运行')).toBeInTheDocument();
  });

  it('falls back to default icon when skill.icon is unknown', () => {
    const skillUnknownIcon = { ...mockSkill, icon: 'NonExistent' };
    render(<SkillCard skill={skillUnknownIcon} onClick={() => {}} />);
    // 应该不抛错; Extension icon 会渲染
    expect(screen.getByText('story-long-write')).toBeInTheDocument();
  });

  // ===== V1.5.1 Sprint 1.1 修复（已知问题 #5）新增测试 =====

  describe('isInternal prop (V1.5.1 Sprint 1.1 已知问题 #5 修复)', () => {
    it('isInternal=true 时显示 "内部工具" chip', () => {
      render(
        <SkillCard skill={mockInternalSkill} onClick={() => {}} isInternal={true} />,
      );
      expect(
        screen.getByTestId('skill-internal-badge-browser-cdp'),
      ).toBeInTheDocument();
      expect(screen.getByText('内部工具')).toBeInTheDocument();
    });

    it('isInternal=false 时不显示 "内部工具" chip', () => {
      render(<SkillCard skill={mockSkill} onClick={() => {}} isInternal={false} />);
      expect(
        screen.queryByTestId('skill-internal-badge-story-long-write'),
      ).not.toBeInTheDocument();
      expect(screen.queryByText('内部工具')).not.toBeInTheDocument();
    });

    it('isInternal 未传 (默认 false) 时不显示 chip', () => {
      // 不传 isInternal prop, 默认 false
      render(<SkillCard skill={mockSkill} onClick={() => {}} />);
      expect(
        screen.queryByTestId('skill-internal-badge-story-long-write'),
      ).not.toBeInTheDocument();
    });

    it('即使 category="内部", isInternal=false 时也不显示 chip', () => {
      // 防御性测试：将来若某 skill 既有 category="内部" 又有 isInternal=false，
      // 不应显示 chip (chip 由 isInternal flag 唯一控制)
      render(
        <SkillCard skill={mockInternalSkill} onClick={() => {}} isInternal={false} />,
      );
      expect(
        screen.queryByTestId('skill-internal-badge-browser-cdp'),
      ).not.toBeInTheDocument();
    });

    it('即使 category="创作类", isInternal=true 时也显示 chip', () => {
      // 防御性测试：将来若某 skill 既有 category="创作类" 又有 isInternal=true，
      // 应显示 chip (chip 由 isInternal flag 唯一控制)
      render(<SkillCard skill={mockSkill} onClick={() => {}} isInternal={true} />);
      expect(
        screen.getByTestId('skill-internal-badge-story-long-write'),
      ).toBeInTheDocument();
    });

    it('内部 skill 仍可点击 (onClick 仍触发)', () => {
      const onClick = vi.fn();
      render(
        <SkillCard
          skill={mockInternalSkill}
          onClick={onClick}
          isInternal={true}
        />,
      );
      fireEvent.click(screen.getByText('browser-cdp'));
      expect(onClick).toHaveBeenCalledTimes(1);
    });
  });
});