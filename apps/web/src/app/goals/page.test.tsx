// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import GoalsPage from './page';
import type { Goal, Notebook } from '@/lib/api';

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

const notebook: Notebook = {
  id: 'nb-1',
  subject_id: 'subj-1',
  title: 'Cardiology',
  slug: 'cardiology',
  description: null,
  ai_provider_override: null,
  retrieval_settings: {},
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const goal: Goal = {
  id: 'goal-1',
  notebook_id: 'nb-1',
  title: 'Pass the cardiovascular exam',
  due_on: '2026-12-01',
  days_left: 10,
  minutes_per_day: 30,
  required_minutes_per_day: 25,
  reachable: true,
  achieved_at: null,
  projected_mastery: 80,
  target_mastery: 85,
  summary: 'On track.',
  milestones: [],
};

const { goals, notebooks, deleteGoal } = vi.hoisted(() => ({
  goals: vi.fn(),
  notebooks: vi.fn(),
  deleteGoal: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      goals,
      notebooks,
      createGoal: vi.fn(),
      deleteGoal,
    },
  };
});

import { api } from '@/lib/api';

afterEach(() => {
  goals.mockReset();
  notebooks.mockReset();
  deleteGoal.mockReset();
  vi.mocked(api.createGoal).mockReset();
});

async function renderLoaded() {
  notebooks.mockResolvedValue({ items: [notebook], next_cursor: null });

  render(<GoalsPage />);
  await screen.findByText('Pass the cardiovascular exam');
}

describe('GoalsPage drop', () => {
  it('removes the goal from the list when deletion succeeds', async () => {
    goals.mockResolvedValueOnce([goal]).mockResolvedValueOnce([]);
    deleteGoal.mockResolvedValue(undefined);
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: 'Drop this goal' }));

    await waitFor(() => {
      expect(screen.queryByText('Pass the cardiovascular exam')).not.toBeInTheDocument();
    });
    expect(deleteGoal).toHaveBeenCalledWith('goal-1');
  });

  it('shows an error and keeps the goal when deletion fails', async () => {
    goals.mockResolvedValue([goal]);
    deleteGoal.mockRejectedValue(new Error('network down'));
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: 'Drop this goal' }));

    await screen.findByRole('alert');
    expect(screen.getByText('Pass the cardiovascular exam')).toBeInTheDocument();
  });
});
