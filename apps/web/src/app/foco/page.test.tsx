// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import FocoHomePage from './page';
import type { FocusSession, NextActivity } from '@/lib/api';

const push = vi.fn();
const router = { push, replace: vi.fn() };
vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/components/mino/Mino', () => ({ Mino: () => null }));

const calls = vi.hoisted(() => ({
  focusCurrent: vi.fn(),
  nextActivity: vi.fn(),
  focusStart: vi.fn(),
  focusAbandon: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: calls };
});

afterEach(() => {
  for (const fn of Object.values(calls)) fn.mockReset();
  push.mockReset();
});

const learn: NextActivity = {
  kind: 'learn',
  title: 'Cardiology',
  concept: 'The QRS complex',
  journey_id: 'j-1',
  session_id: 's-1',
  due_count: 2,
  overdue_count: 0,
  minutes_estimate: 10,
  reason_code: 'continue',
  reason: 'Where you stopped in Cardiology',
};

const sitting: FocusSession = {
  id: 'f-1',
  kind: 'learn',
  title: 'Cardiology',
  concept: 'The QRS complex',
  journey_id: 'j-1',
  teaching_session_id: 's-1',
  planned_minutes: 10,
  steps_total: 4,
  steps_done: 1,
  status: 'paused',
  started_at: '2026-10-07T10:00:00Z',
  paused_at: '2026-10-07T10:03:00Z',
  completed_at: null,
  last_activity_at: '2026-10-07T10:03:00Z',
  seconds_left: 420,
  summary: { cards_reviewed: 0, concepts_touched: [] },
};

describe('Modo TDAH home', () => {
  it('shows one task, why, how long, a duration and one button — nothing else', async () => {
    calls.focusCurrent.mockResolvedValue(null);
    calls.nextActivity.mockResolvedValue(learn);
    const { container } = render(<FocoHomePage />);

    await screen.findByText('The QRS complex');
    expect(screen.getByText('ADHD mode')).toBeInTheDocument();
    expect(screen.getByText('Your focus now:')).toBeInTheDocument();
    expect(screen.getByText('Where you stopped in Cardiology.')).toBeInTheDocument();
    expect(screen.getByText('~10 min')).toBeInTheDocument();
    expect(screen.getAllByRole('radio').map((r) => r.textContent)).toEqual([
      '5 min',
      '10 min',
      '15 min',
      '25 min',
      'Auto',
    ]);
    // One primary action; no rail, no tab bar, no lists.
    expect(container.querySelectorAll('button.bg-primary:not([role="radio"])')).toHaveLength(1);
    expect(container.querySelector('nav.noema-rail, nav.noema-tabbar, ul')).toBeNull();
  });

  it('counts entering ADHD mode once per tab session', async () => {
    // An earlier test in this file already entered; start a fresh tab session.
    window.sessionStorage.clear();
    const plausible = vi.fn();
    window.plausible = plausible;
    calls.focusCurrent.mockResolvedValue(null);
    calls.nextActivity.mockResolvedValue(learn);
    try {
      const first = render(<FocoHomePage />);
      await screen.findByText('The QRS complex');
      first.unmount();
      render(<FocoHomePage />);
      await screen.findByText('The QRS complex');

      expect(plausible.mock.calls).toEqual([['adhd_mode_enabled', { props: { via: 'foco' } }]]);
    } finally {
      delete window.plausible;
      window.sessionStorage.clear();
    }
  });

  it('starts a sitting with the chosen duration and opens it', async () => {
    calls.focusCurrent.mockResolvedValue(null);
    calls.nextActivity.mockResolvedValue(learn);
    calls.focusStart.mockResolvedValue({ ...sitting, status: 'active', steps_done: 0 });
    render(<FocoHomePage />);

    await screen.findByText('The QRS complex');
    fireEvent.click(screen.getByRole('radio', { name: '5 min' }));
    expect(screen.getByText('~5 min')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));

    await waitFor(() => expect(calls.focusStart).toHaveBeenCalledWith(5, ''));
    expect(push).toHaveBeenCalledWith('/foco/sessao?id=f-1');
  });

  it('asks what to learn when nothing is under way, and sends it as the goal', async () => {
    calls.focusCurrent.mockResolvedValue(null);
    calls.nextActivity.mockResolvedValue({
      ...learn,
      kind: 'start',
      title: '',
      concept: '',
      reason_code: 'start',
      due_count: 0,
    });
    calls.focusStart.mockResolvedValue({ ...sitting, status: 'active' });
    render(<FocoHomePage />);

    const field = await screen.findByLabelText('What do you want to learn?');
    const start = screen.getByRole('button', { name: 'Start' });
    expect(start).toBeDisabled();
    fireEvent.change(field, { target: { value: 'how vaccines work' } });
    fireEvent.click(start);
    await waitFor(() => expect(calls.focusStart).toHaveBeenCalledWith(null, 'how vaccines work'));
  });

  it('offers to continue a sitting already under way instead of starting another', async () => {
    calls.focusCurrent.mockResolvedValue(sitting);
    calls.nextActivity.mockResolvedValue(learn);
    render(<FocoHomePage />);

    const go = await screen.findByRole('button', { name: 'Continue session' });
    expect(screen.getByText('Paused at step 2 of 4.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start' })).toBeNull();
    fireEvent.click(go);
    expect(push).toHaveBeenCalledWith('/foco/sessao?id=f-1');
  });
});
