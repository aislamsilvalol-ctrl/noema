// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ResetPasswordPage from './page';
import { ApiError } from '@/lib/api';

let params = new URLSearchParams({ token: 'a-real-token' });
vi.mock('next/navigation', () => ({
  useSearchParams: () => params,
}));

const { resetPassword } = vi.hoisted(() => ({ resetPassword: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, resetPassword } };
});

afterEach(() => {
  resetPassword.mockReset();
  params = new URLSearchParams({ token: 'a-real-token' });
});

describe('ResetPasswordPage', () => {
  it('shows the invalid-link state immediately when the URL has no token', () => {
    params = new URLSearchParams();
    render(<ResetPasswordPage />);
    expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument();
  });

  it('submits the token from the URL alongside the new password and shows success', async () => {
    resetPassword.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'a-fresh-strong-password');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await screen.findByText(/password has been changed/i);
    expect(resetPassword).toHaveBeenCalledWith('a-real-token', 'a-fresh-strong-password');
  });

  it('falls back to the invalid-link state when the token is expired or already used', async () => {
    resetPassword.mockRejectedValue(
      new ApiError({ type: 'about:blank', status: 401, title: 'Unauthorized', detail: 'Expired.' }),
    );
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'a-fresh-strong-password');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await screen.findByText(/invalid or has expired/i);
  });

  it('surfaces a non-auth error and leaves the form usable', async () => {
    resetPassword.mockRejectedValue(
      new ApiError({ type: 'about:blank', status: 500, title: 'Server error', detail: 'Something broke.' }),
    );
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'a-fresh-strong-password');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await screen.findByText('Something broke.');
    expect(screen.getByRole('button', { name: /reset password/i })).toBeEnabled();
  });
});
