// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsPage from './page';
import type { Credential, Meta, PlanPrice, Provider, User } from '@/lib/api';

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
  plan: 'free',
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

const plans: PlanPrice[] = [
  { plan: 'free', monthly_ai_units: 100, monthly_price_cents: 0 },
  { plan: 'student', monthly_ai_units: 350, monthly_price_cents: 2990 },
  { plan: 'pro', monthly_ai_units: 700, monthly_price_cents: 5990 },
  { plan: 'max', monthly_ai_units: 1200, monthly_price_cents: 9990 },
];

const { deleteCredential, checkout, billingPortal } = vi.hoisted(() => ({
  deleteCredential: vi.fn(),
  checkout: vi.fn(),
  billingPortal: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      providers: vi.fn(),
      credentials: vi.fn(),
      me: vi.fn(),
      meta: vi.fn(),
      plans: vi.fn(),
      addCredential: vi.fn(),
      deleteCredential,
      deleteAccount: vi.fn(),
      checkout,
      billingPortal,
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
  vi.mocked(api.plans).mockReset();
  deleteCredential.mockReset();
  checkout.mockReset();
  billingPortal.mockReset();
});

async function renderLoaded(account_ = account) {
  vi.mocked(api.providers).mockResolvedValue([provider]);
  vi.mocked(api.credentials).mockResolvedValue([credential]);
  vi.mocked(api.me).mockResolvedValue(account_);
  vi.mocked(api.meta).mockResolvedValue(meta);
  vi.mocked(api.plans).mockResolvedValue(plans);

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

describe('SettingsPage billing', () => {
  it('lists the paid plans and does not offer to subscribe to the current one', async () => {
    await renderLoaded();

    expect(screen.getByText('Pro')).toBeInTheDocument();
    expect(screen.getByText('Max')).toBeInTheDocument();
    // Free is the account's current plan -- shown as a label, not a plan
    // someone can "subscribe" to, and never rendered as a purchasable row
    // (there is nothing to check out for a plan that costs nothing).
    expect(screen.queryByText('R$0,00')).not.toBeInTheDocument();
  });

  it('redirects to the returned Stripe URL when checkout starts', async () => {
    checkout.mockResolvedValue({ url: 'https://checkout.stripe.com/fake' });
    const user = userEvent.setup();
    const original = window.location;
    // @ts-expect-error -- jsdom's location is not directly assignable; this
    // is the standard escape hatch to observe a real `href =` redirect.
    delete window.location;
    window.location = { ...original, href: '' } as Location;
    try {
      await renderLoaded();

      await user.click(screen.getAllByRole('button', { name: 'Subscribe' })[0]);

      await waitFor(() => {
        expect(window.location.href).toBe('https://checkout.stripe.com/fake');
      });
      // The first "Subscribe" button in DOM order is Student -- the fixture
      // plans list is [free, student, pro, max] and free is filtered out.
      expect(checkout).toHaveBeenCalledWith('student');
    } finally {
      window.location = original;
    }
  });

  it('shows a real error and stays on the page when checkout fails', async () => {
    checkout.mockRejectedValue(new Error('Billing is not configured on this deployment.'));
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getAllByRole('button', { name: 'Subscribe' })[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Billing is not configured on this deployment.');
  });

  it('offers to manage the subscription only once the account is on a paid plan', async () => {
    await renderLoaded({ ...account, plan: 'pro' });

    expect(screen.getByRole('button', { name: 'Manage subscription' })).toBeInTheDocument();
    // The account's own current plan reads as a label, not a purchasable
    // row -- other paid plans (upgrade/downgrade) still offer to check out.
    expect(screen.getByText('Your plan')).toBeInTheDocument();
  });

  it('never offers "manage subscription" for the free plan', async () => {
    await renderLoaded();

    expect(
      screen.queryByRole('button', { name: 'Manage subscription' }),
    ).not.toBeInTheDocument();
  });
});
