/**
 * skillCategories 单元测试
 *
 * 验证 13 skill 完整覆盖 + 关键字段非空
 */

import { describe, it, expect } from 'vitest';

import {
  SKILL_CATEGORIES,
  CATEGORY_MAP,
  VISIBLE_SKILLS,
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

  it('hides internal skills from VISIBLE_SKILLS', () => {
    const visible = VISIBLE_SKILLS.map((s) => s.skill);
    expect(visible).not.toContain('browser-cdp');
    expect(visible.length).toBe(12);
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
});