/**
 * Toolbar 单元测试 (Sprint 2)
 *
 * 覆盖:
 *   - 按钮显示 (保存 / 撤销 / 重做 / AI 续写 / AI 重写 / AI 插入)
 *   - 根据 isDirty / aiLoading / isStreaming 切换 disabled 状态
 *   - 点击触发 onAction 回调 (含 payload 类型)
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { Toolbar, type ToolbarAction } from '../src/components/write/Toolbar';

describe('Toolbar', () => {
  it('renders all action buttons', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={3}
        selection={null}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-save')).toBeInTheDocument();
    expect(screen.getByTestId('toolbar-undo')).toBeInTheDocument();
    expect(screen.getByTestId('toolbar-redo')).toBeInTheDocument();
    expect(screen.getByTestId('toolbar-continue')).toBeInTheDocument();
    expect(screen.getByTestId('toolbar-rewrite')).toBeInTheDocument();
    expect(screen.getByTestId('toolbar-insert')).toBeInTheDocument();
  });

  it('disables save button when not dirty', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={null}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-save')).toBeDisabled();
  });

  it('enables save button when isDirty=true', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={null}
        canUndo={true}
        canRedo={true}
        isDirty={true}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-save')).not.toBeDisabled();
  });

  it('disables AI rewrite/insert when selection is null', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={null}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-rewrite')).toBeDisabled();
    expect(screen.getByTestId('toolbar-insert')).toBeDisabled();
  });

  it('enables AI rewrite when selection has text', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={{ from: 10, to: 50, text: '选中段落' }}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-rewrite')).not.toBeDisabled();
    expect(screen.getByTestId('toolbar-insert')).not.toBeDisabled();
  });

  it('disables AI continue when streaming is in progress', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={null}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading="continue"
        isStreaming={true}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-continue')).toBeDisabled();
  });

  it('fires onAction with correct type for undo/redo', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={null}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    fireEvent.click(screen.getByTestId('toolbar-undo'));
    fireEvent.click(screen.getByTestId('toolbar-redo'));
    expect(onAction).toHaveBeenCalledWith({ type: 'undo' } satisfies ToolbarAction);
    expect(onAction).toHaveBeenCalledWith({ type: 'redo' } satisfies ToolbarAction);
  });

  it('fires onAction with selection for rewrite', () => {
    const onAction = vi.fn();
    const sel = { from: 5, to: 15, text: 'hello world' };
    render(
      <Toolbar
        chapter={1}
        selection={sel}
        canUndo={true}
        canRedo={true}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    fireEvent.click(screen.getByTestId('toolbar-rewrite'));
    expect(onAction).toHaveBeenCalledWith({ type: 'rewrite', selection: sel });
  });

  it('disables undo/redo when canUndo=false', () => {
    const onAction = vi.fn();
    render(
      <Toolbar
        chapter={1}
        selection={null}
        canUndo={false}
        canRedo={false}
        isDirty={false}
        isAutoSaving={false}
        aiLoading={null}
        isStreaming={false}
        onAction={onAction}
      />,
    );
    expect(screen.getByTestId('toolbar-undo')).toBeDisabled();
    expect(screen.getByTestId('toolbar-redo')).toBeDisabled();
  });
});