/**
 * Sidebar：左侧导航（主功能 + 管理）
 *
 * 移动端适配（PRD §5 Sprint 4 第 7 项）：
 *   - < sm: temporary drawer（由 AppShell mobileOpen 控制）
 *   - >= sm: permanent drawer（占位 ml=drawerWidth）
 */

import { Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Toolbar, Divider, Box, Typography } from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import EditNoteIcon from '@mui/icons-material/EditNote';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import RateReviewIcon from '@mui/icons-material/RateReview';
import DownloadIcon from '@mui/icons-material/Download';
import SettingsIcon from '@mui/icons-material/Settings';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../../auth/useAuth';

interface SidebarProps {
  drawerWidth: number;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  group: 'main' | 'admin';
  exact?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: '主页', path: '/', icon: <DashboardIcon />, group: 'main', exact: true },
  { label: 'Skills', path: '/skills', icon: <AutoFixHighIcon />, group: 'main' },
  { label: '写作', path: '/write', icon: <EditNoteIcon />, group: 'main' },
  { label: '章节', path: '/chapters', icon: <MenuBookIcon />, group: 'main' },
  { label: '审查', path: '/review', icon: <RateReviewIcon />, group: 'main' },
  { label: '导出', path: '/export', icon: <DownloadIcon />, group: 'main' },
  { label: '封面', path: '/cover', icon: <AutoFixHighIcon />, group: 'main' },
  { label: '导入', path: '/import', icon: <UploadFileIcon />, group: 'main' },
  { label: '设置', path: '/settings', icon: <SettingsIcon />, group: 'main' },
];

const ADMIN_ITEMS: NavItem[] = [
  { label: '管理', path: '/admin', icon: <AdminPanelSettingsIcon />, group: 'admin' },
];

const drawerSx = (drawerWidth: number) => ({
  width: drawerWidth,
  flexShrink: 0,
  '& .MuiDrawer-paper': {
    width: drawerWidth,
    boxSizing: 'border-box',
    borderRight: 1,
    borderColor: 'divider',
    bgcolor: (t: { palette: { mode: string; background: { paper: string } } }) => t.palette.background.paper,
  },
});

export function Sidebar({ drawerWidth, mobileOpen = false, onMobileClose }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAdmin } = useAuth();

  const isActive = (item: NavItem): boolean => {
    if (item.exact) return location.pathname === item.path;
    return location.pathname.startsWith(item.path);
  };

  // 点击导航后自动关闭 mobile drawer
  const handleNavigate = (path: string): void => {
    navigate(path);
    onMobileClose?.();
  };

  const drawerContent = (
    <>
      <Toolbar /> {/* spacer for fixed header */}
      <Box sx={{ overflow: 'auto', py: 1 }}>
        <Typography variant="overline" sx={{ px: 2, color: 'text.secondary' }}>
          主功能
        </Typography>
        <List dense>
          {NAV_ITEMS.map((item) => (
            <ListItem key={item.path} disablePadding>
              <ListItemButton
                selected={isActive(item)}
                onClick={() => handleNavigate(item.path)}
                sx={{
                  mx: 1,
                  borderRadius: 1,
                  '&.Mui-selected': {
                    bgcolor: (t) => (t.palette.mode === 'light' ? 'primary.50' : 'primary.900'),
                    color: 'primary.main',
                    '& .MuiListItemIcon-root': { color: 'primary.main' },
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>

        {isAdmin && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="overline" sx={{ px: 2, color: 'text.secondary' }}>
              管理
            </Typography>
            <List dense>
              {ADMIN_ITEMS.map((item) => (
                <ListItem key={item.path} disablePadding>
                  <ListItemButton
                    selected={isActive(item)}
                    onClick={() => handleNavigate(item.path)}
                    sx={{
                      mx: 1,
                      borderRadius: 1,
                      '&.Mui-selected': {
                        bgcolor: (t) =>
                          t.palette.mode === 'light' ? 'secondary.50' : 'secondary.900',
                        color: 'secondary.main',
                        '& .MuiListItemIcon-root': { color: 'secondary.main' },
                      },
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
                    <ListItemText primary={item.label} />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          </>
        )}
      </Box>
    </>
  );

  return (
    <>
      {/* 桌面端：permanent drawer (>= sm) */}
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', sm: 'block' },
          ...drawerSx(drawerWidth),
        }}
        open
      >
        {drawerContent}
      </Drawer>

      {/* 移动端：temporary drawer (< sm) */}
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onMobileClose}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', sm: 'none' },
          ...drawerSx(drawerWidth),
        }}
      >
        {drawerContent}
      </Drawer>
    </>
  );
}
