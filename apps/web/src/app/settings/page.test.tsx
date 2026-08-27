// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsPage from './page';
import type { Credential, Meta, Provider, User } from '@/lib/api';

// A fresh object from useRouter() on every render would give this page's
// `load` useCallback a new identity each time, retriggering its mount effect
// in a loop -- Next's real useRouter() is referentially stable, so the mock
// has to be too (see notebooks/[id]/page.test.tsx for where this bit before).
const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/LanguageSwitcher', () => ({
  LanguageSwitcher: () => null,
}));

const provider: Provider = {
  name: 'anthropic',
  configured: true,
  is_default: true,
  capabilities: {},
};

const credential: Credential = {
  id: 'cred-1',
  provider: 'anthropic',
  label: 'default',
  last4: '9f2a',
  verification_error: null,
  last_used_at: null,
  last_verified_at: null,
  created_at: '2026-01-01T00:00:00Z',
};

const account: User = {
  id: 'user-1',
  email: 'ada@example.com',
  display_name: 'Ada',
  settings: {},
  created_at: '2026-01-01T00:00:00Z',
};

const meta: Meta = {
  revision: 'abc123',
  local: false,
  default_provider: 'anthropic',
  allow_signups: true,
  embedding_model: 'text-embedding-3-small',
  mode: 'hosted',
  version: '0.1.0',
};

const { deleteCredential } = vi.hoisted(() => ({ deleteCredential: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      providers: vi.fn(),
      credentials: vi.fn(),
      me: vi.fn(),
      meta: vi.fn(),
      addCredential: vi.fn(),
      deleteCredential,
      deleteAccount: vi.fn(),
    },
    downloadExport: vi.fn(),
  };
});

import { api } from '@/lib/api';

afterEach(() => {
  vi.mocked(api.providers).mockReset();
  vi.mocked(api.credentials).mockReset();
  vi.mocked(api.me).mockReset();
  vi.mocked(api.meta).mockReset();
  deleteCredential.mockReset();
});

async function renderLoaded() {
  vi.mocked(api.providers).mockResolvedValue([provider]);
  vi.mocked(api.credentials).mockResolvedValue([credential]);
  vi.mocked(api.me).mockResolvedValue(account);
  vi.mocked(api.meta).mockResolvedValue(meta);

  render(<SettingsPage />);
  await screen.findByText('····9f2a');
}

describe('SettingsPage credential deletion', () => {
  it('removes the credential from the list when deletion succeeds', async () => {
    deleteCredential.mockResolvedValue(undefined);
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(screen.queryByText('····9f2a')).not.toBeInTheDocument();
    });
    expect(deleteCredential).toHaveBeenCalledWith('cred-1');
  });

  it('shows an error and keeps the credential when deletion fails', async () => {
    deleteCredential.mockRejectedValue(new Error('network down'));
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await screen.findByRole('alert');
    expect(screen.getByText('····9f2a')).toBeInTheDocument();
  });
});
