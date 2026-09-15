/**
 * Header：顶栏 logo + 用户菜单 + 主题切换 + 注销
 */

import { useState } from 'react';
import {
  AppBar,
  Avatar,
  Box,
  IconButton,
  Menu,
  MenuItem,
  Toolbar,
  Tooltip,
  Typography,
  Divider,
  ListItemIcon,
  Chip,
} from '@mui/material';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import LogoutIcon from '@mui/icons-material/Logout';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import PersonIcon from '@mui/icons-material/Person';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../../auth/useAuth';
import { useThemeStore } from '../../store/themeStore';

interface HeaderProps {
  drawerWidth: number;
}

export function Header({ drawerWidth }: HeaderProps) {
  const navigate = useNavigate();
  const { user, username, role, logout } = useAuth();
  const themeMode = useThemeStore((s) => s.mode);
  const toggleTheme = useThemeStore((s) => s.toggle);

  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  const handleOpen = (e: React.MouseEvent<HTMLElement>): void => setAnchorEl(e.currentTarget);
  const handleClose = (): void => setAnchorEl(null);

  const handleLogout = async (): Promise<void> => {
    handleClose();
    await logout();
  };

  const handleProfile = (): void => {
    handleClose();
    navigate('/settings');
  };

  return (
    <AppBar
      position="fixed"
      color="default"
      elevation={0}
      sx={{
        width: { sm: `calc(100% - ${drawerWidth}px)` },
        ml: { sm: `${drawerWidth}px` },
        bgcolor: (t) => (t.palette.mode === 'light' ? 'background.paper' : 'background.paper'),
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      <Toolbar sx={{ justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: 1,
              bgcolor: 'primary.main',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontWeight: 700,
              fontSize: 14,
            }}
          >
            n2a
          </Box>
          <Typography variant="h6" component="div" sx={{ fontWeight: 600 }}>
            novel2all
          </Typography>
          <Chip size="small" label="V1.5" variant="outlined" sx={{ ml: 1 }} />
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title={themeMode === 'dark' ? '切换到亮色' : '切换到暗色'}>
            <IconButton onClick={toggleTheme} aria-label="toggle theme">
              {themeMode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />}
            </IconButton>
          </Tooltip>

          <Tooltip title={user ? `${username} · ${role}` : '未登录'}>
            <IconButton onClick={handleOpen} aria-label="user menu">
              <Avatar
                sx={{ width: 32, height: 32, bgcolor: role === 'admin' ? 'secondary.main' : 'primary.main' }}
              >
                {role === 'admin' ? (
                  <AdminPanelSettingsIcon fontSize="small" />
                ) : (
                  username.charAt(0).toUpperCase()
                )}
              </Avatar>
            </IconButton>
          </Tooltip>

          <Menu
            anchorEl={anchorEl}
            open={open}
            onClose={handleClose}
            onClick={(e) => e.stopPropagation()}
            transformOrigin={{ horizontal: 'right', vertical: 'top' }}
            anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
          >
            <Box sx={{ px: 2, py: 1, minWidth: 220 }}>
              <Typography variant="subtitle2">{username}</Typography>
              <Typography variant="caption" color="text.secondary">
                角色：{role}
              </Typography>
            </Box>
            <Divider />
            <MenuItem onClick={handleProfile}>
              <ListItemIcon>
                <PersonIcon fontSize="small" />
              </ListItemIcon>
              设置
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              注销
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
