/**
 * Theme store：light / dark mode
 * localStorage 持久化（key: 'n2a.theme'）
 */

import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'n2a.theme';

function loadInitial(): ThemeMode {
  try {
    const t = localStorage.getItem(STORAGE_KEY);
    if (t === 'dark') return 'dark';
  } catch {
    /* localStorage 不可用 */
  }
  return 'light';
}

function persist(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* 忽略 */
  }
}

interface ThemeState {
  mode: ThemeMode;
  toggle: () => void;
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: loadInitial(),
  toggle: () => {
    const next: ThemeMode = get().mode === 'light' ? 'dark' : 'light';
    persist(next);
    set({ mode: next });
    if (next === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  },
  setMode: (mode) => {
    persist(mode);
    set({ mode });
    if (mode === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  },
}));
