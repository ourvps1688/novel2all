/**
 * 根组件：路由表 + 懒加载 + 守卫
 */

import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';

import { ProtectedRoute } from './auth/ProtectedRoute';
import { AdminGuard } from './auth/AdminGuard';
import { AppShell } from './components/layout/AppShell';

// 路由级懒加载：拆 chunk 减少首屏体积
const LoginPage = lazy(() => import('./auth/LoginPage').then((m) => ({ default: m.LoginPage })));
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const WritePage = lazy(() => import('./pages/WritePage').then((m) => ({ default: m.WritePage })));
const ChapterListPage = lazy(() =>
  import('./pages/ChapterListPage').then((m) => ({ default: m.ChapterListPage })),
);
const SkillsPage = lazy(() => import('./pages/SkillsPage').then((m) => ({ default: m.SkillsPage })));
const SkillDetailPage = lazy(() =>
  import('./pages/SkillDetailPage').then((m) => ({ default: m.SkillDetailPage })),
);
const ReviewQueuePage = lazy(() =>
  import('./pages/ReviewQueuePage').then((m) => ({ default: m.ReviewQueuePage })),
);
const ExportPage = lazy(() =>
  import('./pages/ExportPage').then((m) => ({ default: m.ExportPage })),
);
const AdminLayout = lazy(() =>
  import('./layouts/AdminLayout').then((m) => ({ default: m.AdminLayout })),
);
const AdminUsersPage = lazy(() =>
  import('./pages/admin/AdminUsersPage').then((m) => ({ default: m.AdminUsersPage })),
);
const AdminAuditPage = lazy(() =>
  import('./pages/admin/AdminAuditPage').then((m) => ({ default: m.AdminAuditPage })),
);
const AdminProjectsPage = lazy(() =>
  import('./pages/admin/AdminProjectsPage').then((m) => ({ default: m.AdminProjectsPage })),
);
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);
const CoverPage = lazy(() => import('./pages/CoverPage').then((m) => ({ default: m.CoverPage })));
const NotFoundPage = lazy(() =>
  import('./pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);

// Suspense fallback（路由级 loading）
function RouteLoader() {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
      }}
    >
      <CircularProgress />
    </Box>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteLoader />}>
      <Routes>
        {/* 登录页（公开） */}
        <Route path="/login" element={<LoginPage />} />

        {/* 受保护路由：必须登录 */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="/write" element={<WritePage />} />
          <Route path="/write/:chapter" element={<WritePage />} />
          <Route path="/chapters" element={<ChapterListPage />} />
          <Route path="/skills" element={<SkillsPage />} />
          <Route path="/skills/:name" element={<SkillDetailPage />} />
          <Route path="/review" element={<ReviewQueuePage />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/cover" element={<CoverPage />} />

          {/* Admin 专属（嵌套路由：/admin → /admin/users） */}
          <Route
            path="/admin"
            element={
              <AdminGuard>
                <Navigate to="/admin/users" replace />
              </AdminGuard>
            }
          />
          <Route
            path="/admin/*"
            element={
              <AdminGuard>
                <AdminLayout title="管理员后台">
                  <Routes>
                    <Route path="users" element={<AdminUsersPage />} />
                    <Route path="audit" element={<AdminAuditPage />} />
                    <Route path="projects" element={<AdminProjectsPage />} />
                    <Route path="*" element={<Navigate to="users" replace />} />
                  </Routes>
                </AdminLayout>
              </AdminGuard>
            }
          />
        </Route>

        {/* 未匹配：404 */}
        <Route path="/404" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </Suspense>
  );
}
