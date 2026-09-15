/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// https://vitejs.dev/config/
// Vite 配置：React + 路径别名 + /api 反向代理 + 测试集成
export default defineConfig(({ mode }) => {
  // 加载 .env.local / .env.[mode]（不暴露到 client；只在 vite.config.ts 里用）
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_API_PROXY_TARGET || 'http://192.168.3.106:8000';

  return {
    plugins: [react()],

    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
        '@api': path.resolve(__dirname, './src/api'),
        '@auth': path.resolve(__dirname, './src/auth'),
        '@components': path.resolve(__dirname, './src/components'),
        '@pages': path.resolve(__dirname, './src/pages'),
        '@hooks': path.resolve(__dirname, './src/hooks'),
        '@store': path.resolve(__dirname, './src/store'),
        '@utils': path.resolve(__dirname, './src/utils'),
        '@types': path.resolve(__dirname, './src/types'),
      },
    },

    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: false,
      // 开发代理：所有 /api/* 请求转发到后端 FastAPI
      // 浏览器仍发同源请求（cookie SameSite=Strict 才能正常携带）
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
          // SSE 必须禁用缓冲
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('Connection', 'keep-alive');
            });
          },
        },
        '/metrics': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },

    build: {
      target: 'es2020',
      outDir: 'dist',
      sourcemap: mode !== 'production',
      rollupOptions: {
        output: {
          manualChunks: {
            // 拆 vendor 提升缓存命中率
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-mui': ['@mui/material', '@mui/icons-material'],
            'vendor-tiptap': ['@tiptap/react', '@tiptap/starter-kit', '@tiptap/pm'],
            'vendor-query': ['@tanstack/react-query'],
            'vendor-utils': ['axios', 'zod', 'uuid', 'zustand', 'recharts'],
          },
        },
      },
      chunkSizeWarningLimit: 1500,
    },

    // Vitest 配置（与 Vite 共用配置）
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./tests/setup.ts'],
      css: false,
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
        exclude: ['node_modules/', 'dist/', 'tests/', '**/*.d.ts'],
      },
    },
  };
});
