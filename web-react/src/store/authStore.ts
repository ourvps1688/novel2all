/**
 * Auth zustand store
 *
 * 状态机：
 *   - user: null      → 未登录（或正在初始化）
 *   - user: User      → 已登录
 *
 * 与 React Query 的关系：
 *   - useMe() 触发 fetch，结果同步到 store
 *   - mutation (login/logout) 直接调用 store.setUser() / clear()
 *   - axios interceptor 在 401 时调用 store.clear() + setUnauthorizedHandler 注册的回调
 */

import { create } from 'zustand';
import type { User } from '../api/types';

export interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
}

export interface AuthActions {
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (initialized: boolean) => void;
  clear: () => void;
}

export type AuthStore = AuthState & AuthActions;

const initialState: AuthState = {
  user: null,
  loading: false,
  error: null,
  initialized: false,
};

export const useAuthStore = create<AuthStore>((set) => ({
  ...initialState,

  setUser: (user) => set({ user, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setInitialized: (initialized) => set({ initialized }),

  clear: () => set({ user: null, error: null, initialized: true }),
}));

// ==================== Selectors ====================

export const authSelectors = {
  isAuthenticated: (s: AuthState): boolean => s.user != null,
  isAdmin: (s: AuthState): boolean => s.user?.role === 'admin',
  isEditor: (s: AuthState): boolean => s.user?.role === 'editor' || s.user?.role === 'admin',
};
