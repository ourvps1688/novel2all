/**
 * ProtectedRoute：已登录守卫
 *
 * 用法：
 *   <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
 *     <Route path="/" element={<DashboardPage />} />
 *   </Route>
 *
 * 注意：AuthProvider 已在 App 外层确保 initialized=true 后才渲染
 * 这里只需判断 user 是否存在
 */

import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { useAuthStore } from '../store/authStore';

interface ProtectedRouteProps {
  children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (user == null) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
