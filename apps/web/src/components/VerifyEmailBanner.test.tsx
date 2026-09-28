// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { VerifyEmailBanner } from '@/components/VerifyEmailBanner';
import { ApiError } from '@/lib/api';
import { en } from '@/locales/en';

const { me, meta, resendVerification } = vi.hoisted(() => ({
  me: vi.fn(),
  meta: vi.fn(),
  resendVerification: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, me, meta, resendVerification } };
});

function account(verified: boolean) {
  return {
    id: 'u1',
    email: 'ana@example.com',
    display_name: 'Ana',
    settings: {},
    plan: 'free',
    email_verified: verified,
    created_at: '2026-09-28T00:00:00Z',
  };
}

beforeEach(() => {
  window.sessionStorage.clear();
  meta.mockResolvedValue({ email_verification: true });
});

afterEach(() => {
  me.mockReset();
  resendVerification.mockReset();
});

describe('VerifyEmailBanner', () => {
  it('asks for nothing while mail cannot reach the learner', async () => {
    meta.mockResolvedValue({ email_verification: false });
    me.mockResolvedValue(account(false));
    const { container } = render(<VerifyEmailBanner />);

    await waitFor(() => expect(meta).toHaveBeenCalled());
    expect(me).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows one line for an account that has not confirmed its email', async () => {
    me.mockResolvedValue(account(false));
    render(<VerifyEmailBanner />);

    await screen.findByText(en.emailVerification.bannerTitle);
    expect(screen.getByRole('button', { name: en.emailVerification.resend })).toBeInTheDocument();
  });

  it('stays silent for a confirmed account, and does not ask again this session', async () => {
    me.mockResolvedValue(account(true));
    const { unmount } = render(<VerifyEmailBanner />);

    await waitFor(() => expect(me).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(en.emailVerification.bannerTitle)).not.toBeInTheDocument();

    unmount();
    render(<VerifyEmailBanner />);
    await waitFor(() => expect(window.sessionStorage.getItem('noema.verify-email.confirmed')).toBe('1'));
    expect(me).toHaveBeenCalledTimes(1);
  });

  it('stays silent when the API cannot say who is asking', async () => {
    me.mockRejectedValue(
      new ApiError({ type: 'about:blank', status: 401, title: 'Unauthorized', detail: '' }),
    );
    render(<VerifyEmailBanner />);

    await waitFor(() => expect(me).toHaveBeenCalled());
    expect(screen.queryByText(en.emailVerification.bannerTitle)).not.toBeInTheDocument();
  });

  it('closes for the session', async () => {
    me.mockResolvedValue(account(false));
    const user = userEvent.setup();
    const { unmount } = render(<VerifyEmailBanner />);
    await screen.findByText(en.emailVerification.bannerTitle);

    await user.click(screen.getByRole('button', { name: en.emailVerification.dismiss }));

    expect(screen.queryByText(en.emailVerification.bannerTitle)).not.toBeInTheDocument();
    unmount();
    render(<VerifyEmailBanner />);
    expect(screen.queryByText(en.emailVerification.bannerTitle)).not.toBeInTheDocument();
    expect(me).toHaveBeenCalledTimes(1);
  });

  it('resends and says so', async () => {
    me.mockResolvedValue(account(false));
    resendVerification.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<VerifyEmailBanner />);
    await screen.findByText(en.emailVerification.bannerTitle);

    await user.click(screen.getByRole('button', { name: en.emailVerification.resend }));

    await screen.findByText(en.emailVerification.sent);
    expect(resendVerification).toHaveBeenCalledTimes(1);
  });

  it('tells the learner when one went out recently', async () => {
    me.mockResolvedValue(account(false));
    resendVerification.mockRejectedValue(
      new ApiError({ type: 'about:blank', status: 429, title: 'Too many', detail: '' }),
    );
    const user = userEvent.setup();
    render(<VerifyEmailBanner />);
    await screen.findByText(en.emailVerification.bannerTitle);

    await user.click(screen.getByRole('button', { name: en.emailVerification.resend }));

    await screen.findByText(en.emailVerification.tooSoon);
  });
});
