// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import LandingPage from './page';
import type { Meta, PlanPrice, User } from '@/lib/api';

vi.mock('@/components/LanguageSwitcher', () => ({
  LanguageSwitcher: () => null,
}));

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

const { metaFn, plansFn, meFn } = vi.hoisted(() => ({
  metaFn: vi.fn(),
  plansFn: vi.fn(),
  meFn: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: { meta: metaFn, plans: plansFn, me: meFn },
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

// Every pricing test below is signed-out (the common case) unless it says
// otherwise -- `me()` rejecting is what a visitor with no session cookie
// actually gets back from `/auth/me`.
meFn.mockRejectedValue(new Error('not signed in'));

describe('LandingPage pricing', () => {
  it('renders every real plan fetched from the API, priced in BRL', async () => {
    metaFn.mockResolvedValue(meta);
    plansFn.mockResolvedValue(plans);

    render(<LandingPage />);

    await waitFor(() => {
      expect(screen.getByText('Pro')).toBeInTheDocument();
    });
    expect(screen.getByText('Max')).toBeInTheDocument();
    // R$59,90 formatted by Intl.NumberFormat -- assert the digits/currency
    // landed, not an exact locale string that could drift across runners.
    expect(screen.getByText(/59[,.]90/)).toBeInTheDocument();
  });

  it('never shows pricing for a local-mode deployment -- there is no account to bill', async () => {
    metaFn.mockResolvedValue({ ...meta, local: true });
    plansFn.mockResolvedValue(plans);

    render(<LandingPage />);

    await waitFor(() => expect(plansFn).toHaveBeenCalled());
    expect(screen.queryByText('Pro')).not.toBeInTheDocument();
  });

  it('shows a real error instead of silently hiding pricing when the fetch fails', async () => {
    metaFn.mockResolvedValue(meta);
    plansFn.mockRejectedValue(new Error('network down'));

    render(<LandingPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load pricing right now.');
  });
});

describe('LandingPage auth-aware CTA', () => {
  const user: User = {
    id: 'u1',
    email: 'learner@example.com',
    display_name: 'Learner',
    plan: 'free',
    settings: {},
    created_at: '2026-01-01T00:00:00Z',
  };

  it('offers to sign in, not "continue learning", before the session check resolves or for a signed-out visitor', async () => {
    metaFn.mockResolvedValue(meta);
    plansFn.mockResolvedValue(plans);
    meFn.mockRejectedValue(new Error('not signed in'));

    render(<LandingPage />);

    await waitFor(() => expect(meFn).toHaveBeenCalled());
    const ctas = screen.getAllByRole('link', { name: 'Start learning' });
    expect(ctas.length).toBeGreaterThan(0);
    for (const cta of ctas) {
      expect(cta).toHaveAttribute('href', '/login');
    }
  });

  it('switches every primary CTA to "Continue learning" -> /today once a real session is confirmed', async () => {
    metaFn.mockResolvedValue(meta);
    plansFn.mockResolvedValue(plans);
    meFn.mockResolvedValue(user);

    render(<LandingPage />);

    const ctas = await screen.findAllByRole('link', { name: 'Continue learning' });
    expect(ctas.length).toBeGreaterThan(0);
    for (const cta of ctas) {
      expect(cta).toHaveAttribute('href', '/today');
    }
    expect(screen.queryByRole('link', { name: 'Start learning' })).not.toBeInTheDocument();
  });
});

describe('LandingPage Mino placeholder', () => {
  it('renders the hero placeholder as purely decorative', () => {
    metaFn.mockResolvedValue(meta);
    plansFn.mockResolvedValue(plans);

    render(<LandingPage />);

    const mino = document.querySelector('img[aria-hidden="true"]');
    expect(mino).not.toBeNull();
    expect(mino).toHaveAttribute('alt', '');
    expect(mino).toHaveAttribute('src', '/brand/mino/mino-hero.svg');
  });
});
