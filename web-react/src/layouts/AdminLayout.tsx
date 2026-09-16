/**
 * AdminLayout — 管理员后台布局
 *
 * 路由守卫:
 *   - 未登录 → 跳到 /login
 *   - 已登录但 user.role !== 'admin' → 跳到 /
 *
 * 侧边导航: Users / Audit / Projects
 */

import { useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

import {
  Container,
  Typography,
  Box,
  Tabs,
  Tab,
  Stack,
  Alert,
} from '@mui/material';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';

import { useMe } from '../api/auth';

interface AdminLayoutProps {
  /** 页面标题（顶部） */
  title: string;
  /** 标题右侧可选 action 按钮 */
  action?: React.ReactNode;
  /** 子元素（路由嵌套时通过 <Outlet /> 渲染，可选） */
  children?: React.ReactNode;
}

export function AdminLayout({ title, action }: AdminLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: me, isLoading } = useMe();

  const user = me?.user ?? null;
  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    if (isLoading) return;
    if (!me?.authenticated || !user) {
      void navigate('/login');
      return;
    }
    if (!isAdmin) {
      void navigate('/');
    }
  }, [me, user, isAdmin, isLoading, navigate]);

  // Loading / 未授权时显示骨架
  if (isLoading || !user || !isAdmin) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="info">检查管理员权限...</Alert>
      </Container>
    );
  }

  // 计算当前 tab (根据 pathname)
  const currentPath = location.pathname;
  let currentTab = 0;
  if (currentPath.startsWith('/admin/audit')) currentTab = 1;
  else if (currentPath.startsWith('/admin/projects')) currentTab = 2;

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 3 }}>
        <AdminPanelSettingsIcon color="primary" sx={{ fontSize: 32 }} />
        <Box sx={{ flex: 1 }}>
          <Typography variant="h4">{title}</Typography>
          <Typography variant="body2" color="text.secondary">
            管理员后台 · 当前用户：{user.username} ({user.role})
          </Typography>
        </Box>
        {action}
      </Stack>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={currentTab} aria-label="admin-tabs">
          <Tab
            label="用户管理"
            onClick={() => void navigate('/admin/users')}
            data-testid="admin-tab-users"
          />
          <Tab
            label="审计日志"
            onClick={() => void navigate('/admin/audit')}
            data-testid="admin-tab-audit"
          />
          <Tab
            label="项目分享"
            onClick={() => void navigate('/admin/projects')}
            data-testid="admin-tab-projects"
          />
        </Tabs>
      </Box>

      <Outlet />
    </Container>
  );
}
