// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LaunchSection } from './LaunchSection';
import type { AdminLaunch } from '@/lib/api';

vi.mock('@/lib/i18n', async () => {
  const { en } = await import('@/locales/en');
  return { useT: () => en };
});

const { adminLaunch } = vi.hoisted(() => ({ adminLaunch: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { adminLaunch } };
});

function day(i: number, over: Partial<AdminLaunch['daily'][number]> = {}) {
  return {
    day: `2026-09-${String(i + 1).padStart(2, '0')}`,
    signups: 0,
    activated: 0,
    dau: 0,
    lessons_started: 0,
    lessons_completed: 0,
    focus_started: 0,
    focus_completed: 0,
    successful_sessions: 0,
    ai_calls: 0,
    ai_failures: 0,
    ai_cost_cents: 0,
    ...over,
  };
}

const LAUNCH: AdminLaunch = {
  days: 14,
  window_start: '2026-09-01',
  window_end: '2026-09-14',
  generated_at: '2026-09-14T12:00:00Z',
  daily: Array.from({ length: 14 }, (_, i) =>
    day(i, { signups: i % 3, dau: i, lessons_started: i % 4, successful_sessions: i % 2, ai_calls: 10 * i }),
  ),
  weekly: [
    { week_start: '2026-08-31', active_learners: 6, successful_sessions: 3, north_star: 0.5 },
    { week_start: '2026-09-07', active_learners: 0, successful_sessions: 0, north_star: null },
  ],
  signups: 13,
  activated: 4,
  activation_cohort: 8,
  activation_cohort_activated: 3,
  activation_rate: 0.375,
  dau: 13,
  wau: 20,
  lessons_started: 19,
  lessons_completed: 7,
  successful_sessions: { teaching: 4, focus: 2, review: 1 },
  north_star: 1.25,
  d1_cohort: 12,
  d1_retained: 6,
  d1_rate: 0.5,
  d7_cohort: 0,
  d7_retained: 0,
  d7_rate: null,
  revenue: [
    { plan: 'student', paying: 0, comped: 1, price_cents: 2990, mrr_cents: 0 },
    { plan: 'pro', paying: 2, comped: 0, price_cents: 5990, mrr_cents: 11980 },
    { plan: 'max', paying: 0, comped: 0, price_cents: 9990, mrr_cents: 0 },
  ],
  paying_users: 2,
  mrr_cents: 11980,
  ai_calls: 910,
  ai_failures: 9,
  ai_failure_rate: 0.0099,
  ai_cost_cents: 432.5,
  ai_latency_p50_ms: null,
  ai_latency_p95_ms: null,
  feedback_reports: 3,
  focus_started: 5,
  focus_completed: 2,
  definitions: {
    activation: 'Within 7 days of signup: started a lesson and answered a graded item.',
    north_star: 'Successful learning sessions per weekly active learner.',
  },
  not_recorded: ['ai_latency_ms'],
};

beforeEach(() => {
  adminLaunch.mockReset();
  adminLaunch.mockResolvedValue(LAUNCH);
});

describe('LaunchSection', () => {
  it('shows the funnel headline from the report', async () => {
    render(<LaunchSection />);

    expect(await screen.findByText('37.5%')).toBeInTheDocument();
    expect(screen.getByText('3 of 8, signups ≥ 7 days old')).toBeInTheDocument();
    expect(screen.getByText('13 · 20')).toBeInTheDocument();
    expect(screen.getByText('1.25')).toBeInTheDocument();
    expect(adminLaunch).toHaveBeenCalledWith(30);
  });

  it('says a rate it cannot compute is a dash, not zero', async () => {
    render(<LaunchSection />);

    // D7: nobody has been around for seven days yet.
    expect(await screen.findByText('50.0% · —')).toBeInTheDocument();
    const weekly = document.querySelector('[data-launch-weekly]') as HTMLElement;
    expect(within(weekly).getByText('—')).toBeInTheDocument();
  });

  it('draws one bar per day for each series, with its total', async () => {
    render(<LaunchSection />);

    const strip = await screen.findByRole('img', { name: 'AI calls: 910' });
    expect(strip.querySelectorAll('rect')).toHaveLength(14);
    expect(screen.getByRole('img', { name: 'Signups: 13' })).toBeInTheDocument();
  });

  it('separates paying from comped plans', async () => {
    render(<LaunchSection />);

    const revenue = (await screen.findByText('pro')).closest('table') as HTMLElement;
    const student = within(revenue).getByText('student').closest('tr') as HTMLElement;
    expect(within(student).getAllByText('0')).toHaveLength(1);
    expect(within(student).getByText('1')).toBeInTheDocument();
  });

  it('names what is not recorded and shows the definitions', async () => {
    render(<LaunchSection />);

    expect(await screen.findByText(/Not recorded yet: ai_latency_ms/)).toBeInTheDocument();
    expect(screen.getByText(/answered a graded item/)).toBeInTheDocument();
  });

  it('reloads for another window', async () => {
    const user = userEvent.setup();
    render(<LaunchSection />);
    await screen.findByText('37.5%');

    await user.click(screen.getByRole('button', { name: '90d' }));

    await waitFor(() => expect(adminLaunch).toHaveBeenLastCalledWith(90));
  });

  it('says so when the report cannot load', async () => {
    adminLaunch.mockRejectedValue(new Error('Admin access required.'));
    render(<LaunchSection />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Admin access required.');
  });
});
