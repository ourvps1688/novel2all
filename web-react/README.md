# novel2all Web-React V1.5

Vite + React 18 + TypeScript + MUI 5 SPA，替换原 Jinja2 + HTMX + Alpine.js 前端。

## 快速开始

```bash
# 1. 安装依赖（要求 Node >= 18.18, pnpm >= 9）
pnpm install

# 2. 配置后端地址（可选；默认 http://192.168.3.106:8000）
echo "VITE_API_PROXY_TARGET=http://your-backend:8000" > .env.local

# 3. 启动 dev server
pnpm dev
# → http://localhost:5173  （/api/* 代理到后端）

# 4. 构建生产
pnpm build  # → dist/
pnpm preview  # 本地预览生产构建

# 5. 代码质量
pnpm typecheck  # tsc --noEmit
pnpm lint       # ESLint
pnpm format     # Prettier
pnpm test       # Vitest
```

## 项目结构

```
src/
├── api/           # axios + React Query hooks + Zod schemas
├── auth/          # AuthProvider + LoginPage + Guards
├── pages/         # 顶层页面
├── components/    # 可复用组件（layout/dashboard/write/...）
├── hooks/         # 自定义 hooks（useSSE/useSnackbar/...）
├── store/         # zustand stores（auth/theme/snackbar）
├── utils/         # 工具函数（errors/format/idem）
├── types/         # UI 层类型
├── theme.ts       # MUI 主题
├── App.tsx        # 路由根
└── main.tsx       # 入口
```

## 后端依赖

FastAPI V1.0.2（已部署在 192.168.3.106:8000），所有 API 端点见
`/api/openapi.json`。前端不内置 mock；开发依赖 MSW 仅用于单元测试。

## 部署

生产环境由 FastAPI 同时托管静态资源（详见 `docs/web-react-v1.5-design.md` 第 10 节）。

## 关键设计决策

1. **httpOnly cookie + /api/auth/me**：防 XSS 偷 token；CSRF 用 SameSite=Strict
2. **React Query cache**：server-state 主流方案；UI state 用 useState/zustand
3. **Tiptap editor**：中文友好、可扩展
4. **MUI 5**：组件齐全、主题成熟
5. **React Router 6 SPA**：不需要 SEO；SPA UX 更好
6. **路由懒加载**：拆 chunk、首屏快

## License

MIT（同 novel2all 主项目）
