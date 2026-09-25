// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import LoginPage from './page';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const mocks = vi.hoisted(() => ({ login: vi.fn(), answerMfa: vi.fn(), meta: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: { ...actual.api, login: mocks.login, answerMfa: mocks.answerMfa, meta: mocks.meta },
  };
});

afterEach(() => {
  for (const fn of Object.values(mocks)) fn.mockReset();
  push.mockReset();
});

async function signIn() {
  const user = userEvent.setup();
  mocks.meta.mockResolvedValue({ allow_signups: true });
  render(<LoginPage />);
  await user.type(screen.getByLabelText(/email/i), 'ana@example.com');
  await user.type(screen.getByLabelText(/^password/i), 'correct-horse-battery');
  await user.click(screen.getByRole('button', { name: /sign in/i }));
  return user;
}

describe('LoginPage', () => {
  it('goes straight in when the account has no second step', async () => {
    mocks.login.mockResolvedValue({ user: {}, csrf_token: 'c' });
    await signIn();
    expect(push).toHaveBeenCalledWith('/today');
  });

  it('asks for a code when the password was right but a second step is owed', async () => {
    mocks.login.mockResolvedValue({ mfa_required: true, challenge: 'ch-1' });
    mocks.answerMfa.mockResolvedValue({ user: {}, csrf_token: 'c' });
    const user = await signIn();

    expect(push).not.toHaveBeenCalled();
    await user.type(await screen.findByLabelText(/code/i), '123456');
    await user.click(screen.getByRole('button', { name: /verify/i }));

    expect(mocks.answerMfa).toHaveBeenCalledWith('ch-1', '123456');
    expect(push).toHaveBeenCalledWith('/today');
  });
});
