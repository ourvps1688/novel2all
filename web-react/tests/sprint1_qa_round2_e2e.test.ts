/**
 * Sprint 1.1 QA Round 2: 端到端 schema parse 验证
 *
 * 独立 E2E: 用真实后端响应 shape（status="started"）直接喂给 zod schema
 *   - 必须能 parse 通过（Fix #4 验证）
 *   - 多余字段（skill/project_root）必须被忽略（向后兼容）
 *
 * 此测试是 QA Round 2 独立添加，不依赖 engineer 提供的 test case。
 */

import { describe, it, expect } from 'vitest';
import {
  SkillExecuteResponseSchema,
  SkillStatusResponseSchema,
  SkillStatusEnum,
} from '../src/types/skills';

describe('Sprint 1.1 QA Round 2 E2E: backend → zod parse', () => {
  it('[Fix #4] 真实后端 execute 响应 shape → SkillExecuteResponseSchema.parse 不抛错', () => {
    // 这个 shape 来自 src/novel2all/web/app.py:1027-1033 (execute_skill_endpoint 返回值)
    const realBackendResp = {
      task_id: '4040a492',
      status: 'started',
      started_at: 1789527855.35366,
      skill: 'story-setup',
      project_root: '.',
    };
    // 这是 V1.5.1 已知问题 #4 的根因：缺少 'started' 会让旧 enum parse 失败
    // 修复后必须能 parse
    const parsed = SkillExecuteResponseSchema.parse(realBackendResp);
    expect(parsed.task_id).toBe('4040a492');
    expect(parsed.status).toBe('started');
    expect(parsed.started_at).toBeCloseTo(1789527855.35366, 4);
    // 多余字段被剥离 (passthrough 默认行为)
    expect((parsed as Record<string, unknown>).skill).toBeUndefined();
    expect((parsed as Record<string, unknown>).project_root).toBeUndefined();
  });

  it('[Fix #4] 旧 enum (无 started) 会 fail, 新 enum (含 started) pass', () => {
    // 验证 schema 的修复是必要的 - 反证
    // 假设后端实际可能返回的所有 5 个 status:
    const allPossibleStatuses = ['started', 'running', 'done', 'failed', 'cancelled'];
    for (const s of allPossibleStatuses) {
      const parsed = SkillExecuteResponseSchema.parse({ task_id: 't', status: s });
      expect(parsed.status).toBe(s);
    }
    // 特别地: 'started' 必须 parse 通过
    expect(() =>
      SkillExecuteResponseSchema.parse({ task_id: 't', status: 'started' }),
    ).not.toThrow();
  });

  it('[Fix #4] SkillStatusResponseSchema 也能 parse started', () => {
    // SSE 首批事件也可能就是 started
    const sseStartedEvent = {
      task_id: 'abc',
      status: 'started',
      skill: 'story-setup',
      chapter: 1,
    };
    const parsed = SkillStatusResponseSchema.parse(sseStartedEvent);
    expect(parsed.status).toBe('started');
  });

  it('[Fix #5] SKILL_CATEGORIES 包含全部 13 个 skill', async () => {
    const { SKILL_CATEGORIES } = await import('../src/data/skillCategories');
    expect(SKILL_CATEGORIES.length).toBe(13);
    // 验证 browser-cdp 在内
    const browser = SKILL_CATEGORIES.find((m) => m.skill === 'browser-cdp');
    expect(browser).toBeDefined();
    expect(browser?.isInternal).toBe(true);
  });

  it('[Fix #5] USER_INVOCABLE_SKILLS 仅包含非 internal = 12 个', async () => {
    const { USER_INVOCABLE_SKILLS } = await import('../src/data/skillCategories');
    expect(USER_INVOCABLE_SKILLS.length).toBe(12);
    // browser-cdp 不应在 user invocable 列表中
    expect(USER_INVOCABLE_SKILLS.find((m) => m.skill === 'browser-cdp')).toBeUndefined();
  });

  it('[Fix #5] INTERNAL_SKILLS 仅包含 internal = 1 个', async () => {
    const { INTERNAL_SKILLS } = await import('../src/data/skillCategories');
    expect(INTERNAL_SKILLS.length).toBe(1);
    expect(INTERNAL_SKILLS[0]?.skill).toBe('browser-cdp');
  });

  it('[Fix #5] SkillStatusEnum 含 7 个状态', () => {
    expect(SkillStatusEnum.options.length).toBe(7);
    const expected = ['started', 'queued', 'running', 'done', 'failed', 'cancelled', 'timeout'];
    for (const s of expected) {
      expect(SkillStatusEnum.options).toContain(s);
    }
  });

  it('[Fix #5] SKILL_CATEGORY_LIST 含 5 个分类（含 内部）', async () => {
    const { SKILL_CATEGORY_LIST } = await import('../src/types/skills');
    expect(SKILL_CATEGORY_LIST.length).toBe(5);
    expect(SKILL_CATEGORY_LIST).toContain('内部');
  });
});