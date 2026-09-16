/**
 * AdminProjectsPage — 项目分享管理（PRD §5 Sprint 4 第 3 项）
 *
 * 功能:
 *   - 选择用户 → 列出该用户的所有项目（GET /api/auth/users/{id}/projects）
 *   - 显示当前分享状态
 *   - 项目分享：选择用户 → 授权
 *   - 分享撤销
 *
 * 后端 API:
 *   GET    /api/auth/users/{user_id}/projects → UserProjectsSchema
 *   POST   /api/auth/projects/{project_root:path}/share?user_id=&role=
 *   DELETE /api/auth/projects/{project_root:path}/share/{user_id}
 */

import { useState } from 'react';

import {
  Stack,
  Typography,
  Paper,
  Button,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import ShareIcon from '@mui/icons-material/Share';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import LockRemoveIcon from '@mui/icons-material/PersonRemove';

import { useUserProjects } from '../../api/auth';
import { useUsers } from '../../api/users';
import { useSnackbar } from '../../hooks/useSnackbar';

type ShareRole = 'editor' | 'viewer';

export function AdminProjectsPage() {
  const snackbar = useSnackbar();
  const usersQuery = useUsers();
  const users = usersQuery.data?.users ?? [];

  const [selectedUserId, setSelectedUserId] = useState<number | ''>('');
  const userProjectsQuery = useUserProjects(
    selectedUserId === '' ? null : Number(selectedUserId),
  );
  const projects = userProjectsQuery.data?.projects ?? [];

  const handleShare = async (
    projectPath: string,
    targetUserId: number,
    role: ShareRole,
  ) => {
    if (!confirm(`分享项目「${projectPath}」给 user_id=${targetUserId} (${role})？`)) return;
    try {
      const params = new URLSearchParams({ user_id: String(targetUserId), role });
      const resp = await fetch(
        `/api/auth/projects/${encodeURI(projectPath)}/share?${params}`,
        { method: 'POST', credentials: 'include' },
      );
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt.slice(0, 200)}`);
      }
      snackbar.success(`已分享 (${(await resp.json()).shared ?? 1})`);
      void userProjectsQuery.refetch();
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRevoke = async (projectPath: string, targetUserId: number) => {
    if (!confirm(`撤销 user_id=${targetUserId} 的项目访问？`)) return;
    try {
      const resp = await fetch(
        `/api/auth/projects/${encodeURI(projectPath)}/share/${targetUserId}`,
        { method: 'DELETE', credentials: 'include' },
      );
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt.slice(0, 200)}`);
      }
      snackbar.success('已撤销分享');
      void userProjectsQuery.refetch();
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Stack spacing={3}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          项目分享管理
        </Typography>
        <FormControl size="small" sx={{ minWidth: 240 }} data-testid="admin-projects-user-select">
          <InputLabel>选择用户</InputLabel>
          <Select
            value={selectedUserId}
            label="选择用户"
            onChange={(e) => setSelectedUserId(e.target.value as number | '')}
          >
            <MenuItem value="">（请选择）</MenuItem>
            {users.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.username} ({u.role}) — ID:{u.id}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Tooltip title="刷新">
          <span>
            <IconButton
              onClick={() => {
                void usersQuery.refetch();
                void userProjectsQuery.refetch();
              }}
              disabled={usersQuery.isFetching || userProjectsQuery.isFetching}
            >
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      {(usersQuery.isError || userProjectsQuery.isError) && (
        <Alert severity="error">
          加载失败：
          {(usersQuery.error as Error | null)?.message ?? ''}
          {(userProjectsQuery.error as Error | null)?.message ?? ''}
        </Alert>
      )}

      {usersQuery.isLoading ? (
        <Stack alignItems="center" sx={{ py: 4 }}>
          <CircularProgress />
        </Stack>
      ) : selectedUserId === '' ? (
        <Alert severity="info">请选择用户查看其可访问项目</Alert>
      ) : userProjectsQuery.isLoading ? (
        <Stack alignItems="center" sx={{ py: 4 }}>
          <CircularProgress />
        </Stack>
      ) : projects.length === 0 ? (
        <Alert severity="info">该用户暂无项目</Alert>
      ) : (
        projects.map((proj) => (
          <Paper key={proj.path} sx={{ p: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <ShareIcon color="primary" />
              <Typography variant="subtitle1" sx={{ flex: 1 }}>
                {proj.name ?? proj.path}
              </Typography>
              <Chip size="small" label={proj.path} variant="outlined" />
              {proj.role && (
                <Chip size="small" label={proj.role} color="primary" variant="outlined" />
              )}
              {proj.shared && (
                <Chip size="small" label="已分享" color="success" variant="outlined" />
              )}
            </Stack>

            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                创建时间：{proj.created_at ?? '-'}
              </Typography>
              {proj.shared && (
                <Tooltip title="撤销该用户的项目分享">
                  <Button
                    size="small"
                    color="error"
                    startIcon={<LockRemoveIcon />}
                    onClick={() => void handleRevoke(proj.path, Number(selectedUserId))}
                  >
                    撤销分享
                  </Button>
                </Tooltip>
              )}
              <Tooltip title="分享给其他用户">
                <ShareOtherUserButton
                  projectPath={proj.path}
                  excludeUserId={Number(selectedUserId)}
                  candidates={users}
                  onShare={(userId, role) => void handleShare(proj.path, userId, role)}
                />
              </Tooltip>
            </Stack>
          </Paper>
        ))
      )}
    </Stack>
  );
}

interface ShareOtherUserButtonProps {
  projectPath: string;
  excludeUserId: number;
  candidates: Array<{ id: number; username: string; role: string }>;
  onShare: (userId: number, role: ShareRole) => void;
}

function ShareOtherUserButton({
  projectPath,
  excludeUserId,
  candidates,
  onShare,
}: ShareOtherUserButtonProps) {
  const [open, setOpen] = useState(false);
  const [userId, setUserId] = useState<number | ''>('');
  const [role, setRole] = useState<ShareRole>('viewer');

  const others = candidates.filter((u) => u.id !== excludeUserId);

  if (!open) {
    return (
      <Button
        size="small"
        startIcon={<PersonAddIcon />}
        onClick={() => setOpen(true)}
        data-testid={`admin-projects-share-other-${projectPath}`}
      >
        分享给其他用户
      </Button>
    );
  }

  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel>目标用户</InputLabel>
        <Select
          value={userId}
          label="目标用户"
          onChange={(e) => setUserId(e.target.value as number | '')}
        >
          {others.map((u) => (
            <MenuItem key={u.id} value={u.id}>
              {u.username} (#{u.id})
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <FormControl size="small" sx={{ minWidth: 100 }}>
        <InputLabel>权限</InputLabel>
        <Select
          value={role}
          label="权限"
          onChange={(e) => setRole(e.target.value as ShareRole)}
        >
          <MenuItem value="editor">editor</MenuItem>
          <MenuItem value="viewer">viewer</MenuItem>
        </Select>
      </FormControl>
      <Button
        size="small"
        variant="contained"
        disabled={userId === ''}
        onClick={() => {
          if (userId === '') return;
          onShare(Number(userId), role);
          setOpen(false);
          setUserId('');
        }}
      >
        确认
      </Button>
      <Button size="small" onClick={() => setOpen(false)}>
        取消
      </Button>
    </Stack>
  );
}
