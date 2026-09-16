/**
 * skillExecutionStore 单元测试
 *
 * 覆盖 startRun / finishRun / clearHistory / clearAll
 * 使用 fresh store (zustand 测试技巧: 替换 _internal 状态)
 */

import { describe, it, expect, beforeEach } from 'vitest';

import { useSkillExecutionStore } from '../src/store/skillExecutionStore';

function resetStore(): void {
  useSkillExecutionStore.setState({ history: {}, current: {} });
}

describe('skillExecutionStore', () => {
  beforeEach(() => {
    // 清 localStorage + store
    if (typeof window !== 'undefined') {
      window.localStorage.clear();
    }
    resetStore();
  });

  it('startRun creates a new history entry with preparing status', () => {
    const taskId = useSkillExecutionStore.getState().startRun('story-setup', '测试输入');
    expect(taskId).toBeTruthy();
    const state = useSkillExecutionStore.getState();
    expect(state.history['story-setup']).toHaveLength(1);
    expect(state.history['story-setup']?.[0]?.taskId).toBe(taskId);
    expect(state.history['story-setup']?.[0]?.status).toBe('preparing');
    expect(state.history['story-setup']?.[0]?.inputPreview).toBe('测试输入');
    expect(state.current['story-setup']?.taskId).toBe(taskId);
  });

  it('startRun truncates long input previews', () => {
    const longInput = 'x'.repeat(200);
    useSkillExecutionStore.getState().startRun('story-long-write', longInput);
    const entry = useSkillExecutionStore.getState().history['story-long-write']?.[0];
    expect(entry?.inputPreview).toMatch(/…$/);
    expect(entry?.inputPreview.length).toBeLessThanOrEqual(81); // 80 chars + ellipsis
  });

  it('finishRun updates status and timestamp', async () => {
    const taskId = useSkillExecutionStore.getState().startRun('story-setup', 'x');
    // 等待 1ms 让时间戳不同
    await new Promise((r) => setTimeout(r, 5));
    useSkillExecutionStore.getState().finishRun('story-setup', taskId, 'success', 'result');
    const entry = useSkillExecutionStore.getState().history['story-setup']?.[0];
    expect(entry?.status).toBe('success');
    expect(entry?.finishedAt).not.toBeNull();
    expect(entry?.outputPreview).toBe('result');
    expect(entry?.durationMs).toBeGreaterThan(0);
  });

  it('finishRun with unknown taskId is a no-op (does not crash)', () => {
    useSkillExecutionStore.getState().startRun('story-setup', 'x');
    expect(() =>
      useSkillExecutionStore.getState().finishRun('story-setup', 'nonexistent', 'error', ''),
    ).not.toThrow();
  });

  it('clearHistory removes a single skill bucket', () => {
    useSkillExecutionStore.getState().startRun('story-setup', 'a');
    useSkillExecutionStore.getState().startRun('story-long-write', 'b');
    useSkillExecutionStore.getState().clearHistory('story-setup');
    const state = useSkillExecutionStore.getState();
    expect(state.history['story-setup']).toBeUndefined();
    expect(state.history['story-long-write']).toHaveLength(1);
  });

  it('clearAll wipes everything', () => {
    useSkillExecutionStore.getState().startRun('story-setup', 'a');
    useSkillExecutionStore.getState().startRun('story-long-write', 'b');
    useSkillExecutionStore.getState().clearAll();
    expect(Object.keys(useSkillExecutionStore.getState().history)).toHaveLength(0);
  });

  it('preserves history order (most recent first)', () => {
    const t1 = useSkillExecutionStore.getState().startRun('story-setup', 'first');
    const t2 = useSkillExecutionStore.getState().startRun('story-setup', 'second');
    const list = useSkillExecutionStore.getState().history['story-setup'];
    expect(list?.[0]?.taskId).toBe(t2);
    expect(list?.[1]?.taskId).toBe(t1);
  });
});