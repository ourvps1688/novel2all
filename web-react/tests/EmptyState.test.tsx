/**
 * EmptyState + LoadingSkeleton 单元测试
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import InboxIcon from '@mui/icons-material/Inbox';

import { EmptyState } from '../src/components/common/EmptyState';
import { LoadingSkeleton } from '../src/components/common/LoadingSkeleton';

describe('EmptyState', () => {
  it('renders title and subtitle', () => {
    render(<EmptyState title="暂无数据" subtitle="先创建一个项目吧" />);
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
    expect(screen.getByText('先创建一个项目吧')).toBeInTheDocument();
  });

  it('renders action button and fires onClick', () => {
    const onClick = vi.fn();
    render(<EmptyState title="空" action={{ label: '去试试', onClick }} />);
    fireEvent.click(screen.getByText('去试试'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('renders custom icon', () => {
    render(<EmptyState title="空" icon={<InboxIcon data-testid="custom-icon" />} />);
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('renders without boxed container when boxed=false', () => {
    const { container } = render(<EmptyState title="空" boxed={false} />);
    expect(container.querySelector('.MuiCard-root')).toBeNull();
  });
});

describe('LoadingSkeleton', () => {
  it('renders card variant by default', () => {
    const { container } = render(<LoadingSkeleton />);
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });

  it('renders skillGrid with count items', () => {
    const { container } = render(<LoadingSkeleton variant="skillGrid" count={6} />);
    // 6 卡片 × (2 Skeleton per card avatar + 2 text) = 24
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThanOrEqual(12);
  });

  it('renders skillDetail variant', () => {
    const { container } = render(<LoadingSkeleton variant="skillDetail" />);
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThanOrEqual(2);
  });
});