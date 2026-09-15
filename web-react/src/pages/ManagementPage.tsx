/**
 * ManagementPage：admin 管理页（T05 占位）
 *
 * 嵌套路由：
 *   /admin/users
 *   /admin/projects
 *   /admin/audit
 */

import { Container, Typography, Box, Alert, Stack, Tabs, Tab } from '@mui/material';
import { Routes, Route, Link, useLocation } from 'react-router-dom';

export function ManagementPage() {
  const location = useLocation();
  const currentTab = location.pathname.includes('/users')
    ? 'users'
    : location.pathname.includes('/projects')
      ? 'projects'
      : location.pathname.includes('/audit')
        ? 'audit'
        : 'users';

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        管理
      </Typography>

      <Alert severity="info" sx={{ mb: 2 }}>
        <strong>T10 占位</strong> — 完整实现见 P2 sprint。
      </Alert>

      <Tabs value={currentTab} sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tab label="用户" value="users" component={Link} to="/admin/users" />
        <Tab label="项目授权" value="projects" component={Link} to="/admin/projects" />
        <Tab label="审计日志" value="audit" component={Link} to="/admin/audit" />
      </Tabs>

      <Box sx={{ p: 3, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary">
            用户管理：<code>/api/auth/users</code> + CRUD（admin only）
          </Typography>
          <Typography variant="body2" color="text.secondary">
            项目授权：<code>/api/auth/users/&#123;id&#125;/projects</code>
          </Typography>
          <Typography variant="body2" color="text.secondary">
            审计日志：<code>/api/auth/audit</code>
          </Typography>
        </Stack>
      </Box>

      <Routes>
        <Route path="users" element={<Box />} />
        <Route path="projects" element={<Box />} />
        <Route path="audit" element={<Box />} />
      </Routes>
    </Container>
  );
}
