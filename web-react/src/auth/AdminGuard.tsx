/**
 * AdminGuard：仅 admin 可访问
 * 用法：嵌套在 ProtectedRoute 之内
 */

import { Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Alert, Box, Typography } from '@mui/material';

import { useAuthStore } from '../store/authStore';

interface AdminGuardProps {
  children: ReactNode;
}

export function AdminGuard({ children }: AdminGuardProps) {
  const user = useAuthStore((s) => s.user);

  if (user == null) {
    return <Navigate to="/login" replace />;
  }

  if (user.role !== 'admin') {
    return (
      <Box sx={{ p: 4, maxWidth: 600, mx: 'auto' }}>
        <Alert severity="warning">
          <Typography variant="h6" gutterBottom>
            权限不足
          </Typography>
          <Typography variant="body2">
            管理页面仅限 <strong>admin</strong> 角色访问。当前角色：
            <code>{user.role}</code>。
          </Typography>
        </Alert>
      </Box>
    );
  }

  return <>{children}</>;
}
