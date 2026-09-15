/**
 * UI 层模型类型（与 api/types.ts 区分）
 */

import type { WritePhase } from '../api/types';

/** 8 阶段进度（与后端 pipeline.write_chapter 一致） */
export const WRITE_PHASES: { id: WritePhase | 'idle' | 'cancelled' | 'error'; label: string; weight: number }[] = [
  { id: 'init', label: '初始化', weight: 0.02 },
  { id: 'pre_write_check', label: '写作前检查', weight: 0.05 },
  { id: 'writing', label: '写作中', weight: 0.6 },
  { id: 'save', label: '保存', weight: 0.1 },
  { id: 'extract', label: '提取', weight: 0.08 },
  { id: 'merge', label: '合并', weight: 0.08 },
  { id: 'post_write_check', label: '写作后检查', weight: 0.05 },
  { id: 'done', label: '完成', weight: 0.02 },
];

/** 给定当前 phase，返回 0~1 进度（用于 progress bar） */
export function computePhaseProgress(currentPhase: WritePhase | 'idle' | 'cancelled' | 'error'): number {
  if (currentPhase === 'done') return 1;
  if (currentPhase === 'error' || currentPhase === 'cancelled' || currentPhase === 'idle') return 0;
  let acc = 0;
  for (const p of WRITE_PHASES) {
    if (p.id === currentPhase) return acc + p.weight / 2;
    acc += p.weight;
  }
  return 1;
}

/** Dashboard 卡片类型 */
export type DashboardCardType =
  | 'currentChapter'
  | 'projectProgress'
  | 'cacheStatus'
  | 'todayCost';

/** Onboarding 步骤 */
export type OnboardingStep = 'projectInit' | 'modelSelect' | 'firstWrite';
