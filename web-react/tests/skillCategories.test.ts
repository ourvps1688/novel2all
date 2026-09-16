/**
 * skillCategories 单元测试
 *
 * 验证 13 skill 完整覆盖 + 关键字段非空
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #5）：
 *   - 新增 INTERNAL_SKILLS 测试
 *   - 新增 isInternal flag 测试（browser-cdp 必须 isInternal=true）
 *   - VISIBLE_SKILLS 现代表「用户可直接调用的 skill」(12 个)；UI 现在展示全部 13 个
 */

import { describe, it, expect } from 'vitest';

import {
  SKILL_CATEGORIES,
  CATEGORY_MAP,
  VISIBLE_SKILLS,
  USER_INVOCABLE_SKILLS,
  INTERNAL_SKILLS,
  QUICK_START_SKILLS,
} from '../src/data/skillCategories';
import type { SkillCategory } from '../src/types/skills';

describe('skillCategories', () => {
  it('exposes exactly 13 skills', () => {
    expect(SKILL_CATEGORIES).toHaveLength(13);
  });

  it('covers all expected skills by name', () => {
    const names = SKILL_CATEGORIES.map((s) => s.skill).sort();
    expect(names).toEqual(
      [
        'browser-cdp',
        'story',
        'story-cover',
        'story-deslop',
        'story-import',
        'story-long-analyze',
        'story-long-scan',
        'story-long-write',
        'story-review',
        'story-setup',
        'story-short-analyze',
        'story-short-scan',
        'story-short-write',
      ].sort(),
    );
  });

  it('builds CATEGORY_MAP keyed by skill name', () => {
    expect(Object.keys(CATEGORY_MAP)).toHaveLength(13);
    expect(CATEGORY_MAP['story-long-write']?.label).toBe('长篇写作');
    expect(CATEGORY_MAP['story-setup']?.category).toBe('创作类');
  });

  it('USER_INVOCABLE_SKILLS excludes browser-cdp (12 total)', () => {
    const invocable = USER_INVOCABLE_SKILLS.map((s) => s.skill);
    expect(invocable).not.toContain('browser-cdp');
    expect(invocable.length).toBe(12);
  });

  it('VISIBLE_SKILLS is an alias for USER_INVOCABLE_SKILLS (向后兼容)', () => {
    expect(VISIBLE_SKILLS.map((s) => s.skill)).toEqual(
      USER_INVOCABLE_SKILLS.map((s) => s.skill),
    );
    expect(VISIBLE_SKILLS.length).toBe(12);
  });

  it('INTERNAL_SKILLS 仅含 browser-cdp', () => {
    // V1.5.1 Sprint 1.1 修复（已知问题 #5）
    const internal = INTERNAL_SKILLS.map((s) => s.skill);
    expect(internal).toEqual(['browser-cdp']);
    expect(INTERNAL_SKILLS.length).toBe(1);
  });

  it('browser-cdp 必须 isInternal=true (其他 skill 默认 false/undefined)', () => {
    // V1.5.1 Sprint 1.1 修复（已知问题 #5）：isInternal flag 必填语义
    expect(CATEGORY_MAP['browser-cdp']?.isInternal).toBe(true);
    const others = SKILL_CATEGORIES.filter((s) => s.skill !== 'browser-cdp');
    for (const s of others) {
      expect(s.isInternal === true).toBe(false);
    }
  });

  it('groups skills into all required categories', () => {
    const categories = new Set(SKILL_CATEGORIES.map((s) => s.category));
    const required: SkillCategory[] = ['创作类', '分析类', '工具类', '入口类', '内部'];
    required.forEach((c) => expect(categories.has(c)).toBe(true));
  });

  it('QUICK_START_SKILLS points to existing skills', () => {
    for (const name of QUICK_START_SKILLS) {
      expect(CATEGORY_MAP[name]).toBeDefined();
    }
  });

  it('every skill with inputSchema has at least one property', () => {
    SKILL_CATEGORIES.forEach((s) => {
      if (s.inputSchema) {
        expect(s.inputSchema.type).toBe('object');
        expect(s.inputSchema.properties).toBeDefined();
        const props = s.inputSchema.properties ?? {};
        expect(Object.keys(props).length).toBeGreaterThan(0);
      }
    });
  });

  it('SKILL_CATEGORIES 与 CATEGORY_MAP 一致 (没有重复 skill)', () => {
    const names = SKILL_CATEGORIES.map((s) => s.skill);
    const unique = new Set(names);
    expect(unique.size).toBe(names.length);
    // CATEGORY_MAP key 集合等于 SKILL_CATEGORIES skill 集合
    expect(new Set(Object.keys(CATEGORY_MAP))).toEqual(unique);
  });
});