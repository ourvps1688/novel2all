/**
 * Chapter 系统 TypeScript 类型 (Sprint 2 / V1.5.2)
 *
 * 范围:
 *   - 章节 UI 状态 (selection / dirty / loading)
 *   - AI 操作类型 + 请求/响应
 *   - 8 阶段写作进度 (复用 api/types.ts 的 WritePhase)
 *
 * 数据契约:
 *   - Chapter / ChapterContent 等后端契约见 api/types.ts (snake_case)
 *   - 本文件类型全部用 camelCase, 适配 UI 层
 */

import type { WritePhase } from '../api/types';

// ============ Text Selection ============

/**
 * Tiptap 编辑器中的选区
 * 注: from/to 是 ProseMirror 字符位置 (0-based, exclusive end)
 */
export interface TextSelection {
  /** 选区起始位置 (inclusive) */
  from: number;
  /** 选区结束位置 (exclusive) */
  to: number;
  /** 选中的纯文本 */
  text: string;
}

// ============ AI 操作 ============

/** AI 操作类型 */
export type AIOperationType =
  | 'continue' // AI 续写 (整章) → /api/write/stream
  | 'rewrite' // AI 重写选区 → /api/chapter/{n}/rewrite
  | 'insert' // AI 插入段落 → /api/chapter/{n}/insert
  | 'deslop' // 去 AI 味 (Sprint 3 范围, 占位)
  | 'review'; // 送审 (Sprint 3 范围, 占位)

// ============ 写作进度 (UI 视图) ============

/**
 * 写作进度 UI 视图 (与后端 pipeline.write_chapter 一致)
 *
 * 字段命名遵循前端 UI 习惯 (camelCase), 与 api/types.ts 的
 * WriteProgressEventSchema (snake_case) 不同。
 */
export interface WriteProgressView {
  phase: WritePhase | 'idle' | 'cancelled' | 'error';
  charsWritten: number;
  charsPerSecond?: number;
  etaSeconds?: number;
  taskId?: string;
  message?: string;
  outputPath?: string;
  errorMessage?: string;
  errorCode?: string;
}

// ============ 8 阶段写作配置 (UI 权重) ============

/** 8 阶段权重 (playbook §9.5) */
export const PHASE_WEIGHTS: Record<WritePhase, number> = {
  init: 0,
  pre_write_check: 5,
  writing: 60,
  save: 75,
  extract: 85,
  merge: 95,
  post_write_check: 99,
  done: 100,
};

/** 给定 phase 返回进度百分比 0~100 */
export function phaseProgressPercent(phase: WritePhase): number {
  return PHASE_WEIGHTS[phase] ?? 0;
}

/** 阶段中文 label */
export const PHASE_LABELS: Record<WritePhase, string> = {
  init: '初始化',
  pre_write_check: '写作前检查',
  writing: '写作中',
  save: '保存',
  extract: '提取',
  merge: '合并',
  post_write_check: '写作后检查',
  done: '完成',
};