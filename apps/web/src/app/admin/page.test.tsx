// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import AdminPage from './page';
import { ApiError, type AdminIntelligence, type SimulatorOut } from '@/lib/api';

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const { adminIntelligence, adminSimulate } = vi.hoisted(() => ({
  adminIntelligence: vi.fn(),
  adminSimulate: vi.fn(),
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: { adminIntelligence, adminSimulate },
  };
});

const snapshot: AdminIntelligence = {
  requests_today: 12,
  tokens_today: 3400,
  spend_today_cents: 150.5,
  spend_this_month_cents: 4200.0,
  error_rate: 0.05,
  tier_mix: { economy: 0.7, standard: 0.3 },
  top_users: [{ user_id: 'u1', email: 'alice@example.com', spend_cents: 900.0 }],
  not_yet_tracked: ['cache_hit_rate', 'rag_calls', 'latency_p50_ms'],
};

const simulated: SimulatorOut = {
  ai_cost_per_user_cents: 10,
  ai_cost_total_cents: 10000,
  payment_fees_cents: 5000,
  gross_revenue_cents: 100000,
  net_revenue_cents: 85000,
  gross_margin_percent: 85,
  estimated_mrr_cents: 100000,
};

describe('AdminPage', () => {
  it('shows an access-denied state on a 403, not a generic error', async () => {
    adminIntelligence.mockRejectedValue(
      new ApiError({ type: 'forbidden', title: 'Forbidden', status: 403, detail: 'no' }),
    );

    render(<AdminPage />);

    expect(await screen.findByText('Admin access required.')).toBeInTheDocument();
  });

  it('renders real intelligence data once loaded', async () => {
    adminIntelligence.mockResolvedValue(snapshot);

    render(<AdminPage />);

    expect(await screen.findByText('12')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText(/cache_hit_rate/)).toBeInTheDocument();
  });

  it('runs the simulator and shows real computed results', async () => {
    adminIntelligence.mockResolvedValue(snapshot);
    adminSimulate.mockResolvedValue(simulated);
    const user = userEvent.setup();

    render(<AdminPage />);
    await screen.findByText('12');

    await user.click(screen.getByRole('button', { name: 'Run simulation' }));

    await waitFor(() => expect(adminSimulate).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Results')).toBeInTheDocument();
  });

  it('surfaces a simulator error instead of failing silently', async () => {
    adminIntelligence.mockResolvedValue(snapshot);
    adminSimulate.mockRejectedValue(new Error('tier_mix must sum to 1.0'));
    const user = userEvent.setup();

    render(<AdminPage />);
    await screen.findByText('12');

    await user.click(screen.getByRole('button', { name: 'Run simulation' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('tier_mix must sum to 1.0');
  });
});
