/**
 * useSkillStream 单元测试
 *
 * 覆盖：
 *   - EventSource 启动
 *   - chunk 事件解析
 *   - 错误事件 → reconnect
 *   - cancel 关闭连接
 *
 * Mock EventSource (浏览器原生 API, jsdom 不支持)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useSkillStream } from '../src/hooks/useSkillStream';

// ============ EventSource Mock ============

type Handler = (e: Event) => void;

interface MockEventSource {
  url: string;
  withCredentials: boolean;
  listeners: Map<string, Set<Handler>>;
  closed: boolean;
  close: () => void;
  addEventListener: (event: string, handler: Handler) => void;
  removeEventListener: (event: string, handler: Handler) => void;
  fireEvent: (event: string, e?: Event) => void;
}

function createMockES(): MockEventSource {
  const listeners = new Map<string, Set<Handler>>();
  const es: MockEventSource = {
    url: '',
    withCredentials: false,
    listeners,
    closed: false,
    close: vi.fn(() => {
      es.closed = true;
    }),
    addEventListener: (event, handler) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)!.add(handler);
    },
    removeEventListener: (event, handler) => {
      listeners.get(event)?.delete(handler);
    },
    fireEvent: (event, e) => {
      const evt = e ?? new MessageEvent(event, { data: '' });
      listeners.get(event)?.forEach((h) => h(evt));
    },
  };
  return es;
}

let mockES: MockEventSource | null = null;

beforeEach(() => {
  mockES = createMockES();
  // 覆盖全局 EventSource (测试需要)
  global.EventSource = vi.fn((url: string, init?: { withCredentials?: boolean }) => {
    if (mockES) {
      mockES.url = url;
      mockES.withCredentials = init?.withCredentials ?? false;
    }
    return mockES as unknown as EventSource;
  }) as unknown as typeof EventSource;
});

describe('useSkillStream', () => {
  it('opens EventSource on stream() with correct URL', () => {
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk: vi.fn(),
      });
    });
    expect(mockES?.url).toBe('/api/skills/story-setup/status?task_id=t-1');
    expect(mockES?.withCredentials).toBe(true);
  });

  it('parses chunk events and invokes onChunk', () => {
    const onChunk = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName: 'story-setup', onChunk });
    });
    act(() => {
      mockES?.fireEvent(
        'chunk',
        new MessageEvent('chunk', { data: JSON.stringify({ text: 'hello world' }) }),
      );
    });
    expect(onChunk).toHaveBeenCalledWith('hello world');
  });

  it('invokes onError when chunk payload is invalid JSON', () => {
    const onError = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk: vi.fn(),
        onError,
      });
    });
    act(() => {
      mockES?.fireEvent('chunk', new MessageEvent('chunk', { data: 'not-json' }));
    });
    expect(onError).toHaveBeenCalled();
  });

  it('invokes onDone on done event', () => {
    const onDone = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk: vi.fn(),
        onDone,
      });
    });
    act(() => {
      mockES?.fireEvent(
        'done',
        new MessageEvent('done', { data: JSON.stringify({ elapsed_ms: 1234 }) }),
      );
    });
    expect(onDone).toHaveBeenCalledWith(
      expect.objectContaining({ durationMs: 1234, taskId: 't-1' }),
    );
  });

  it('triggers reconnect on network error', () => {
    const onReconnect = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk: vi.fn(),
        onReconnect,
      });
    });
    // 用 fake timers 加速重连 (1s 延迟)
    vi.useFakeTimers();
    act(() => {
      // 网络断开 (无 data 字段的 ErrorEvent)
      mockES?.fireEvent('error', new Event('error'));
    });
    // 重连应在 ~1s 后触发
    act(() => {
      vi.advanceTimersByTime(1100);
    });
    expect(onReconnect).toHaveBeenCalledWith(1);
    vi.useRealTimers();
  });

  it('cancel() closes the EventSource', async () => {
    const closeSpy = vi.spyOn(mockES!, 'close');
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName: 'story-setup', onChunk: vi.fn() });
    });
    await act(async () => {
      await result.current.cancel('t-1');
    });
    expect(closeSpy).toHaveBeenCalled();
  });
});