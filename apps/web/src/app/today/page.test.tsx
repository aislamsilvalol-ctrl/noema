// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TodayPage from './page';
import type { Journey, Mastery } from '@/lib/api';
import { takePrefill } from '@/lib/prefill';

// Stable router identity: the page's mount effect lists `router` as a
// dependency, and a fresh object per render would re-run it in a loop.
const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// The character needs a canvas and the rig's SVG; neither is what this page
// test is about.
vi.mock('@/components/mino/Mino', () => ({
  Mino: () => null,
}));

const calls = vi.hoisted(() => ({
  latestSession: vi.fn(),
  dueCards: vi.fn(),
  subjects: vi.fn(),
  notebooks: vi.fn(),
  latestJourney: vi.fn(),
  mastery: vi.fn(),
  journeys: vi.fn(),
  openLessons: vi.fn(),
  plan: vi.fn(),
  preferences: vi.fn(),
  updatePreferences: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: calls };
});

afterEach(() => {
  for (const fn of Object.values(calls)) fn.mockReset();
  window.sessionStorage.clear();
});

const journey: Journey = {
  id: 'j-1',
  subject: 'Cardiology',
  objective: 'Read an ECG',
  level: 'beginner',
  status: 'active',
  session_id: 's-1',
  focus_level: 0,
  checkpoints: 1,
  parked: [],
  current: { module: 0, lesson: 1, concept: 'The QRS complex' },
  plan: [
    {
      title: 'Rhythm',
      status: 'active',
      lessons: [
        { title: 'The P wave', status: 'done', concepts: ['P wave'] },
        { title: 'The QRS complex', status: 'active', concepts: ['QRS'] },
      ],
    },
  ],
  concepts: [
    { name: 'P wave', state: 'mastered', evidence: 5, misconceptions: [] },
    { name: 'QRS', state: 'learning', evidence: 2, misconceptions: [] },
  ],
  memory: [
    {
      created_at: '2026-09-15T10:00:00Z',
      level: 'session',
      summary: { last_taught: 'the P wave', next_step: 'measure the QRS width on three strips' },
      turn_from: 1,
      turn_to: 12,
    },
  ],
  momentum: { events_today: 0, mastered_today: 0 },
};

function score(name: string, mastery: number, observations: number): Mastery {
  return {
    concept_id: `c-${name}`,
    concept_name: name,
    mastery,
    provisional: false,
    last_evidence_at: null,
    // Which projection produced the number. Required on the response: FastAPI
    // marks a response model's fields required even when they have defaults,
    // because the response always carries them.
    source: 'graph',
    components: {
      calibration: 0,
      competence: 0,
      effective_observations: observations,
      prior_mean: 0,
      provisional: false,
      retrievability: 0,
      uncertainty: 0,
    },
  };
}

function emptyAccount() {
  calls.latestSession.mockResolvedValue(null);
  calls.dueCards.mockResolvedValue([]);
  calls.subjects.mockResolvedValue({ items: [], next_cursor: null });
  calls.notebooks.mockResolvedValue({ items: [], next_cursor: null });
  calls.latestJourney.mockResolvedValue(null);
  calls.mastery.mockResolvedValue([]);
  calls.journeys.mockResolvedValue([]);
  calls.openLessons.mockResolvedValue([]);
  calls.preferences.mockResolvedValue({ learning_mode: 'normal', session_minutes: 20 });
  calls.plan.mockResolvedValue({ blocks: [], estimated_minutes: 0, rationale: '' });
}

function returningAccount() {
  emptyAccount();
  calls.latestJourney.mockResolvedValue(journey);
  calls.journeys.mockResolvedValue([journey]);
  calls.dueCards.mockResolvedValue(
    Array.from({ length: 6 }, (_, i) => ({ id: `card-${i}`, front_md: '', back_md: '' })),
  );
  calls.subjects.mockResolvedValue({
    items: [{ id: 'subj-1', name: 'Cardiology' }],
    next_cursor: null,
  });
}

describe('TodayPage', () => {
  it('shows a first-run account one invitation and never calls the planner', async () => {
    emptyAccount();
    render(<TodayPage />);

    await screen.findByText(/Reviews and session plans appear here/);
    expect(screen.getByRole('link', { name: 'What do you want to learn?' })).toHaveAttribute(
      'href',
      '/learn/new',
    );
    expect(document.querySelector('[data-today-line]')).toBeNull();
    expect(document.querySelector('[data-review-row]')).toBeNull();
    expect(screen.queryByText('Plan a session')).not.toBeInTheDocument();
    expect(calls.plan).not.toHaveBeenCalled();
  });

  it('answers a returning learner in order: today, continue, review, growth, Mino', async () => {
    returningAccount();
    render(<TodayPage />);

    // The Today line waits for the preference, so the budget is the learner's own.
    await screen.findByText('Today · ~20 min');
    expect(
      screen.getByText('6 cards to review, ≈3 min; the lesson takes the remaining 17.'),
    ).toBeInTheDocument();

    const resume = screen.getByRole('link', { name: 'Continue Cardiology' });
    expect(resume).toHaveAttribute('href', '/chat');
    expect(resume.className).toContain('bg-primary');

    expect(screen.getByText('6 cards due · ≈ 3 min')).toBeInTheDocument();
    const review = screen.getByRole('link', { name: 'Start reviewing' });
    expect(review).toHaveAttribute('href', '/review');
    expect(review.className).not.toContain('bg-primary');

    expect(screen.getByText('1 of 2 concepts mastered across 1 journey')).toBeInTheDocument();
    expect(screen.getByText('Next step: measure the QRS width on three strips')).toBeInTheDocument();

    // The screen's order is the answer: today, then continue, then the list.
    const html = document.body.innerHTML;
    expect(html.indexOf('data-today-line')).toBeLessThan(html.indexOf('Continue Cardiology'));
    expect(html.indexOf('Continue Cardiology')).toBeLessThan(html.indexOf('data-review-row'));

    // One primary on the whole screen, the planner's action included. The
    // planner's selected budget segment shares the token but is not an action.
    await waitFor(() => expect(calls.plan).toHaveBeenCalled());
    expect(
      document.querySelectorAll('a.bg-primary, button.bg-primary:not([role="radio"])'),
    ).toHaveLength(1);
  });

  it('uses the planner\'s own review estimate once the plan is loaded', async () => {
    returningAccount();
    calls.plan.mockResolvedValue({
      rationale: 'Reviews first.',
      estimated_minutes: 18,
      blocks: [
        { kind: 'warmup', minutes: 4, why: '', items: [{ kind: 'card_review', concept_name: null }] },
        { kind: 'practice', minutes: 14, why: '', items: [{ kind: 'question', concept_name: null }] },
      ],
    });
    render(<TodayPage />);

    await screen.findByText('Reviews first.');
    expect(screen.getByText('6 cards due · 4 min')).toBeInTheDocument();
    expect(
      screen.getByText('6 cards to review, 4 min; the lesson takes the remaining 16.'),
    ).toBeInTheDocument();
  });

  it('names the weakest concept only when there is enough evidence to trust it', async () => {
    returningAccount();
    calls.mastery.mockResolvedValue([
      score('Bundle branch block', 20, 2), // weaker, but two observations is a guess
      score('The QRS complex', 41, 5),
      score('The P wave', 88, 9),
    ]);
    const { unmount } = render(<TodayPage />);

    await screen.findByText('The QRS complex · 41% mastery');
    expect(screen.queryByText(/Bundle branch block/)).not.toBeInTheDocument();
    // A new lesson about that concept, never whichever lesson was newest.
    const workOnIt = screen.getByRole('link', { name: 'Work on it' });
    expect(workOnIt).toHaveAttribute('href', '/chat?new=1');
    workOnIt.addEventListener('click', (event) => event.preventDefault());
    workOnIt.click();
    expect(takePrefill()).toEqual({ text: 'I want to work on The QRS complex.', autosend: true });
    unmount();

    calls.mastery.mockResolvedValue([score('Bundle branch block', 20, 2), score('The P wave', 88, 9)]);
    render(<TodayPage />);
    await screen.findByText('Today · ~20 min');
    expect(document.querySelector('[data-weak-row]')).toBeNull();
  });

  it('says plainly when nothing is due and no lesson is open', async () => {
    emptyAccount();
    // A library with no lesson yet: returning, but with nothing to continue.
    calls.notebooks.mockResolvedValue({
      items: [{ id: 'nb-1', title: 'Cardiology', subject_id: 'subj-1' }],
      next_cursor: null,
    });
    render(<TodayPage />);

    await screen.findByText('Nothing due and no lesson open.');
    expect(document.querySelector('[data-review-row]')).toBeNull();
    expect(document.querySelector('[data-mino-row]')).toBeNull();
  });
});
