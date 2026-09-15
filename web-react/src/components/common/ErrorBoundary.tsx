/**
 * 全局 ErrorBoundary：捕获 React 渲染错误并展示降级 UI
 *
 * 设计：
 *  - 捕获后展示卡片 + 重置按钮（清空 query cache + navigate('/')）
 *  - 不向 console.error 重复写（React 18 会自动写）
 *  - 生产环境可上报到 Sentry 等（TODO）
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Box, Button, Card, CardContent, Stack, Typography, Alert } from '@mui/material';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  componentStack: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { hasError: false, error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // 生产可上报：Sentry.captureException(error, { extra: info });
    this.setState({ componentStack: info.componentStack ?? null });
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null, componentStack: null });
    // 强制刷新页面（最安全）
    window.location.href = '/';
  };

  override render(): ReactNode {
    if (!this.state.hasError) return this.props.children;

    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          p: 3,
          bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.50' : 'background.default'),
        }}
      >
        <Card sx={{ maxWidth: 560, width: '100%' }}>
          <CardContent>
            <Stack spacing={2} alignItems="center">
              <ErrorOutlineIcon sx={{ fontSize: 56 }} color="error" />
              <Typography variant="h5">页面出错了</Typography>
              <Alert severity="error" sx={{ width: '100%' }}>
                <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                  {this.state.error?.message ?? '未知错误'}
                </Typography>
              </Alert>
              <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'center' }}>
                请尝试刷新页面。如反复出现，请截图发给开发者并附上浏览器控制台日志。
              </Typography>
              <Button variant="contained" onClick={this.handleReset}>
                返回首页
              </Button>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    );
  }
}
