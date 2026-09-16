/**
 * AppShell：受保护页面的统一布局（侧栏 + 顶栏 + 内容 outlet）
 *
 * 移动端适配（PRD §5 Sprint 4 第 7 项）：
 *   - < sm (xs): Sidebar 隐藏为 temporary drawer，Header 显示 hamburger menu 触发
 *   - >= sm: Sidebar 永久显示，Header 占位 ml=drawerWidth
 */

import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';

import { Header } from './Header';
import { Sidebar } from './Sidebar';

export const DRAWER_WIDTH = 240;

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleMobileToggle = (): void => setMobileOpen((v) => !v);
  const handleMobileClose = (): void => setMobileOpen(false);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Header
        drawerWidth={DRAWER_WIDTH}
        onMobileMenuToggle={handleMobileToggle}
      />
      <Sidebar
        drawerWidth={DRAWER_WIDTH}
        mobileOpen={mobileOpen}
        onMobileClose={handleMobileClose}
      />
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
