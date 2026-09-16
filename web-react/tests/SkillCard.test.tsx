/**
 * SkillCard 单元测试
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
});