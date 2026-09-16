/**
 * SkillOutput 单元测试
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SkillOutput } from '../src/components/skill/SkillOutput';
import type { SkillOutputChunk } from '../src/types/skills';

describe('SkillOutput', () => {
  it('renders empty hint when idle', () => {
    render(<SkillOutput chunks={[]} phase="idle" />);
    expect(screen.getByText(/输入参数后点击/)).toBeInTheDocument();
  });

  it('renders aggregated text from chunks', () => {
    const chunks: SkillOutputChunk[] = [
      { type: 'text', text: '你好, ' },
      { type: 'text', text: '世界' },
    ];
    render(<SkillOutput chunks={chunks} phase="success" />);
    expect(screen.getByText('你好, 世界')).toBeInTheDocument();
  });

  it('shows success chip when phase=success', () => {
    render(<SkillOutput chunks={[{ type: 'text', text: '完成' }]} phase="success" />);
    expect(screen.getByText('已完成')).toBeInTheDocument();
  });

  it('shows error chip when phase=error with errorMsg', () => {
    render(<SkillOutput chunks={[]} phase="error" errorMsg="网络断开" />);
    expect(screen.getByText('网络断开')).toBeInTheDocument();
  });

  it('shows cancelled chip when phase=cancelled', () => {
    render(<SkillOutput chunks={[{ type: 'text', text: 'partial' }]} phase="cancelled" />);
    expect(screen.getByText('已取消')).toBeInTheDocument();
  });

  it('renders progress phase chip when running', () => {
    render(
      <SkillOutput
        chunks={[{ type: 'text', text: '生成中' }]}
        phase="running"
        progress={{ phase: 'writing', charsWritten: 1234 }}
      />,
    );
    expect(screen.getByText(/写作中/)).toBeInTheDocument();
  });
});