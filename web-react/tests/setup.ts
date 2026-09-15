/**
 * Vitest 测试 setup
 *
 * - 引入 @testing-library/jest-dom 扩展 expect
 * - 清理 React 状态（afterEach unmount）
 * - 启用 MSW server（如启用）
 */

import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

// 可选：MSW server（需要后续在 mockServiceWorker.js 配套）
// import { server } from './mocks/server';
// beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
// afterEach(() => server.resetHandlers());
// afterAll(() => server.close());
