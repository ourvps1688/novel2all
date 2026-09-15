/**
 * useAuth：取 auth 状态 + 暴露 login/logout mutation
 */

import { useNavigate } from 'react-router-dom';

import { useAuth as useAuthContext } from './AuthProvider';
import { useLoginMutation, useLogoutMutation } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import { useSnackbar } from '../hooks/useSnackbar';
import { ApiError } from '../utils/errors';

export function useAuth() {
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const auth = useAuthContext();
  const setUser = useAuthStore((s) => s.setUser);
  const clear = useAuthStore((s) => s.clear);

  const loginMutation = useLoginMutation();
  const logoutMutation = useLogoutMutation();

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      const result = await loginMutation.mutateAsync({ username, password });
      setUser(result.user);
      snackbar.success(`欢迎回来，${result.user.username}`);
      navigate('/', { replace: true });
      return true;
    } catch (err) {
      if (err instanceof ApiError) {
        snackbar.error(err.userMessage);
      } else {
        snackbar.error('登录失败：未知错误');
      }
      return false;
    }
  };

  const logout = async (): Promise<void> => {
    try {
      await logoutMutation.mutateAsync();
      clear();
      snackbar.info('已注销');
      navigate('/login', { replace: true });
    } catch (err) {
      // 即使后端报错也清空前端（cookie 可能已失效）
      clear();
      navigate('/login', { replace: true });
      if (err instanceof ApiError && !err.isUnauthorized) {
        snackbar.error('注销失败：' + err.userMessage);
      }
    }
  };

  return {
    ...auth,
    login,
    logout,
    isLoggingIn: loginMutation.isPending,
    isLoggingOut: logoutMutation.isPending,
    loginError: loginMutation.error,
  };
}
