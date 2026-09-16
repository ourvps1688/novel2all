/* eslint-disable react-refresh/only-export-components */
/**
 * React 入口：挂载根组件、注入 Provider、初始化 React Query
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { lightTheme, darkTheme } from './theme';
import { useThemeStore } from './store/themeStore';
import { AuthProvider } from './auth/AuthProvider';
import { SnackbarProvider } from './components/common/SnackbarProvider';
import { ErrorBoundary } from './components/common/ErrorBoundary';

// React Query 客户端（全局单例）
// 配置策略：
//  - 30s 内重复请求不重发（staleTime）
//  - 失败重试 1 次（避免双击 + 网络抖动）
//  - 后端鉴权失败（401）不重试
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error) => {
        // 401/403/404/422 不重试
        const status = (error as { status?: number })?.status;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});

// 监听主题 store 切换
function ThemedApp() {
  const mode = useThemeStore((s) => s.mode);
  const theme = mode === 'dark' ? darkTheme : lightTheme;

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <AuthProvider>
              <SnackbarProvider>
                <App />
              </SnackbarProvider>
            </AuthProvider>
          </BrowserRouter>
          {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
        </QueryClientProvider>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemedApp />
  </React.StrictMode>,
);
