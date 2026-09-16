/**
 * skills.ts Zod Schema 单元测试
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #4）：SkillExecuteResponseSchema.status
 * 必须包含后端实际可能返回的所有状态，特别是：
 *   - "started"（POST /execute 立即返回，参见 app.py:1029）
 *   - "queued" / "running" / "done" / "failed" / "cancelled"
 *   - "timeout"（防御性）
 *
 * 之前缺失 "started" 会导致前端 zod parse 失败 + SSE 链路整个断掉。
 */

import { describe, it, expect } from 'vitest';

import {
  SkillExecuteResponseSchema,
  SkillStatusResponseSchema,
  SkillStatusEnum,
} from '../src/types/skills';

describe('SkillStatusEnum', () => {
  it('包含后端 execute 立即返回的 "started"', () => {
    // 必须包含 started，否则 V1.5.1 已知问题 #4 复发
    expect(SkillStatusEnum.options).toContain('started');
  });

  it('包含全部 7 个后端可能状态', () => {
    const expected = [
      'started',
      'queued',
      'running',
      'done',
      'failed',
      'cancelled',
      'timeout',
    ];
    for (const s of expected) {
      expect(SkillStatusEnum.options).toContain(s);
    }
    expect(SkillStatusEnum.options.length).toBe(expected.length);
  });

  it('能直接 parse 字符串', () => {
    expect(SkillStatusEnum.parse('started')).toBe('started');
    expect(SkillStatusEnum.parse('running')).toBe('running');
    expect(SkillStatusEnum.parse('done')).toBe('done');
    expect(SkillStatusEnum.parse('failed')).toBe('failed');
    expect(SkillStatusEnum.parse('cancelled')).toBe('cancelled');
  });

  it('拒绝未知状态', () => {
    expect(() => SkillStatusEnum.parse('unknown-state')).toThrow();
    expect(() => SkillStatusEnum.parse('')).toThrow();
    expect(() => SkillStatusEnum.parse('STARTED')).toThrow(); // 大小写敏感
  });
});

describe('SkillExecuteResponseSchema', () => {
  it('parse 后端 execute 真实返回（带 started + skill + project_root 字段）', () => {
    // 模拟后端 app.py:1027-1033 的真实响应
    const backendResp = {
      task_id: 'a1b2c3d4',
      status: 'started',
      started_at: 1737012345.678,
      skill: 'story-setup',
      project_root: '.',
    };
    const parsed = SkillExecuteResponseSchema.parse(backendResp);
    expect(parsed.task_id).toBe('a1b2c3d4');
    expect(parsed.status).toBe('started');
    expect(parsed.started_at).toBe(1737012345.678);
  });

  it('parse 不带 started_at 的最小响应', () => {
    const resp = { task_id: 't-1', status: 'queued' };
    const parsed = SkillExecuteResponseSchema.parse(resp);
    expect(parsed.task_id).toBe('t-1');
    expect(parsed.status).toBe('queued');
    expect(parsed.started_at).toBeUndefined();
  });

  it('parse 所有 7 个合法状态', () => {
    const states: Array<'started' | 'queued' | 'running' | 'done' | 'failed' | 'cancelled' | 'timeout'> = [
      'started',
      'queued',
      'running',
      'done',
      'failed',
      'cancelled',
      'timeout',
    ];
    for (const s of states) {
      const parsed = SkillExecuteResponseSchema.parse({ task_id: 't', status: s });
      expect(parsed.status).toBe(s);
    }
  });

  it('拒绝非法 status', () => {
    expect(() =>
      SkillExecuteResponseSchema.parse({ task_id: 't', status: 'invalid' }),
    ).toThrow();
  });

  it('拒绝缺失 task_id', () => {
    expect(() =>
      SkillExecuteResponseSchema.parse({ status: 'started' }),
    ).toThrow();
  });

  it('允许额外字段（多余字段被忽略，向后兼容）', () => {
    // 后端可能加新字段（如 skill_name / project_root / message），
    // zod 默认 passthrough 行为：多余字段会被剥离，不会抛错
    const resp = {
      task_id: 't',
      status: 'started',
      skill: 'story-setup',
      project_root: '.',
      extra_field: 'future',
    };
    const parsed = SkillExecuteResponseSchema.parse(resp);
    expect(parsed.task_id).toBe('t');
    expect(parsed.status).toBe('started');
    expect((parsed as Record<string, unknown>).extra_field).toBeUndefined();
  });
});

describe('SkillStatusResponseSchema', () => {
  it('parse started 事件（含 task_id + status）', () => {
    const evt = {
      task_id: 't-1',
      status: 'started',
      skill: 'story-setup',
      chapter: 1,
    };
    const parsed = SkillStatusResponseSchema.parse(evt);
    expect(parsed.task_id).toBe('t-1');
    expect(parsed.status).toBe('started');
  });

  it('parse running 事件（含 progress + phase）', () => {
    const evt = {
      task_id: 't-1',
      status: 'running',
      phase: 'writing',
      progress: 60,
      chars_written: 1234,
      chars_per_second: 50,
      eta_seconds: 12,
    };
    const parsed = SkillStatusResponseSchema.parse(evt);
    expect(parsed.status).toBe('running');
    expect(parsed.phase).toBe('writing');
    expect(parsed.chars_written).toBe(1234);
    expect(parsed.chars_per_second).toBe(50);
    expect(parsed.eta_seconds).toBe(12);
  });

  it('parse done 事件（含 output_path + content_chars）', () => {
    const evt = {
      task_id: 't-1',
      status: 'done',
      output_path: '/tmp/ch1.md',
      content_chars: 2000,
      post_issue_count: 0,
      pre_issue_count: 0,
    };
    const parsed = SkillStatusResponseSchema.parse(evt);
    expect(parsed.status).toBe('done');
  });

  it('parse cancelled 事件', () => {
    const evt = {
      task_id: 't-1',
      status: 'cancelled',
      chapter: 3,
      partial_chars: 850,
      output_path: '/tmp/ch3.md',
      message: '已在 850 字处取消',
    };
    const parsed = SkillStatusResponseSchema.parse(evt);
    expect(parsed.status).toBe('cancelled');
    expect(parsed.message).toContain('取消');
  });

  it('parse failed 事件（含 error 字段）', () => {
    const evt = {
      task_id: 't-1',
      status: 'failed',
      error: 'Pipeline 失败: OutlineNotFoundError',
      message: 'Outlined not found',
    };
    const parsed = SkillStatusResponseSchema.parse(evt);
    expect(parsed.status).toBe('failed');
    expect(parsed.error).toContain('OutlineNotFoundError');
  });

  it('parse 所有 7 个合法状态', () => {
    const states: Array<'started' | 'queued' | 'running' | 'done' | 'failed' | 'cancelled' | 'timeout'> = [
      'started',
      'queued',
      'running',
      'done',
      'failed',
      'cancelled',
      'timeout',
    ];
    for (const s of states) {
      const parsed = SkillStatusResponseSchema.parse({ task_id: 't', status: s });
      expect(parsed.status).toBe(s);
    }
  });

  it('拒绝非法 status', () => {
    expect(() =>
      SkillStatusResponseSchema.parse({ task_id: 't', status: 'banana' }),
    ).toThrow();
  });

  it('允许 metadata 任意键值对', () => {
    const evt = {
      task_id: 't',
      status: 'running',
      metadata: {
        anything: 1,
        nested: { deep: 'value' },
        arr: [1, 2, 3],
      },
    };
    const parsed = SkillStatusResponseSchema.parse(evt);
    expect(parsed.metadata).toBeDefined();
  });
});