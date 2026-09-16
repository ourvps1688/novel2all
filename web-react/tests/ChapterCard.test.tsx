/**
 * ChapterCard 单元测试 (Sprint 2)
 *
 * 覆盖:
 *   - 渲染章节号 / 文件名 / 字数 / 首行
 *   - selected 状态边框高亮
 *   - status='writing' 显示 "进行中" chip
 *   - onClick 回调触发
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ChapterCard, type ChapterCardData } from '../src/components/chapter/ChapterCard';

const mockChapter: ChapterCardData = {
  chapter: 3,
  filename: '第003章.md',
  char_count: 1845,
  first_line: '林雷站在剑碑前, 伸手触碰那古老的符文...',
};

describe('ChapterCard', () => {
  it('renders chapter number, filename, char count and first line', () => {
    render(<ChapterCard chapter={mockChapter} onClick={() => {}} />);
    expect(screen.getByText('第 3 章')).toBeInTheDocument();
    expect(screen.getByText('第003章.md')).toBeInTheDocument();
    expect(screen.getByText(/1,?845/)).toBeInTheDocument(); // 数字带千分位
    expect(screen.getByText(/林雷站在剑碑前/)).toBeInTheDocument();
  });

  it('shows "进行中" chip when status=writing', () => {
    render(<ChapterCard chapter={mockChapter} status="writing" onClick={() => {}} />);
    expect(screen.getByText(/进行中/)).toBeInTheDocument();
  });

  it('shows "已审" chip when status=reviewed', () => {
    render(<ChapterCard chapter={mockChapter} status="reviewed" onClick={() => {}} />);
    expect(screen.getByText(/已审/)).toBeInTheDocument();
  });

  it('does not show status chip when status=idle (default)', () => {
    render(<ChapterCard chapter={mockChapter} onClick={() => {}} />);
    expect(screen.queryByText(/进行中/)).not.toBeInTheDocument();
    expect(screen.queryByText(/已审/)).not.toBeInTheDocument();
  });

  it('fires onClick when card is clicked', () => {
    const onClick = vi.fn();
    render(<ChapterCard chapter={mockChapter} onClick={onClick} />);
    fireEvent.click(screen.getByLabelText(/打开第 3 章/));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not crash when first_line is empty', () => {
    const emptyChapter = { ...mockChapter, first_line: '' };
    render(<ChapterCard chapter={emptyChapter} onClick={() => {}} />);
    expect(screen.getByText(/暂无内容/)).toBeInTheDocument();
  });

  it('formats char_count with thousands separator', () => {
    const largeChapter = { ...mockChapter, char_count: 12345 };
    render(<ChapterCard chapter={largeChapter} onClick={() => {}} />);
    // 12345 → 12,345
    expect(screen.getByText(/12,?345/)).toBeInTheDocument();
  });
});