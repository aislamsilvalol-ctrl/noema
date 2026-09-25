// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PathPanel, TodayProgress } from './Progression';
import type { Progression } from '@/lib/api';

const { progress } = vi.hoisted(() => ({ progress: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, progress } };
});

const END = '2026-09-26T03:00:00Z';

function state(level: number): Progression {
  return {
    level,
    stage: level >= 5 ? 'trail' : 'first_steps',
    xp_total: 600,
    level_floor: 514,
    next_level_at: 780,
    xp_today: 45,
    missions: [
      { id: 'recall', period: 'daily', progress: 2, target: 3, done: false, xp: 25, ends_at: END },
      { id: 'lesson', period: 'daily', progress: 1, target: 1, done: true, xp: 25, ends_at: END },
      { id: 'master', period: 'weekly', progress: 0, target: 1, done: false, xp: 100, ends_at: END },
    ],
    marks: [
      { id: 'first_lesson', earned: true, earned_at: '2026-09-20T10:00:00Z' },
      { id: 'ten_mastered', earned: false, earned_at: null },
    ],
  };
}

afterEach(() => {
  progress.mockReset();
  window.localStorage.clear();
});

describe('Progression', () => {
  it('shows today only the daily missions, with honest counts', async () => {
    progress.mockResolvedValue(state(5));
    render(<TodayProgress />);

    expect(await screen.findByText('Recall 3 cards')).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.queryByText('Master one concept')).not.toBeInTheDocument();
    expect(screen.getByText(/180 XP to the next level/)).toBeInTheDocument();
  });

  it('stamps earned marks and leaves the rest as not yet', async () => {
    progress.mockResolvedValue(state(5));
    render(<PathPanel />);

    const earned = await screen.findByText('First lesson');
    expect(earned.closest('[data-mark]')).toHaveAttribute('data-earned', 'true');
    expect(screen.getByText('Ten concepts').closest('[data-mark]')).toHaveAttribute(
      'data-earned',
      'false',
    );
  });

  it('announces a level reached since the last visit, once', async () => {
    window.localStorage.setItem('noema.level.seen', '4');
    progress.mockResolvedValue(state(5));
    const { unmount } = render(<TodayProgress />);
    expect(await screen.findByRole('status')).toHaveTextContent('Level 5');
    unmount();

    render(<TodayProgress />);
    await screen.findByText('Recall 3 cards');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows nothing, and breaks nothing, when progress cannot load', async () => {
    progress.mockRejectedValue(new Error('down'));
    const { container } = render(<TodayProgress />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(container).toBeEmptyDOMElement();
  });
});
