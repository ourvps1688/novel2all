/**
 * Project 类型定义 (V1.5.x)
 *
 * 设计：
 *   - ProjectStatus 已在 api/types.ts 定义 (响应后端 GET /api/status)
 *   - 本文件定义**前端发起**的初始化请求 / 跨页共享的项目元数据
 */

import { z } from 'zod';

// ============ 初始化请求 ============

/**
 * POST /api/skills/story-setup/execute 接受的参数 (作为 inputSchema 实例)
 *
 * 与 data/skillCategories.ts 中 story-setup 的 inputSchema 对齐
 * 单独提取便于 setupPage (Sprint 4) / OnboardingWizard 复用
 */
export const ProjectInitRequestSchema = z.object({
  project_name: z.string().min(1).max(50),
  pen_name: z.string().max(30).optional(),
  genre: z.enum(['玄幻', '都市', '科幻', '历史', '言情', '悬疑', '武侠', '军事', '其他']),
  platform: z.enum(['起点', '番茄', '七猫', '盐言', '不限']).optional(),
  style_anchor: z.string().max(200).optional(),
});
export type ProjectInitRequest = z.infer<typeof ProjectInitRequestSchema>;

// ============ 派生元数据 (跨页共享) ============

/** 项目当前阶段 (用于 Dashboard 展示) */
export type ProjectLifecycleStage =
  | 'uninitialized' // 未初始化
  | 'setup' // 初始化中
  | 'writing' // 创作中
  | 'review' // 审查中
  | 'idle' // 空闲
  | 'archived'; // 已归档

/** 项目根路径 (V1.5.x 单项目, 默认 ".") */
export const DEFAULT_PROJECT_ROOT = '.';

// ============ Re-export ============

// 复用 api/types.ts 的 ProjectStatus (避免重复定义导致 schema 漂移)
export { ProjectStatusSchema } from '../api/types';
export type { ProjectStatus } from '../api/types';