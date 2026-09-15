/**
 * Sidebar：左侧导航（4 主区）
 *
 * 区：
 *  1. 创作 — 写作 + 章节列表
 *  2. 审查 — review 队列
 *  3. 导出 — 整书/章节导出
 *  4. 管理 — 仅 admin：用户/项目/审计
 */

import { Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Toolbar, Divider, Box, Typography } from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import EditNoteIcon from '@mui/icons-material/EditNote';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import RateReviewIcon from '@mui/icons-material/RateReview';
import DownloadIcon from '@mui/icons-material/Download';
import SettingsIcon from '@mui/icons-material/Settings';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../../auth/useAuth';

interface SidebarProps {
  drawerWidth: number;
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
  { label: '写作', path: '/write', icon: <EditNoteIcon />, group: 'main' },
  { label: '章节', path: '/chapters', icon: <MenuBookIcon />, group: 'main' },
  { label: '审查', path: '/review', icon: <RateReviewIcon />, group: 'main' },
  { label: '导出', path: '/export', icon: <DownloadIcon />, group: 'main' },
  { label: '设置', path: '/settings', icon: <SettingsIcon />, group: 'main' },
];

const ADMIN_ITEMS: NavItem[] = [
  { label: '管理', path: '/admin', icon: <AdminPanelSettingsIcon />, group: 'admin' },
];

export function Sidebar({ drawerWidth }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAdmin } = useAuth();

  const isActive = (item: NavItem): boolean => {
    if (item.exact) return location.pathname === item.path;
    return location.pathname.startsWith(item.path);
  };

  return (
    <Drawer
      variant="permanent"
      sx={{
        display: { xs: 'none', sm: 'block' },
        width: drawerWidth,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: drawerWidth,
          boxSizing: 'border-box',
          borderRight: 1,
          borderColor: 'divider',
          bgcolor: (t) => t.palette.background.paper,
        },
      }}
    >
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
                onClick={() => navigate(item.path)}
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
                    onClick={() => navigate(item.path)}
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
    </Drawer>
  );
}
