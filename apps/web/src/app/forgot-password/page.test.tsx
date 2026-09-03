// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ForgotPasswordPage from './page';
import { ApiError } from '@/lib/api';

const { forgotPassword } = vi.hoisted(() => ({ forgotPassword: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, forgotPassword } };
});

afterEach(() => {
  forgotPassword.mockReset();
});

describe('ForgotPasswordPage', () => {
  it('shows the same success state regardless of whether the account exists', async () => {
    forgotPassword.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), 'learner@example.com');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await screen.findByText(/check your inbox/i);
    expect(forgotPassword).toHaveBeenCalledWith('learner@example.com');
  });

  it('surfaces an error and leaves the form usable when the request fails', async () => {
    forgotPassword.mockRejectedValue(
      new ApiError({ type: 'about:blank', status: 429, title: 'Too many requests', detail: 'Slow down.' }),
    );
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), 'learner@example.com');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await screen.findByText('Slow down.');
    expect(screen.getByRole('button', { name: /send/i })).toBeEnabled();
  });
});
