/**
 * Auth flow 测试
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { LoginPage } from '../src/auth/LoginPage';
import { AuthProvider } from '../src/auth/AuthProvider';

// Mock axios
vi.mock('../src/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    postForm: vi.fn(),
    delete: vi.fn(),
  },
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
  it('renders username + password fields and submit button', async () => {
    // /api/auth/me 返回未登录
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ user: null, authenticated: false });

    renderWithProviders(<LoginPage />);

    expect(screen.getByLabelText(/用户名/)).toBeInTheDocument();
    expect(screen.getByLabelText(/密码/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /登录/ })).toBeInTheDocument();
  });

  it('shows validation error when fields are empty', async () => {
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ user: null, authenticated: false });

    renderWithProviders(<LoginPage />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /登录/ }));

    await waitFor(() => {
      expect(screen.getByText(/用户名不能为空/)).toBeInTheDocument();
      expect(screen.getByText(/密码不能为空/)).toBeInTheDocument();
    });
  });
});
