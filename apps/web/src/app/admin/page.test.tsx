// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminPage from './page';
import {
  ApiError,
  type AdminIntelligence,
  type AdminUser,
  type PlanReport,
  type SimulatorOut,
} from '@/lib/api';

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const {
  adminIntelligence,
  adminSimulate,
  adminUsers,
  adminSetPlan,
  adminProfitReport,
  downloadUsersReport,
} = vi.hoisted(() => ({
  adminIntelligence: vi.fn(),
  adminSimulate: vi.fn(),
  adminUsers: vi.fn(),
  adminSetPlan: vi.fn(),
  adminProfitReport: vi.fn(),
  downloadUsersReport: vi.fn(),
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      adminIntelligence,
      adminSimulate,
      adminUsers,
      adminSetPlan,
      adminProfitReport,
      // The Professor economy panel loads on its own; an empty month is the
      // honest default for every test that is not about it.
      adminProfessorEconomy: vi.fn().mockResolvedValue({
        features: [],
        calls: 0,
        prompt_tokens: 0,
        cached_tokens: 0,
        completion_tokens: 0,
        cost_cents: 0,
        cache_hit_rate: null,
        compaction_tokens_saved: 0,
        compactions: 0,
        lessons: 0,
        cost_per_lesson_cents: null,
        active_learners: 0,
        cost_per_learner_cents: null,
      }),
    },
    downloadUsersReport,
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

const bob: AdminUser = {
  id: 'u2',
  email: 'bob@example.com',
  display_name: 'Bob',
  plan: 'free',
  created_at: '2026-01-01T00:00:00Z',
  used_units_this_period: 40,
  limit_units: 100,
};

const profitRows: PlanReport[] = [
  {
    plan: 'free',
    user_count: 3,
    real_cost_cents: 120.0,
    projected_revenue_if_billed_cents: 0,
    projected_margin_if_billed_cents: -120.0,
  },
  {
    plan: 'pro',
    user_count: 2,
    real_cost_cents: 200.0,
    projected_revenue_if_billed_cents: 11980,
    projected_margin_if_billed_cents: 11780.0,
  },
];

beforeEach(() => {
  adminUsers.mockResolvedValue({ items: [bob], next_cursor: null });
  adminProfitReport.mockResolvedValue(profitRows);
});

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

  it('lists real users with their plan and usage', async () => {
    adminIntelligence.mockResolvedValue(snapshot);

    render(<AdminPage />);

    expect(await screen.findByText('bob@example.com')).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === 'Usage this month: 40 / 100')).toBeInTheDocument();
  });

  it('changes a plan and reflects the update, without a page reload', async () => {
    adminIntelligence.mockResolvedValue(snapshot);
    adminSetPlan.mockResolvedValue({ ...bob, plan: 'pro' });
    const user = userEvent.setup();

    render(<AdminPage />);
    await screen.findByText('bob@example.com');

    await user.selectOptions(screen.getByDisplayValue('free'), 'pro');

    await waitFor(() => expect(adminSetPlan).toHaveBeenCalledWith('u2', 'pro'));
    expect(await screen.findByDisplayValue('pro')).toBeInTheDocument();
  });

  it('shows a retryable error when a plan change fails, and keeps the old plan', async () => {
    adminIntelligence.mockResolvedValue(snapshot);
    adminSetPlan.mockRejectedValue(new Error('could not change plan'));
    const user = userEvent.setup();

    render(<AdminPage />);
    await screen.findByText('bob@example.com');

    await user.selectOptions(screen.getByDisplayValue('free'), 'pro');

    expect(await screen.findByText('could not change plan')).toBeInTheDocument();
    expect(screen.getByDisplayValue('free')).toBeInTheDocument();
  });

  it('searches users by the typed query', async () => {
    adminIntelligence.mockResolvedValue(snapshot);
    const user = userEvent.setup();

    render(<AdminPage />);
    await screen.findByText('bob@example.com');

    await user.type(screen.getByPlaceholderText('Search by email or name'), 'bob');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(adminUsers).toHaveBeenLastCalledWith('bob'));
  });

  it('renders the real per-plan profit projection, one row per plan', async () => {
    adminIntelligence.mockResolvedValue(snapshot);

    render(<AdminPage />);

    // user_count is locale-independent, unlike the currency-formatted cells --
    // real proof the fetched rows reached the table, not a formatting check.
    // Scoped to <td> since the Users section's plan <select> also renders
    // "free"/"pro" as <option> text.
    const freeRow = (await screen.findByText('free', { selector: 'td' })).closest('tr');
    const proRow = screen.getByText('pro', { selector: 'td' }).closest('tr');
    expect(freeRow).toHaveTextContent('3');
    expect(proRow).toHaveTextContent('2');
  });

  it('never presents the projection as real revenue -- the honest-boundary note is always shown', async () => {
    adminIntelligence.mockResolvedValue(snapshot);

    render(<AdminPage />);

    const note = await screen.findByText(/there is no Stripe integration/i);
    expect(note).toBeInTheDocument();
    expect(note.textContent).toMatch(/projection/i);
  });

  it('exports the users CSV and surfaces a real download failure', async () => {
    adminIntelligence.mockResolvedValue(snapshot);
    downloadUsersReport.mockRejectedValue(new Error('export failed'));
    const user = userEvent.setup();

    render(<AdminPage />);
    await screen.findByText('bob@example.com');

    await user.click(screen.getByRole('button', { name: 'Export users (CSV)' }));

    expect(await screen.findByText('export failed')).toBeInTheDocument();
    expect(downloadUsersReport).toHaveBeenCalledTimes(1);
  });
});
