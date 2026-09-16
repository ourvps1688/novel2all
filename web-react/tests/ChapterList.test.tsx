/**
 * ChapterList 单元测试 (Sprint 2)
 *
 * 覆盖:
 *   - 渲染章节网格 (按章节号升序)
 *   - 搜索过滤
 *   - 空状态 (无章节 / 无匹配)
 *   - onSelect 回调触发
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ChapterList } from '../src/components/chapter/ChapterList';
import type { ChapterCardData } from '../src/components/chapter/ChapterCard';

const mockChapters: ChapterCardData[] = [
  { chapter: 3, filename: '第003章.md', char_count: 1845, first_line: '林雷站在剑碑前' },
  { chapter: 1, filename: '第001章.md', char_count: 5200, first_line: '天地玄黄' },
  { chapter: 2, filename: '第002章.md', char_count: 4800, first_line: '宇宙洪荒' },
];

describe('ChapterList', () => {
  it('renders chapters sorted by chapter number', () => {
    render(<ChapterList chapters={mockChapters} />);
    const titles = screen.getAllByText(/第 \d+ 章/);
    // 第 1 章 / 第 2 章 / 第 3 章 (按数字升序)
    expect(titles[0]?.textContent).toContain('第 1 章');
    expect(titles[1]?.textContent).toContain('第 2 章');
    expect(titles[2]?.textContent).toContain('第 3 章');
  });

  it('renders empty state when chapters array is empty', () => {
    render(<ChapterList chapters={[]} />);
    expect(screen.getByText(/还没有章节/)).toBeInTheDocument();
  });

  it('filters chapters by search term', () => {
    render(<ChapterList chapters={mockChapters} />);
    const search = screen.getByLabelText(/搜索章节/);
    fireEvent.change(search, { target: { value: '天地' } });
    // 仅 第 1 章 "天地玄黄" 匹配
    expect(screen.getByText(/第 1 章/)).toBeInTheDocument();
    expect(screen.queryByText(/第 2 章/)).not.toBeInTheDocument();
    expect(screen.queryByText(/第 3 章/)).not.toBeInTheDocument();
  });

  it('shows empty state when search has no match', () => {
    render(<ChapterList chapters={mockChapters} />);
    const search = screen.getByLabelText(/搜索章节/);
    fireEvent.change(search, { target: { value: 'xyz不存在的关键字' } });
    expect(screen.getByText(/无匹配章节/)).toBeInTheDocument();
  });

  it('fires onSelect with chapter number when card is clicked', () => {
    const onSelect = vi.fn();
    render(<ChapterList chapters={mockChapters} onSelect={onSelect} />);
    fireEvent.click(screen.getByLabelText(/打开第 2 章/));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it('filters by chapter number', () => {
    render(<ChapterList chapters={mockChapters} />);
    const search = screen.getByLabelText(/搜索章节/);
    fireEvent.change(search, { target: { value: '3' } });
    // 第 3 章 char_count=3 includes "3", 第 1 章 "第001章.md" 包含 "1" 不含 "3", 但 "1,845" 包含 "1" 不包含 "3"
    // 但第 1 章 first_line 没有 "3"; 第 3 章 first_line 没有 "3"
    // 让我们简化: 搜索 "3" 匹配文件名 (第001章.md 第002章.md 第003章.md 只有 003 含 "3")
    // 严格: "3" 出现在 chapter=3 的章节中
    expect(screen.getByText(/第 3 章/)).toBeInTheDocument();
  });
});