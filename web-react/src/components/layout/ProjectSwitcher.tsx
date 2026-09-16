/**
 * ProjectSwitcher — 项目切换下拉（Sprint 5 第 2 批 / PRD §5 Sprint 5 第 3 项）
 *
 * 功能:
 *   - Header dropdown 列出当前用户可访问的所有项目
 *   - 点击项目 → useProjectSwitch() 切换 + invalidate queries
 *   - 当前激活项目显示 "✓ 当前" 标记
 *   - 刷新按钮 + 加载 / 错误状态
 *
 * 复用 useUserProjects (Sprint 4 加的 hook):
 *   普通用户: useUserProjects(me.user.id) 列自己项目
 *   admin: useUserProjects(targetUserId) 列任意用户项目
 */

import { useState, useMemo, useEffect } from 'react';

import {
  Box,
  Button,
  IconButton,
  Tooltip,
  Menu,
  MenuItem,
  Typography,
  Divider,
  Stack,
  Chip,
  ListItemIcon,
  ListItemText,
  CircularProgress,
  Alert,
} from '@mui/material';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckIcon from '@mui/icons-material/Check';
import FolderIcon from '@mui/icons-material/Folder';

import { useMe } from '../../api/auth';
import { useUserProjects } from '../../api/auth';
import {
  useProjectContextStore,
  useProjectSwitch,
  type ProjectContext,
} from '../../store/projectContext';

export function ProjectSwitcher() {
  const me = useMe();
  const currentUserId = me.data?.user?.id ?? null;
  const { data, isLoading, isError, error, refetch, isFetching } = useUserProjects(currentUserId);
  const currentProject = useProjectContextStore((s) => s.currentProject);
  const setCurrentProject = useProjectContextStore((s) => s.setCurrentProject);
  const { switchProject } = useProjectSwitch();

  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  const projects: ProjectContext[] = useMemo(() => {
    if (!data?.projects) return [];
    return data.projects.map((p) => ({
      path: p.path,
      name: p.name ?? p.path.split('/').pop() ?? p.path,
      role: (p.role as ProjectContext['role']) ?? undefined,
    }));
  }, [data]);

  // 如果当前 currentProject 不在用户项目列表中（比如 admin 切换了 user），
  // 保留当前选择，不自动清除（防止误清）
  // 如果是首次加载，自动选第一个
  useEffect(() => {
    if (!currentProject && projects.length > 0) {
      const first = projects[0];
      if (first) setCurrentProject(first);
    }
  }, [currentProject, projects, setCurrentProject]);

  const handleOpen = (e: React.MouseEvent<HTMLElement>): void => {
    setAnchorEl(e.currentTarget);
  };
  const handleClose = (): void => setAnchorEl(null);

  const handleSelect = (project: ProjectContext): void => {
    setCurrentProject(project);
    switchProject(project);
    handleClose();
  };

  const displayName = currentProject?.name ?? currentProject?.path ?? '默认项目';

  return (
    <>
      <Tooltip title="切换项目">
        <Button
          size="small"
          color="inherit"
          startIcon={<SwapHorizIcon />}
          onClick={handleOpen}
          data-testid="project-switcher"
          sx={{
            textTransform: 'none',
            color: 'text.primary',
            border: 1,
            borderColor: 'divider',
            px: 1.5,
            py: 0.5,
            borderRadius: 1,
          }}
        >
          <Typography
            variant="body2"
            noWrap
            sx={{ maxWidth: 160, fontWeight: 500 }}
          >
            {displayName}
          </Typography>
        </Button>
      </Tooltip>

      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        transformOrigin={{ horizontal: 'left', vertical: 'top' }}
        anchorOrigin={{ horizontal: 'left', vertical: 'bottom' }}
        slotProps={{
          paper: {
            sx: { minWidth: 320, maxWidth: 480, maxHeight: 480 },
          },
        }}
      >
        <Box sx={{ px: 2, py: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <FolderIcon color="primary" fontSize="small" />
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle2">切换项目</Typography>
              <Typography variant="caption" color="text.secondary">
                {projects.length} 个可访问项目
              </Typography>
            </Box>
            <Tooltip title="刷新列表">
              <span>
                <IconButton
                  size="small"
                  onClick={() => void refetch()}
                  disabled={isFetching}
                  data-testid="project-switcher-refresh"
                >
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Box>
        <Divider />

        {isLoading && (
          <Stack alignItems="center" sx={{ py: 3 }}>
            <CircularProgress size={20} />
          </Stack>
        )}

        {isError && (
          <Box sx={{ p: 2 }}>
            <Alert severity="error">
              加载项目失败：{(error as Error).message}
            </Alert>
          </Box>
        )}

        {!isLoading && !isError && projects.length === 0 && (
          <Box sx={{ p: 2 }}>
            <Alert severity="info">
              暂无可访问项目。请联系 admin 分享项目。
            </Alert>
          </Box>
        )}

        {projects.map((project) => {
          const isCurrent = project.path === currentProject?.path;
          return (
            <MenuItem
              key={project.path}
              selected={isCurrent}
              onClick={() => handleSelect(project)}
              data-testid={`project-switcher-item-${project.path}`}
            >
              <ListItemIcon>
                {isCurrent ? (
                  <CheckIcon color="primary" fontSize="small" />
                ) : (
                  <FolderIcon fontSize="small" />
                )}
              </ListItemIcon>
              <ListItemText
                primary={
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                      {project.name}
                    </Typography>
                    {project.role && (
                      <Chip
                        size="small"
                        label={project.role}
                        variant="outlined"
                        sx={{ height: 18, fontSize: 10 }}
                      />
                    )}
                  </Stack>
                }
                secondary={project.path}
              />
            </MenuItem>
          );
        })}
      </Menu>
    </>
  );
}
