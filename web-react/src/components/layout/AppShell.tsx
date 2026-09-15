/**
 * AppShell：受保护页面的统一布局（侧栏 + 顶栏 + 内容 outlet）
 *
 * 用法（App.tsx）：
 *   <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
 *     <Route path="/" element={<DashboardPage />} />
 *   </Route>
 */

import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';

import { Header } from './Header';
import { Sidebar } from './Sidebar';

const DRAWER_WIDTH = 240;

export function AppShell() {
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Header drawerWidth={DRAWER_WIDTH} />
      <Sidebar drawerWidth={DRAWER_WIDTH} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { sm: `${DRAWER_WIDTH}px` },
          mt: '64px', // 顶栏高度
          minHeight: 'calc(100vh - 64px)',
          bgcolor: (t) => t.palette.background.default,
        }}
      >
        <Outlet />
      </Box>
    </Box>
  );
}
