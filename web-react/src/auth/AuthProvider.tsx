/**
 * AuthProvider：
 *  1. mount 时调 /api/auth/me 同步 store
 *  2. 注册 axios 401 全局回调（清空 store + navigate('/login')）
 *  3. 提供 useAuth() 给子组件取 store + actions
 *
 * 注意：此 Provider 只是 wrapper（zustand store 是全局的，不需要 React Context）
 * 真正的"强制重渲染"由 zustand 的订阅机制保证
 */

import { useEffect, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { CircularProgress, Box } from '@mui/material';

import { setUnauthorizedHandler } from '../api/client';
import { useMe } from '../api/auth';
import { useAuthStore, authSelectors } from '../store/authStore';
import { useSnackbar } from '../hooks/useSnackbar';
import type { User } from '../api/types';

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const setUser = useAuthStore((s) => s.setUser);
  const setLoading = useAuthStore((s) => s.setLoading);
  const setInitialized = useAuthStore((s) => s.setInitialized);
  const clear = useAuthStore((s) => s.clear);
  const initialized = useAuthStore((s) => s.initialized);
  const loading = useAuthStore((s) => s.loading);

  // 注册 401 全局回调
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
      // 仅在非登录页时跳转
      if (!window.location.pathname.startsWith('/login')) {
        navigate('/login', { replace: true });
        snackbar.warning('登录已失效，请重新登录');
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [clear, navigate, snackbar]);

  // 启动时验证
  const meQuery = useMe({
    enabled: !initialized, // 已初始化后不再自动 fetch
  });

  useEffect(() => {
    if (!initialized) {
      setLoading(meQuery.isLoading);
    }
    if (meQuery.isSuccess) {
      const u: User | null = meQuery.data.user;
      setUser(u);
      setInitialized(true);
    }
    if (meQuery.isError) {
      // 网络异常但非 401（401 已被 interceptor 处理）
      setInitialized(true);
    }
  }, [meQuery.isLoading, meQuery.isSuccess, meQuery.isError, meQuery.data, initialized, setUser, setLoading, setInitialized]);

  // 首次初始化显示 loading
  if (!initialized || loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  return <>{children}</>;
}

/**
 * 取 auth store 的便捷 hook（含派生 selector）
 */
export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const initialized = useAuthStore((s) => s.initialized);
  const isAuthenticated = useAuthStore(authSelectors.isAuthenticated);
  const isAdmin = useAuthStore(authSelectors.isAdmin);

  return {
    user,
    initialized,
    isAuthenticated,
    isAdmin,
    /** 用户名（fallback: "游客"） */
    username: user?.username ?? '游客',
    /** 用户角色（fallback: "viewer"） */
    role: user?.role ?? 'viewer',
  };
}
