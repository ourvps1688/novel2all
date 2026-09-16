/**
 * Skill 执行历史 zustand store
 *
 * 用途：
 *   - 记录每个 skill 最近 N 次执行 (用于 SkillsPage "最近运行" 区)
 *   - 跟踪当前正在执行的 task (用于跨组件共享状态)
 *   - 持久化到 localStorage (V1.5.x 不做; 数据量小, 刷新即失)
 *
 * 设计：
 *   - 按 skillName 分桶, 每桶保留最新 N 条 (默认 10)
 *   - startRun → 启动一条新 entry (返回 taskId)
 *   - finishRun → 标记 status=done/error/cancelled, 写 output
 *   - cancelRun → 同 finishRun(status='cancelled')
 */

import { create } from 'zustand';

import type { SkillExecutionHistoryEntry, SkillExecutionPhase } from '../types/skills';

const HISTORY_LIMIT_PER_SKILL = 10;
const STORE_KEY = 'n2a-skill-history-v1';

export interface SkillExecutionState {
  /** 按 skill 名分桶的历史 (最新在前) */
  history: Record<string, SkillExecutionHistoryEntry[]>;
  /** 当前正在执行的 (skillName -> entry) */
  current: Record<string, SkillExecutionHistoryEntry | undefined>;

  /** 启动一次执行 (返回 taskId) */
  startRun: (skillName: string, inputPreview: string) => string;
  /** 完成一次执行 (success/error/cancelled) */
  finishRun: (
    skillName: string,
    taskId: string,
    status: SkillExecutionPhase,
    outputPreview?: string,
  ) => void;
  /** 清理单个 skill 的历史 */
  clearHistory: (skillName: string) => void;
  /** 清空所有历史 */
  clearAll: () => void;
}

// ============ 持久化 ============

function loadFromStorage(): Partial<SkillExecutionState> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as {
      history?: Record<string, SkillExecutionHistoryEntry[]>;
    };
    return { history: parsed.history ?? {} };
  } catch {
    return {};
  }
}

function saveToStorage(history: Record<string, SkillExecutionHistoryEntry[]>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify({ history }));
  } catch {
    // quota exceeded / disabled - ignore
  }
}

// ============ Store ============

function genTaskId(): string {
  // 短 ID + 时间戳 (避免和后端 uuid 冲突)
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `${ts}-${rand}`;
}

function truncatePreview(text: string, max = 80): string {
  if (!text) return '';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export const useSkillExecutionStore = create<SkillExecutionState>((set) => {
  const initial = loadFromStorage();
  return {
    history: initial.history ?? {},
    current: {},

    startRun: (skillName, inputPreview) => {
      const taskId = genTaskId();
      const now = Date.now();
      const entry: SkillExecutionHistoryEntry = {
        skillName,
        taskId,
        startedAt: now,
        finishedAt: null,
        status: 'preparing',
        inputPreview: truncatePreview(inputPreview),
        outputPreview: '',
        durationMs: 0,
      };

      set((state) => {
        const existing = state.history[skillName] ?? [];
        const nextHistory = {
          ...state.history,
          [skillName]: [entry, ...existing].slice(0, HISTORY_LIMIT_PER_SKILL),
        };
        saveToStorage(nextHistory);
        return {
          history: nextHistory,
          current: { ...state.current, [skillName]: entry },
        };
      });

      return taskId;
    },

    finishRun: (skillName, taskId, status, outputPreview = '') => {
      const now = Date.now();
      set((state) => {
        const existing = state.history[skillName] ?? [];
        const updated = existing.map((e) =>
          e.taskId === taskId
            ? {
                ...e,
                status,
                finishedAt: now,
                durationMs: now - e.startedAt,
                outputPreview: truncatePreview(outputPreview || e.outputPreview, 200),
              }
            : e,
        );
        const nextHistory = { ...state.history, [skillName]: updated };
        saveToStorage(nextHistory);

        const cur = state.current[skillName];
        const nextCurrent = { ...state.current };
        if (cur?.taskId === taskId) {
          nextCurrent[skillName] = {
            ...cur,
            status,
            finishedAt: now,
            durationMs: now - cur.startedAt,
            outputPreview: truncatePreview(outputPreview || cur.outputPreview, 200),
          };
        }
        return { history: nextHistory, current: nextCurrent };
      });
    },

    clearHistory: (skillName) => {
      set((state) => {
        const next = { ...state.history };
        delete next[skillName];
        saveToStorage(next);
        return { history: next };
      });
    },

    clearAll: () => {
      saveToStorage({});
      set({ history: {}, current: {} });
    },
  };
});

// ============ Selectors ============

/** 取某 skill 的最近 N 条历史 (默认 5) */
export const skillHistorySelectors = {
  recent: (skillName: string, limit = 5) => (state: SkillExecutionState): SkillExecutionHistoryEntry[] => {
    const list = state.history[skillName] ?? [];
    return list.slice(0, limit);
  },
  last: (skillName: string) => (state: SkillExecutionState): SkillExecutionHistoryEntry | null => {
    const list = state.history[skillName];
    return list && list.length > 0 ? (list[0] ?? null) : null;
  },
  isRunning: (skillName: string) => (state: SkillExecutionState): boolean => {
    const cur = state.current[skillName];
    if (!cur) return false;
    return cur.status === 'preparing' || cur.status === 'running';
  },
};