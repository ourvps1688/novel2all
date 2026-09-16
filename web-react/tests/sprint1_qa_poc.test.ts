/**
 * Sprint 1 QA 独立 PoC 测试 (软件-qa-engineer-6)
 *
 * 验证范围：
 *   - PoC A: 13 个 skill 都能触发 execute → SSE 流式输出
 *   - PoC B: 网络异常 (断线 3 次 → polling 降级)
 *   - PoC C: 边界 / 特殊字符 / 超长输入
 *
 * 注意：完全不依赖工程师写的 SkillRunner.test.tsx, 自己 mock EventSource 验证
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useSkillStream } from '../src/hooks/useSkillStream';
import { SKILL_CATEGORIES, VISIBLE_SKILLS } from '../src/data/skillCategories';

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
  global.EventSource = vi.fn((url: string, init?: { withCredentials?: boolean }) => {
    if (mockES) {
      mockES.url = url;
      mockES.withCredentials = init?.withCredentials ?? false;
    }
    return mockES as unknown as EventSource;
  }) as unknown as typeof EventSource;
  vi.useRealTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ============ PoC A: 13 Skill 完整覆盖 ============

describe('PoC A: 13 skill 完整覆盖', () => {
  it('SKILL_CATEGORIES 包含全部 13 个后端 skill', () => {
    expect(SKILL_CATEGORIES).toHaveLength(13);
    const names = SKILL_CATEGORIES.map((s) => s.skill);
    expect(names).toEqual(
      expect.arrayContaining([
        'story',
        'story-setup',
        'story-long-write',
        'story-long-analyze',
        'story-long-scan',
        'story-short-write',
        'story-short-analyze',
        'story-short-scan',
        'story-cover',
        'story-deslop',
        'story-review',
        'story-import',
        'browser-cdp',
      ]),
    );
  });

  it('VISIBLE_SKILLS 排除 browser-cdp', () => {
    const names = VISIBLE_SKILLS.map((s) => s.skill);
    expect(names).not.toContain('browser-cdp');
    expect(names).toHaveLength(12);
  });

  it.each(
    SKILL_CATEGORIES.filter((s) => s.category !== '内部').map((s) => s.skill),
  )('skill "%s" 能正确打开 SSE 连接', (skillName) => {
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName, onChunk: vi.fn() });
    });
    expect(mockES?.url).toBe(`/api/skills/${encodeURIComponent(skillName)}/status?task_id=t-1`);
  });

  it.each(SKILL_CATEGORIES.map((s) => s.skill))(
    'skill "%s" 完整 8 阶段 SSE 事件流可正确解析',
    (skillName) => {
      const onChunk = vi.fn();
      const onProgress = vi.fn();
      const onDone = vi.fn();

      const { result } = renderHook(() => useSkillStream());
      act(() => {
        void result.current.stream({
          taskId: 't-1',
          skillName,
          onChunk,
          onProgress,
          onDone,
        });
      });

      // 模拟完整 SSE 流 (7 个 progress 阶段 + 3 chunks + 1 done)
      // 注意：'done' phase 不通过 progress 事件发送, 而通过 'done' 事件
      const events: Array<[string, unknown]> = [
        ['chunk', { text: '第一段...' }],
        ['progress', { phase: 'init', chars_written: 0 }],
        ['progress', { phase: 'pre_write_check', chars_written: 0 }],
        ['progress', { phase: 'writing', chars_written: 100, chars_per_second: 50 }],
        ['chunk', { text: '继续...' }],
        ['progress', { phase: 'save', chars_written: 500 }],
        ['progress', { phase: 'extract', chars_written: 500 }],
        ['progress', { phase: 'merge', chars_written: 500 }],
        ['progress', { phase: 'post_write_check', chars_written: 500 }],
        ['chunk', { text: '最终输出' }],
        [
          'done',
          { elapsed_ms: 12345, content_chars: 500, metadata: { skill: skillName } },
        ],
      ];

      act(() => {
        for (const [eventName, data] of events) {
          mockES?.fireEvent(
            eventName,
            new MessageEvent(eventName, { data: JSON.stringify(data) }),
          );
        }
      });

      expect(onChunk).toHaveBeenCalledTimes(3);
      expect(onProgress).toHaveBeenCalledTimes(7);
      expect(onDone).toHaveBeenCalledWith(
        expect.objectContaining({
          durationMs: 12345,
          taskId: 't-1',
          metadata: expect.objectContaining({
            content_chars: 500,
            metadata: expect.objectContaining({ skill: skillName }),
          }),
        }),
      );
    },
  );
});

// ============ PoC B: 网络异常 ============

describe('PoC B: 网络异常场景', () => {
  it('断线 3 次后降级 polling', async () => {
    const axios = await import('axios');
    const pollingGetSpy = vi.spyOn(axios.default, 'get').mockResolvedValue({
      data: { status: 'running', progress: { phase: 'writing', chars_written: 100 } },
    });

    const onReconnect = vi.fn();
    const onChunk = vi.fn();
    const onProgress = vi.fn();
    const { result } = renderHook(() => useSkillStream());

    vi.useFakeTimers();
    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk,
        onProgress,
        onReconnect,
      });
    });

    // 模拟 3 次断线
    for (let i = 0; i < 3; i++) {
      act(() => {
        mockES?.fireEvent('error', new Event('error'));
      });
      act(() => {
        vi.advanceTimersByTime(5000);
      });
    }

    expect(onReconnect).toHaveBeenCalledWith(3);
    // 第 4 次失败 → 应触发 polling
    expect(pollingGetSpy).toHaveBeenCalledWith(
      '/api/skills/story-setup/status',
      expect.objectContaining({ params: { task_id: 't-1' } }),
    );
  });

  it('服务端 error event (有 data) 立即终止, 不重连', () => {
    const onError = vi.fn();
    const onReconnect = vi.fn();
    const { result } = renderHook(() => useSkillStream());

    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk: vi.fn(),
        onError,
        onReconnect,
      });
    });

    act(() => {
      mockES?.fireEvent(
        'error',
        new MessageEvent('error', { data: JSON.stringify({ message: '服务器 500' }) }),
      );
    });

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    // 验证 message
    const errArg = (onError.mock.calls[0]?.[0] ?? null) as Error | null;
    expect((errArg as unknown as Error)?.message).toBe('服务器 500');
    // 不应触发重连 (immediate terminal error)
    expect(onReconnect).not.toHaveBeenCalled();
  });

  it('cancelled 事件正确触发 onError', () => {
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
      mockES?.fireEvent(
        'cancelled',
        new MessageEvent('cancelled', { data: JSON.stringify({ message: '用户取消' }) }),
      );
    });
    expect(onError).toHaveBeenCalled();
    const errArg = (onError.mock.calls[0]?.[0] ?? null) as Error | null;
    expect((errArg as unknown as Error)?.message).toContain('用户取消');
  });
});

// ============ PoC C: 边界 / 特殊字符 ============

describe('PoC C: 边界 / 权限', () => {
  it('skill name 含特殊字符 (连字符, 下划线) URL 安全', () => {
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName: 'story-long-write', onChunk: vi.fn() });
    });
    expect(mockES?.url).toContain('story-long-write');
  });

  it('URL 包含 task_id 完整保留', () => {
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 'abc-123-xyz', skillName: 'story-setup', onChunk: vi.fn() });
    });
    expect(mockES?.url).toBe('/api/skills/story-setup/status?task_id=abc-123-xyz');
  });

  it('异常 JSON 数据触发 onError (chunk 解析失败)', () => {
    const onError = vi.fn();
    const onChunk = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({
        taskId: 't-1',
        skillName: 'story-setup',
        onChunk,
        onError,
      });
    });

    act(() => {
      mockES?.fireEvent('chunk', new MessageEvent('chunk', { data: '{not-json' }));
    });
    expect(onError).toHaveBeenCalled();
    expect(onChunk).not.toHaveBeenCalled();
  });

  it('disabled/admin 等额外字段被正确忽略 (chunk 只取 text)', () => {
    const onChunk = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName: 'story-setup', onChunk });
    });

    act(() => {
      mockES?.fireEvent(
        'chunk',
        new MessageEvent('chunk', {
          data: JSON.stringify({ text: '正常', disabled: 0, role: 'admin', _: 'noise' }),
        }),
      );
    });
    expect(onChunk).toHaveBeenCalledWith('正常');
  });

  it('progress 事件缺失字段时降级处理', () => {
    const onProgress = vi.fn();
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName: 'story-setup', onProgress });
    });

    act(() => {
      // 极端稀疏 payload
      mockES?.fireEvent(
        'progress',
        new MessageEvent('progress', { data: JSON.stringify({}) }),
      );
    });
    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({ charsWritten: 0 }),
    );
  });

  it('cancel 后再次 stream 应能重新连接', async () => {
    const { result } = renderHook(() => useSkillStream());
    act(() => {
      void result.current.stream({ taskId: 't-1', skillName: 'story-setup', onChunk: vi.fn() });
    });
    const firstES = mockES;

    await act(async () => {
      await result.current.cancel('t-1');
    });
    expect(firstES?.closed).toBe(true);

    // 重新连接 - 让全局 EventSource 工厂返回新的 mock
    const newMockES = createMockES();
    let newESReturned = false;
    global.EventSource = vi.fn((url: string, init?: { withCredentials?: boolean }) => {
      newMockES.url = url;
      newMockES.withCredentials = init?.withCredentials ?? false;
      newESReturned = true;
      return newMockES as unknown as EventSource;
    }) as unknown as typeof EventSource;

    act(() => {
      void result.current.stream({ taskId: 't-2', skillName: 'story-setup', onChunk: vi.fn() });
    });
    expect(newESReturned).toBe(true);
    expect(newMockES.url).toContain('task_id=t-2');
  });
});
