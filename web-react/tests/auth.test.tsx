/**
 * Auth flow 测试
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { LoginPage } from '../src/auth/LoginPage';
import { AuthProvider } from '../src/auth/AuthProvider';

// Mock axios: 注意 apiClient.get 返回 AxiosResponse { data: T } 形式
vi.mock('../src/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    postForm: vi.fn(),
    delete: vi.fn(),
  },
  get: vi.fn(),
  post: vi.fn(),
  postForm: vi.fn(),
  del: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

function renderWithProviders(ui: React.ReactNode, { initialEntries = ['/login'] } = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LoginPage', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const client = await import('../src/api/client');
    const ac = client.apiClient as unknown as { get: ReturnType<typeof vi.fn> };
    // 透传: 导出 get() → 调 apiClient.get (返回 AxiosResponse { data })
    (client.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => ac.get(url));
    // 默认: /api/auth/me 返回未登录 (AxiosResponse 形态)
    ac.get.mockImplementation((url: string) => {
      if (url.includes('/api/auth/me')) {
        return Promise.resolve({ data: { user: null, authenticated: false } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders username + password fields and submit button', async () => {
    renderWithProviders(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/用户名/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/密码/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /登录/ })).toBeInTheDocument();
  });

  it('shows validation error when fields are empty', async () => {
    renderWithProviders(<LoginPage />);
    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /登录/ })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /登录/ }));

    await waitFor(() => {
      expect(screen.getByText(/用户名不能为空/)).toBeInTheDocument();
      expect(screen.getByText(/密码不能为空/)).toBeInTheDocument();
    });
  });
});
