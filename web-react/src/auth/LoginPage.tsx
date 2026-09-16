/**
 * 登录页：居中卡片 + 表单 + react-hook-form + zod 校验
 *
 * 设计要点：
 *  - 已登录用户访问 /login → 重定向到 /（由 ProtectedRoute 兜底；这里也加判断）
 *  - 失败不暴露"用户不存在"（后端 V1.0.1 B7 已对齐时序）
 *  - 提交按钮带 loading（LoadingButton）
 *  - 默认 username: 'admin'（首次部署方便）
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Box,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
  Alert,
  Link,
  Divider,
} from '@mui/material';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';

import { useAuth } from './useAuth';
import { LoadingButton } from '../components/common/LoadingButton';

const LoginSchema = z.object({
  username: z
    .string()
    .min(1, '用户名不能为空')
    .max(64, '用户名过长')
    .regex(/^[a-zA-Z0-9_-]+$/, '用户名仅允许字母/数字/下划线/连字符'),
  password: z.string().min(1, '密码不能为空').max(128, '密码过长'),
});

type LoginFormData = z.infer<typeof LoginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const { login, isLoggingIn, isAuthenticated, loginError } = useAuth();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(LoginSchema),
    defaultValues: { username: '', password: '' },
  });

  // 已登录直接跳走
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const onSubmit = handleSubmit(async (data) => {
    await login(data.username, data.password);
  });

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: (t) =>
          t.palette.mode === 'light'
            ? 'linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%)'
            : 'linear-gradient(135deg, #0f1115 0%, #1a1d24 100%)',
        p: 2,
      }}
    >
      <Card sx={{ maxWidth: 420, width: '100%' }} variant="outlined">
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <Box
              sx={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                bgcolor: 'primary.main',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
              }}
            >
              <LockOutlinedIcon fontSize="large" />
            </Box>

            <Stack alignItems="center" spacing={0.5}>
              <Typography variant="h4" component="h1">
                novel2all
              </Typography>
              <Typography variant="body2" color="text.secondary">
                长篇一致性创作平台 · V1.5
              </Typography>
            </Stack>

            {loginError instanceof Error && (
              <Alert severity="error" sx={{ width: '100%' }}>
                {loginError.message}
              </Alert>
            )}

            <Box component="form" onSubmit={onSubmit} sx={{ width: '100%' }} noValidate>
              <Stack spacing={2}>
                <TextField
                  label="用户名"
                  autoComplete="username"
                  autoFocus
                  fullWidth
                  required
                  {...register('username')}
                  error={!!errors.username}
                  helperText={errors.username?.message ?? ' '}
                />
                <TextField
                  label="密码"
                  type="password"
                  autoComplete="current-password"
                  fullWidth
                  required
                  {...register('password')}
                  error={!!errors.password}
                  helperText={errors.password?.message ?? ' '}
                />
                <LoadingButton
                  type="submit"
                  variant="contained"
                  size="large"
                  loading={isLoggingIn}
                  fullWidth
                >
                  登录
                </LoadingButton>
              </Stack>
            </Box>

            <Divider flexItem />

            <Stack alignItems="center" spacing={0.5}>
              <Typography variant="caption" color="text.secondary">
                首次部署默认账号 <strong>admin / admin</strong>
              </Typography>
              <Typography variant="caption" color="text.secondary">
                部署问题见{' '}
                <Link href="https://github.com/ourvps1688/novel2all/blob/main/docs/DEPLOY.md">
                  部署文档
                </Link>
              </Typography>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
