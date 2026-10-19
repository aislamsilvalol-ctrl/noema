// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { PlanPrice } from '@/lib/api';

const plans: PlanPrice[] = [
  {
    plan: 'free',
    monthly_price_cents: 0,
    annual_price_cents: null,
    full_lessons: 2,
    weekly_lessons: 3,
    monthly_documents: 3,
    max_journeys: 1,
    monthly_ai_units: 220,
  },
  {
    plan: 'plus',
    monthly_price_cents: 3490,
    annual_price_cents: 34900,
    full_lessons: 40,
    weekly_lessons: null,
    monthly_documents: 30,
    max_journeys: null,
    monthly_ai_units: 3600,
  },
  {
    plan: 'pro',
    monthly_price_cents: 6990,
    annual_price_cents: 69900,
    full_lessons: 128,
    weekly_lessons: null,
    monthly_documents: 100,
    max_journeys: null,
    monthly_ai_units: 10500,
  },
];

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { plans: vi.fn(async () => plans) } };
});

import PricingPage from './page';

describe('PricingPage', () => {
  it('sells lessons and modes, never units, with Plus recommended', async () => {
    render(<PricingPage />);

    await screen.findByText('About 40 full-mode lessons a month');
    expect(screen.getByText('About 125 full-mode lessons a month')).toBeInTheDocument();
    expect(screen.getByText('3 lessons a week')).toBeInTheDocument();
    expect(screen.getByText('1 learning path at a time')).toBeInTheDocument();
    expect(screen.getByText('Recommended')).toBeInTheDocument();
    expect(screen.queryByText(/units?/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Get Plus' })).toHaveAttribute(
      'href',
      '/settings?plan=plus&interval=month#billing',
    );
  });

  it('shows the yearly price and what it comes to a month', async () => {
    const user = userEvent.setup();
    render(<PricingPage />);
    await screen.findByText('Recommended');

    await user.click(screen.getByRole('button', { name: /yearly/i }));

    expect(screen.getByText('R$349')).toBeInTheDocument();
    expect(screen.getByText('R$29.08/month billed yearly')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Get Plus' })).toHaveAttribute(
      'href',
      '/settings?plan=plus&interval=year#billing',
    );
  });
});
