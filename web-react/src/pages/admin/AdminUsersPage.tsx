/**
 * AdminUsersPage — 管理员用户管理页（PRD §5 Sprint 4 第 2 项）
 *
 * 功能:
 *   - 列出所有用户（useUsers → UsersListSchema → users[]）
 *   - 创建用户对话框（useCreateUser: username / password / role）
 *   - 删除用户确认（useDeleteUser）
 *   - 自我删除保护：禁止删自己
 */

import { useState } from 'react';

import {
  Stack,
  Typography,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  CircularProgress,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';

import { useMe } from '../../api/auth';
import { useCreateUser, useDeleteUser, useUsers } from '../../api/users';
import { useSnackbar } from '../../hooks/useSnackbar';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';

type Role = 'admin' | 'editor' | 'viewer';

interface FormState {
  username: string;
  password: string;
  role: Role;
}

const EMPTY_FORM: FormState = { username: '', password: '', role: 'editor' };

export function AdminUsersPage() {
  const snackbar = useSnackbar();
  const { data: me } = useMe();
  const usersQuery = useUsers();
  const createMut = useCreateUser();
  const deleteMut = useDeleteUser();

  const meUser = me?.user ?? null;
  const users = usersQuery.data?.users ?? [];
  const isSelf = (id: number | string | undefined) =>
    meUser && String(meUser.id) === String(id);

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);

  const handleSubmitCreate = async () => {
    if (!form.username.trim() || !form.password.trim()) {
      snackbar.warning('用户名和密码必填');
      return;
    }
    try {
      const user = await createMut.mutateAsync(form);
      snackbar.success(`已创建用户：${user.username}`);
      setCreateOpen(false);
      setForm(EMPTY_FORM);
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleDelete = async () => {
    if (deleteTargetId == null) return;
    try {
      const result = await deleteMut.mutateAsync(deleteTargetId);
      snackbar.success(`已删除用户（deleted=${result.deleted}）`);
      setDeleteTargetId(null);
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Stack spacing={3}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          用户列表 ({users.length})
        </Typography>
        <Tooltip title="刷新">
          <span>
            <IconButton
              onClick={() => void usersQuery.refetch()}
              disabled={usersQuery.isFetching}
            >
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateOpen(true)}
          data-testid="admin-users-create"
        >
          创建用户
        </Button>
      </Stack>

      {usersQuery.isError && (
        <Alert severity="error">
          加载用户失败：{(usersQuery.error as Error).message}
        </Alert>
      )}

      {usersQuery.isLoading ? (
        <Stack alignItems="center" sx={{ py: 4 }}>
          <CircularProgress />
        </Stack>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small" data-testid="admin-users-table">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>用户名</TableCell>
                <TableCell>角色</TableCell>
                <TableCell>状态</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id} hover>
                  <TableCell>{u.id}</TableCell>
                  <TableCell>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <span>{u.username}</span>
                      {isSelf(u.id) && <Chip size="small" label="YOU" color="primary" />}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={u.role}
                      color={u.role === 'admin' ? 'error' : u.role === 'editor' ? 'primary' : 'default'}
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={u.disabled ? '禁用' : '正常'}
                      color={u.disabled ? 'default' : 'success'}
                      variant={u.disabled ? 'outlined' : 'filled'}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip
                      title={isSelf(u.id) ? '不能删除自己' : '删除用户'}
                    >
                      <span>
                        <IconButton
                          size="small"
                          color="error"
                          disabled={isSelf(u.id) || deleteMut.isPending}
                          onClick={() => setDeleteTargetId(Number(u.id))}
                          data-testid={`admin-users-delete-${u.id}`}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {users.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} align="center">
                    <Typography color="text.secondary">暂无用户</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* 创建用户对话框 */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>创建用户</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="用户名"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              autoFocus
              fullWidth
              inputProps={{ 'data-testid': 'admin-users-create-username' }}
            />
            <TextField
              label="密码"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              fullWidth
              inputProps={{ 'data-testid': 'admin-users-create-password' }}
            />
            <FormControl fullWidth>
              <InputLabel>角色</InputLabel>
              <Select
                value={form.role}
                label="角色"
                onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                data-testid="admin-users-create-role"
              >
                <MenuItem value="admin">admin（管理员）</MenuItem>
                <MenuItem value="editor">editor（编辑）</MenuItem>
                <MenuItem value="viewer">viewer（只读）</MenuItem>
              </Select>
            </FormControl>
            <Alert severity="info">
              admin 可访问后台；editor 可写作；viewer 只读。
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>取消</Button>
          <Button
            variant="contained"
            disabled={createMut.isPending}
            onClick={() => void handleSubmitCreate()}
            data-testid="admin-users-create-submit"
          >
            {createMut.isPending ? '创建中...' : '创建'}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={deleteTargetId != null}
        title="删除用户"
        message={`确定删除用户 ID=${deleteTargetId}？此操作不可撤销。`}
        confirmText="删除"
        confirmColor="error"
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTargetId(null)}
      />
    </Stack>
  );
}
