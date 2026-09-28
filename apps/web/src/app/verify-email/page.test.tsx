// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import VerifyEmailPage from './page';
import { ApiError } from '@/lib/api';
import { en } from '@/locales/en';

let params = new URLSearchParams({ token: 'a-real-token' });
vi.mock('next/navigation', () => ({
  useSearchParams: () => params,
}));

const { verifyEmail, resendVerification } = vi.hoisted(() => ({
  verifyEmail: vi.fn(),
  resendVerification: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, verifyEmail, resendVerification } };
});

afterEach(() => {
  verifyEmail.mockReset();
  resendVerification.mockReset();
  params = new URLSearchParams({ token: 'a-real-token' });
});

function problem(status: number, type = 'about:blank') {
  return new ApiError({ type, status, title: 'Problem', detail: '' });
}

describe('VerifyEmailPage', () => {
  it('sends the token from the URL once and confirms', async () => {
    verifyEmail.mockResolvedValue(undefined);
    render(<VerifyEmailPage />);

    await screen.findByText(en.emailVerification.successTitle);
    expect(verifyEmail).toHaveBeenCalledTimes(1);
    expect(verifyEmail).toHaveBeenCalledWith('a-real-token');
    expect(screen.getByRole('link', { name: en.emailVerification.continue })).toHaveAttribute(
      'href',
      '/today',
    );
  });

  it('says expired when the API does, with a way to get a new link', async () => {
    verifyEmail.mockRejectedValue(problem(401, 'https://noema.dev/errors/link-expired'));
    render(<VerifyEmailPage />);

    await screen.findByText(en.emailVerification.expiredTitle);
    expect(screen.getByRole('button', { name: en.emailVerification.requestNew })).toBeInTheDocument();
  });

  it('says invalid for a used or unknown token', async () => {
    verifyEmail.mockRejectedValue(problem(401));
    render(<VerifyEmailPage />);

    await screen.findByText(en.emailVerification.invalidTitle);
  });

  it('is invalid without a token, and asks the API nothing', () => {
    params = new URLSearchParams();
    render(<VerifyEmailPage />);

    expect(screen.getByText(en.emailVerification.invalidTitle)).toBeInTheDocument();
    expect(verifyEmail).not.toHaveBeenCalled();
  });

  it('resends for a signed-in learner', async () => {
    verifyEmail.mockRejectedValue(problem(401, 'https://noema.dev/errors/link-expired'));
    resendVerification.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<VerifyEmailPage />);
    await screen.findByText(en.emailVerification.expiredTitle);

    await user.click(screen.getByRole('button', { name: en.emailVerification.requestNew }));

    await screen.findByText(en.emailVerification.sent);
  });

  it('points a signed-out learner at sign in instead', async () => {
    verifyEmail.mockRejectedValue(problem(401));
    resendVerification.mockRejectedValue(problem(401));
    const user = userEvent.setup();
    render(<VerifyEmailPage />);
    await screen.findByText(en.emailVerification.invalidTitle);

    await user.click(screen.getByRole('button', { name: en.emailVerification.requestNew }));

    await screen.findByText(en.emailVerification.signInFirst);
    expect(screen.getByRole('link', { name: en.emailVerification.signIn })).toHaveAttribute(
      'href',
      '/login',
    );
  });
});
