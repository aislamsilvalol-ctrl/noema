// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import FocoSessionPage from './page';
import type { FocusSession } from '@/lib/api';

const push = vi.fn();
const replace = vi.fn();
const router = { push, replace };
let search = new URLSearchParams('id=f-1');
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => search,
}));
vi.mock('@/components/mino/Mino', () => ({
  Mino: ({ state }: { state: string }) => <span data-mino={state} />,
  MinoProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// The lesson engine's hook, as a store the test drives: what the server
// streams is not what these tests are about — the sitting around it is.
const lesson = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  ask: vi.fn(),
}));
vi.mock('@/components/professor/useLesson', () => ({
  useLesson: () => lesson.state,
}));

const calls = vi.hoisted(() => ({
  focusSession: vi.fn(),
  focusCurrent: vi.fn(),
  focusStep: vi.fn(),
  focusPause: vi.fn(),
  focusResume: vi.fn(),
  focusComplete: vi.fn(),
  session: vi.fn(),
  dueCards: vi.fn(),
  review: vi.fn(),
  nextActivity: vi.fn(),
  preferences: vi.fn(),
  checkQuiz: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: calls };
});

function sitting(patch: Partial<FocusSession> = {}): FocusSession {
  return {
    id: 'f-1',
    kind: 'review',
    title: '',
    concept: '',
    journey_id: null,
    teaching_session_id: null,
    planned_minutes: 5,
    steps_total: 2,
    steps_done: 0,
    status: 'active',
    started_at: '2026-10-07T10:00:00Z',
    paused_at: null,
    completed_at: null,
    last_activity_at: '2026-10-07T10:00:00Z',
    seconds_left: 300,
    summary: { cards_reviewed: 0, concepts_touched: [] },
    ...patch,
  };
}

const CARDS = [
  { id: 'c-1', front_md: 'What does the P wave show?', back_md: 'Atrial depolarisation' },
  { id: 'c-2', front_md: 'Normal QRS width?', back_md: 'Under 120 ms' },
];

beforeEach(() => {
  search = new URLSearchParams('id=f-1');
  calls.preferences.mockResolvedValue({ learning_mode: 'normal', session_minutes: 7 });
  calls.nextActivity.mockResolvedValue({
    kind: 'learn',
    title: 'Cardiology',
    concept: 'The QRS complex',
    journey_id: 'j-1',
    session_id: 's-1',
    due_count: 0,
    overdue_count: 0,
    minutes_estimate: 10,
    reason_code: 'continue',
    reason: '',
  });
  calls.dueCards.mockResolvedValue(CARDS);
  calls.review.mockResolvedValue({ card_id: 'c-1', due_at: null, scheduled_days: 3, state: 'review', mastery: null });
});

afterEach(() => {
  for (const fn of Object.values(calls)) fn.mockReset();
  lesson.ask.mockReset();
  push.mockReset();
  replace.mockReset();
});

describe('a review sitting', () => {
  it('shows one card, counts a rated card as a step, and gives feedback before moving on', async () => {
    calls.focusSession.mockResolvedValue(sitting());
    calls.focusStep.mockResolvedValue(sitting({ steps_done: 1 }));
    const { container } = render(<FocoSessionPage />);

    await screen.findByText('What does the P wave show?');
    expect(screen.getByText('Step 1/2')).toBeInTheDocument();
    expect(screen.getByText('~5 min left')).toBeInTheDocument();
    // One card at a time: the second is not on screen.
    expect(screen.queryByText('Normal QRS width?')).toBeNull();
    // No app chrome: no rail, no tab bar.
    expect(container.querySelector('nav.noema-rail, nav.noema-tabbar')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show answer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Good' }));

    await waitFor(() => expect(calls.focusStep).toHaveBeenCalledWith('f-1', 0));
    expect(calls.review).toHaveBeenCalledWith(expect.objectContaining({ card_id: 'c-1', rating: 3 }));
    expect(await screen.findByText('Step 1 of 2 done.')).toBeInTheDocument();
    expect(screen.getByText(/Next time: in 3 days\./)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('Normal QRS width?')).toBeInTheDocument();
    expect(screen.getByText('Step 2/2')).toBeInTheDocument();
  });

  it('pauses into a break screen and comes back to the same step', async () => {
    calls.focusSession.mockResolvedValue(sitting({ steps_done: 1 }));
    calls.focusPause.mockResolvedValue(sitting({ steps_done: 1, status: 'paused', paused_at: '2026-10-07T10:02:00Z' }));
    calls.focusResume.mockResolvedValue(sitting({ steps_done: 1 }));
    render(<FocoSessionPage />);

    await screen.findByText('Step 2/2');
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(await screen.findByText('Paused.')).toBeInTheDocument();
    expect(calls.focusPause).toHaveBeenCalledWith('f-1');

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(calls.focusResume).toHaveBeenCalledWith('f-1'));
    await waitFor(() => expect(screen.queryByText('Paused.')).toBeNull());
    expect(screen.getByText('Step 2/2')).toBeInTheDocument();
  });

  it('opens a paused sitting on its break screen after a refresh', async () => {
    calls.focusSession.mockResolvedValue(
      sitting({ steps_done: 1, status: 'paused', paused_at: '2026-10-07T10:02:00Z' }),
    );
    render(<FocoSessionPage />);
    expect(await screen.findByText('Paused.')).toBeInTheDocument();
    expect(calls.focusSession).toHaveBeenCalledWith('f-1');
  });

  it('ends with a summary from the server and a way back to normal mode', async () => {
    calls.focusSession.mockResolvedValue(sitting({ steps_done: 1 }));
    calls.focusStep.mockResolvedValue(sitting({ steps_done: 2 }));
    calls.focusComplete.mockResolvedValue(
      sitting({
        steps_done: 2,
        status: 'completed',
        completed_at: '2026-10-07T10:05:00Z',
        summary: { cards_reviewed: 2, concepts_touched: [] },
      }),
    );
    render(<FocoSessionPage />);

    await screen.findByText('What does the P wave show?');
    fireEvent.click(screen.getByRole('button', { name: 'Show answer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Easy' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Finish session' }));

    expect(await screen.findByText('Session done.')).toBeInTheDocument();
    expect(screen.getByText('2 steps done')).toBeInTheDocument();
    expect(screen.getByText('2 cards reviewed')).toBeInTheDocument();
    expect(await screen.findByText('The QRS complex')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to normal mode' }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/today'));
  });
});

describe('a learn sitting', () => {
  function lessonState(patch: Record<string, unknown> = {}) {
    lesson.state = {
      turns: [
        { role: 'user', content: 'Let us continue', segments: [{ kind: 'text', text: 'Let us continue' }] },
        {
          role: 'assistant',
          content: 'The QRS is the ventricles firing. What makes it wide?',
          segments: [{ kind: 'text', text: 'The QRS is the ventricles firing. What makes it wide?' }],
        },
      ],
      journey: null,
      sessionId: 's-1',
      resuming: false,
      input: '',
      setInput: vi.fn(),
      streaming: false,
      status: null,
      error: null,
      cheering: false,
      ask: lesson.ask,
      stop: vi.fn(),
      answerQuiz: vi.fn(),
      ...patch,
    };
  }

  it('drives the lesson engine: only the latest reply, and an answer becomes a step', async () => {
    lessonState();
    calls.focusSession.mockResolvedValue(
      sitting({ kind: 'learn', teaching_session_id: 's-1', concept: 'The QRS complex', steps_total: 4 }),
    );
    calls.session.mockResolvedValue({
      turns: [{ role: 'noema', content: 'x', created_at: '2026-10-07T10:00:30Z' }],
      learning_goal: 'Cardiology',
    });
    calls.focusStep.mockResolvedValue(
      sitting({ kind: 'learn', teaching_session_id: 's-1', steps_total: 4, steps_done: 1 }),
    );
    const { rerender } = render(<FocoSessionPage />);

    await screen.findByText('The QRS is the ventricles firing. What makes it wide?');
    expect(screen.getByText('Step 1/4')).toBeInTheDocument();
    // A reply already exists for this sitting: no second opening is sent.
    await waitFor(() => expect(calls.session).toHaveBeenCalledWith('s-1'));
    expect(lesson.ask).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole('button', { name: 'Got it, next' })[0]!);
    expect(lesson.ask).toHaveBeenCalledWith('Got it. Next.');

    // Mino answers (the stream starts and ends): that answered interaction is a step.
    lessonState({ streaming: true });
    rerender(<FocoSessionPage />);
    lessonState({ streaming: false });
    await act(async () => {
      rerender(<FocoSessionPage />);
    });
    await waitFor(() => expect(calls.focusStep).toHaveBeenCalledWith('f-1', 0));
    expect(await screen.findByText('Step 1 of 4 done.')).toBeInTheDocument();
    const after = document.querySelector('[data-foco-step-done]') as HTMLElement;
    expect(within(after).getByRole('button', { name: 'Continue' })).toBeInTheDocument();
    expect(within(after).getByRole('button', { name: 'Pause' })).toBeInTheDocument();
  });

  it('asks for the first reply of a fresh sitting once, with the learner\'s goal', async () => {
    lessonState({ turns: [] });
    calls.focusSession.mockResolvedValue(
      sitting({ kind: 'learn', teaching_session_id: 's-2', steps_total: 2 }),
    );
    calls.session.mockResolvedValue({ turns: [], learning_goal: 'how vaccines work' });
    render(<FocoSessionPage />);

    await waitFor(() => expect(lesson.ask).toHaveBeenCalledWith('how vaccines work'));
    expect(lesson.ask).toHaveBeenCalledTimes(1);
  });
});
