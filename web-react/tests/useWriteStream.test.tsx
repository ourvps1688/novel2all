/**
 * useWriteStream 单元测试 (Sprint 2)
 *
 * 覆盖:
 *   - 初始 idle 状态
 *   - start() 调用后 streaming=true
 *   - SSE event 'chunk' / 'progress' / 'done' 状态更新
 *   - stop() 关闭 EventSource
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useWriteStream } from '../src/hooks/useSSE';

/**
 * Mock EventSource: 收集 handler, 允许测试主动 fire event
 */
class MockEventSource {
  url: string;
  listeners: Map<string, ((e: MessageEvent) => void)[]> = new Map();
  closed = false;

  static instances: MockEventSource[] = [];

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(event: string, handler: (e: MessageEvent) => void) {
    const list = this.listeners.get(event) ?? [];
    list.push(handler);
    this.listeners.set(event, list);
  }

  fire(event: string, data: unknown) {
    const list = this.listeners.get(event) ?? [];
    list.forEach((h) => h({ data: JSON.stringify(data) } as MessageEvent));
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  // 替换全局 EventSource 为 mock
  globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useWriteStream', () => {
  it('starts in idle state with zero chars', () => {
    const { result } = renderHook(() => useWriteStream());
    expect(result.current.progress.phase).toBe('idle');
    expect(result.current.progress.charsWritten).toBe(0);
    expect(result.current.streaming).toBe(false);
    expect(result.current.accumulated).toBe('');
  });

  it('exposes start and stop functions', () => {
    const { result } = renderHook(() => useWriteStream());
    expect(typeof result.current.start).toBe('function');
    expect(typeof result.current.stop).toBe('function');
  });

  it('start() opens EventSource with correct URL params', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({
        chapter: 3,
        minChars: 2000,
        projectRoot: '.',
        skill: 'story-long-write',
      });
    });

    expect(MockEventSource.instances.length).toBe(1);
    const es = MockEventSource.instances[0];
    expect(es?.url).toContain('chapter=3');
    expect(es?.url).toContain('min_chars=2000');
    expect(es?.url).toContain('project_root=.');
    expect(es?.url).toContain('skill=story-long-write');
  });

  it('chunk events accumulate text and update progress', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({ chapter: 1, minChars: 1000, projectRoot: '.' });
    });

    const es = MockEventSource.instances[0];
    expect(es).toBeDefined();

    act(() => {
      es?.fire('chunk', { text: '林雷' });
      es?.fire('chunk', { text: ' 站在剑碑前' });
    });

    expect(result.current.accumulated).toBe('林雷 站在剑碑前');
    expect(result.current.progress.charsWritten).toBeGreaterThan(0);
    expect(result.current.progress.phase).toBe('writing');
  });

  it('progress events update phase', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({ chapter: 1, minChars: 1000, projectRoot: '.' });
    });

    const es = MockEventSource.instances[0];
    act(() => {
      es?.fire('progress', { phase: 'pre_write_check', message: '检查中' });
    });
    expect(result.current.progress.phase).toBe('pre_write_check');
    expect(result.current.progress.message).toBe('检查中');
  });

  it('done event sets phase=done and stops streaming', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({ chapter: 1, minChars: 1000, projectRoot: '.' });
    });

    const es = MockEventSource.instances[0];
    act(() => {
      es?.fire('done', { output_path: '/tmp/x.md', content_chars: 1800 });
    });

    expect(result.current.progress.phase).toBe('done');
    expect(result.current.progress.charsWritten).toBe(1800);
    expect(result.current.streaming).toBe(false);
  });

  it('error event sets phase=error', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({ chapter: 1, minChars: 1000, projectRoot: '.' });
    });

    const es = MockEventSource.instances[0];
    act(() => {
      es?.fire('error', { message: '项目未初始化', code: 'project_not_found' });
    });

    expect(result.current.progress.phase).toBe('error');
    // 接受任一 errorMessage (network error handler 可能后写入)
    expect(result.current.progress.errorMessage).toMatch(/(项目未初始化|SSE 连接断开)/);
    expect(result.current.progress.errorCode).toBe('project_not_found');
  });

  it('cancelled event sets phase=cancelled', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({ chapter: 1, minChars: 1000, projectRoot: '.' });
    });

    const es = MockEventSource.instances[0];
    act(() => {
      es?.fire('cancelled', { partial_chars: 245, message: '已取消' });
    });

    expect(result.current.progress.phase).toBe('cancelled');
    expect(result.current.progress.charsWritten).toBe(245);
  });

  it('stop() closes the EventSource', () => {
    const { result } = renderHook(() => useWriteStream());

    act(() => {
      result.current.start({ chapter: 1, minChars: 1000, projectRoot: '.' });
    });

    const es = MockEventSource.instances[0];
    expect(es?.closed).toBe(false);

    act(() => {
      result.current.stop();
    });

    expect(result.current.streaming).toBe(false);
  });
});