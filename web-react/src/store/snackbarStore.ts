/**
 * 全局 Snackbar store（zustand）
 * 任何模块都可调用 useSnackbar().show() 触发提示
 */

import { create } from 'zustand';

export type SnackbarSeverity = 'success' | 'info' | 'warning' | 'error';

export interface SnackbarMessage {
  id: number;
  message: string;
  severity: SnackbarSeverity;
  duration: number;
}

interface SnackbarState {
  queue: SnackbarMessage[];
  current: SnackbarMessage | null;
  show: (message: string, severity?: SnackbarSeverity, duration?: number) => void;
  dismiss: () => void;
  next: () => void;
}

let _id = 0;

export const useSnackbarStore = create<SnackbarState>((set, get) => ({
  queue: [],
  current: null,

  show: (message, severity = 'info', duration = 4000) => {
    const msg: SnackbarMessage = {
      id: ++_id,
      message,
      severity,
      duration,
    };
    const cur = get().current;
    if (cur == null) {
      set({ current: msg });
    } else {
      set((s) => ({ queue: [...s.queue, msg] }));
    }
  },

  dismiss: () => {
    set({ current: null });
    // 200ms 后展示下一条（避免抖动）
    setTimeout(() => get().next(), 200);
  },

  next: () => {
    const [head, ...rest] = get().queue;
    set({ current: head ?? null, queue: rest });
  },
}));
