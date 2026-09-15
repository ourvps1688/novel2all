/**
 * Write flow / SSE hook 测试
 */

import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useWriteStream } from '../src/hooks/useSSE';
import { computePhaseProgress } from '../src/types/models';

describe('useWriteStream', () => {
  it('starts with idle phase and zero chars', () => {
    const { result } = renderHook(() => useWriteStream());
    expect(result.current.progress.phase).toBe('idle');
    expect(result.current.progress.charsWritten).toBe(0);
    expect(result.current.streaming).toBe(false);
  });

  it('exposes start and stop functions', () => {
    const { result } = renderHook(() => useWriteStream());
    expect(typeof result.current.start).toBe('function');
    expect(typeof result.current.stop).toBe('function');
  });
});

describe('computePhaseProgress', () => {
  it('returns 0 for idle phase', () => {
    expect(computePhaseProgress('idle')).toBe(0);
  });

  it('returns 1 for done phase', () => {
    expect(computePhaseProgress('done')).toBe(1);
  });

  it('returns 0 for error / cancelled', () => {
    expect(computePhaseProgress('error')).toBe(0);
    expect(computePhaseProgress('cancelled')).toBe(0);
  });

  it('returns intermediate value for writing', () => {
    const p = computePhaseProgress('writing');
    expect(p).toBeGreaterThan(0);
    expect(p).toBeLessThan(1);
  });
});
