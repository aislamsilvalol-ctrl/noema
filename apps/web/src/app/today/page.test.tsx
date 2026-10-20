// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
  nextActivity: vi.fn(),
  progress: vi.fn(),
  me: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: calls };
});

// Home's words follow the hour; the tests read them at a fixed afternoon so
// they pass at any time of day (CI runs at night, UTC).
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 19, 15, 0));
});

afterEach(() => {
  vi.useRealTimers();
  for (const fn of Object.values(calls)) fn.mockReset();
  window.sessionStorage.clear();
});

const learn = {
  kind: 'learn',
  title: 'Cardiology',
  concept: 'The QRS complex',
  journey_id: 'j-1',
  session_id: 's-1',
  due_count: 0,
  overdue_count: 0,
  minutes_estimate: 10,
  reason_code: 'continue',
  reason: 'Where you stopped in Cardiology',
};

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
    {
      title: 'Blocks',
      status: 'planned',
      lessons: [{ title: 'Bundle branch block', status: 'planned', concepts: ['BBB'] }],
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
  calls.progress.mockResolvedValue(null);
  calls.me.mockResolvedValue({ id: 'u-1', email: 'ada@example.com', display_name: 'Ada Lovelace' });
  calls.nextActivity.mockResolvedValue({
    kind: 'start',
    title: '',
    concept: '',
    journey_id: null,
    session_id: null,
    due_count: 0,
    overdue_count: 0,
    minutes_estimate: 10,
    reason_code: 'start',
    reason: 'Nothing under way yet',
  });
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
  it('gives a first day one question, a field to answer it and three lines on how it goes', async () => {
    emptyAccount();
    render(<TodayPage />);

    const heading = await screen.findByRole('heading', { level: 1, name: 'What do you want to learn?' });
    expect(heading).toBeInTheDocument();
    expect(document.querySelector('[data-dash-hero]')?.textContent).toMatch(/, Ada[.?]/);
    expect(document.querySelectorAll('[data-first-day-steps] li')).toHaveLength(3);
    // Nothing to plan, review or measure yet.
    expect(document.querySelector('[data-next-action]')).toBeNull();
    expect(document.querySelector('[data-progress-summary]')).toBeNull();
    expect(document.querySelector('[data-journey-trail]')).toBeNull();

    fireEvent.change(screen.getByLabelText('A subject to learn'), { target: { value: 'Organic chemistry' } });
    fireEvent.click(screen.getByRole('button', { name: /Start/ }));
    expect(takePrefill()).toEqual({ text: 'Organic chemistry', autosend: false });
    expect(push).toHaveBeenCalledWith('/learn/new');
  });

  it('starts a first day from an idea too', async () => {
    emptyAccount();
    render(<TodayPage />);

    fireEvent.click(await screen.findByRole('button', { name: 'How memory works' }));
    expect(takePrefill()).toEqual({ text: 'How memory works', autosend: false });
    expect(push).toHaveBeenCalledWith('/learn/new');
  });

  it('greets by first name and answers a returning learner in order: hero, trail, now, progress', async () => {
    returningAccount();
    calls.nextActivity.mockResolvedValue(learn);
    render(<TodayPage />);

    await screen.findByRole('heading', { level: 1, name: 'The QRS complex' });
    expect(document.querySelector('[data-dash-hero]')?.textContent).toMatch(/Ada\./);
    expect(screen.getByText('lesson 2 of 3')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '1 of 2 concepts mastered' })).toBeInTheDocument();

    const resume = screen.getByRole('link', { name: 'Continue Cardiology' });
    expect(resume).toHaveAttribute('href', '/chat');

    // The order is the answer: where am I, the way, what now, how I grow.
    await screen.findByText('Now');
    const html = document.body.innerHTML;
    const at = (marker: string) => html.indexOf(marker);
    expect(at('data-dash-hero')).toBeLessThan(at('data-journey-trail'));
    expect(at('data-journey-trail')).toBeLessThan(at('data-next-action'));
    expect(at('data-next-action')).toBeLessThan(at('data-progress-summary'));

    // One ember action on the whole screen: Continue.
    expect(document.querySelectorAll('a.dash-ember, button.dash-ember')).toHaveLength(1);
  });

  it('opens the lesson that belongs to the journey', async () => {
    returningAccount();
    calls.openLessons.mockResolvedValue([
      { id: 'other', journey_id: 'j-2', subject: 'Python', current_topic: 'Loops', current_concept: 'for', learning_goal: 'Python', created_at: '', last_turn_at: null, turn_count: 3 },
      { id: 's-1', journey_id: 'j-1', subject: 'Cardiology', current_topic: '', current_concept: '', learning_goal: 'ECG', created_at: '', last_turn_at: null, turn_count: 9 },
    ]);
    render(<TodayPage />);

    const resume = await screen.findByRole('link', { name: 'Continue Cardiology' });
    expect(resume).toHaveAttribute('href', '/chat?session=s-1');
    // The other lesson is offered to pick up again, the hero's is not.
    const tiles = [...document.querySelectorAll('[data-resume-tile]')];
    expect(tiles.map((tile) => tile.getAttribute('href'))).toEqual(['/chat?session=other']);
  });

  it('lets the engine lead "now" when reviews have slipped', async () => {
    returningAccount();
    calls.nextActivity.mockResolvedValue({
      ...learn,
      kind: 'review',
      due_count: 6,
      overdue_count: 2,
      minutes_estimate: 4,
      reason_code: 'overdue',
    });
    render(<TodayPage />);

    await screen.findByText(/2 cards have slipped past the right moment/);
    const review = document.querySelector('[data-now-review]');
    expect(review).toHaveAttribute('href', '/review');
    expect(review?.textContent).toContain('~4 min');
    // Reviews are already the "now" line; the hero does not repeat them.
    expect(screen.queryByText(/Review 6 cards ·/)).not.toBeInTheDocument();
  });

  it('names the weakest concept only when there is enough evidence to trust it', async () => {
    returningAccount();
    calls.nextActivity.mockResolvedValue(learn);
    calls.mastery.mockResolvedValue([
      score('Bundle branch block', 20, 2), // weaker, but two observations is a guess
      score('The QRS complex', 41, 5),
      score('The P wave', 88, 9),
    ]);
    render(<TodayPage />);

    await screen.findByText('You are nearly there with The QRS complex. Worth a second look before moving on.');
    expect(screen.queryByText(/Bundle branch block with Mino/)).not.toBeInTheDocument();
    expect(screen.getByText('41% so far')).toBeInTheDocument();

    const weak = document.querySelector('[data-now-weak]') as HTMLAnchorElement;
    expect(weak).toHaveAttribute('href', '/chat?new=1');
    fireEvent.click(weak);
    expect(takePrefill()).toEqual({ text: 'I want to work on The QRS complex.', autosend: true });

    // Reviews due go beside Continue when "now" is about something else.
    expect(screen.getByRole('link', { name: 'Review 6 cards · 3 min' })).toHaveAttribute('href', '/review');
  });

  it('falls back to what the lesson found shaky when the graph cannot name a weak concept', async () => {
    returningAccount();
    calls.nextActivity.mockResolvedValue(learn);
    calls.latestJourney.mockResolvedValue({
      ...journey,
      concepts: [
        { name: 'P wave', state: 'mastered', evidence: 5, misconceptions: [] },
        { name: 'Bundle branch block', state: 'uncertain', evidence: 3, misconceptions: [] },
      ],
    });
    render(<TodayPage />);

    await screen.findByText(/nearly there with Bundle branch block/);
    expect(screen.getByText('went wrong twice in the lesson')).toBeInTheDocument();
  });

  it('offers Modo TDAH with the engine’s one task, as a short session', async () => {
    returningAccount();
    calls.dueCards.mockResolvedValue([]);
    calls.nextActivity.mockResolvedValue(learn);
    render(<TodayPage />);

    await waitFor(() => expect(document.querySelector('[data-foco-card]')).not.toBeNull());
    const focus = document.querySelector('[data-foco-card]');
    expect(focus).toHaveAttribute('href', '/foco');
    expect(focus?.textContent).toContain('One thing only: The QRS complex');
    expect(focus?.textContent).toContain('~10 min');
    // With nothing more urgent, Mino says what was agreed last time.
    expect(screen.getByText('Next step: measure the QRS width on three strips')).toBeInTheDocument();
  });

  it('stays usable when the recommendation fails', async () => {
    returningAccount();
    calls.dueCards.mockResolvedValue([]);
    calls.nextActivity.mockRejectedValue(new Error('down'));
    render(<TodayPage />);

    expect(await screen.findByRole('link', { name: 'Continue Cardiology' })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector('[data-progress-summary]')).not.toBeNull());
    expect(document.querySelector('[data-foco-card]')).toBeNull();
  });

  it('shows progress from the server only, and no zero for today', async () => {
    returningAccount();
    calls.nextActivity.mockResolvedValue(learn);
    calls.progress.mockResolvedValue({
      level: 4,
      stage: 'trail',
      xp_total: 450,
      level_floor: 329,
      next_level_at: 514,
      xp_today: 0,
      marks: [],
      missions: [
        { id: 'recall', period: 'daily', progress: 1, target: 3, done: false, xp: 25, ends_at: '' },
        { id: 'days', period: 'weekly', progress: 2, target: 4, done: false, xp: 100, ends_at: '' },
      ],
    });
    render(<TodayPage />);

    await waitFor(() => expect(document.querySelector('[data-signal="level"]')).not.toBeNull());
    expect(document.querySelector('[data-signal="mastered"]')?.textContent).toContain('1');
    expect(document.querySelector('[data-signal="level"]')?.textContent).toContain('level · Trail');
    expect(document.querySelector('[data-signal="week"]')?.textContent).toContain('2/4');
    expect(document.querySelector('[data-signal="today"]')).toBeNull();
    // Daily goals are gamification: they live on Progress, not on Home.
    expect(document.querySelector('[data-daily-goals]')).toBeNull();
  });

  it('explores the journey’s real next stretch first, then ideas', async () => {
    returningAccount();
    calls.nextActivity.mockResolvedValue(learn);
    render(<TodayPage />);

    await waitFor(() => expect(document.querySelectorAll('[data-explore-tile]').length).toBe(3));
    const [first, idea] = [...document.querySelectorAll('[data-explore-tile]')] as HTMLAnchorElement[];
    expect(first?.textContent).toContain('Blocks');
    expect(first?.textContent).toContain('After Rhythm');
    fireEvent.click(idea!);
    expect(takePrefill()).toEqual({ text: 'How memory works', autosend: false });
  });

  it('sends a signed-out visitor to the login page', async () => {
    emptyAccount();
    const { ApiError } = await import('@/lib/api');
    calls.latestSession.mockRejectedValue(new ApiError({ status: 401, title: 'Unauthorized' } as never));
    render(<TodayPage />);

    await waitFor(() => expect(push).toHaveBeenCalledWith('/login'));
  });
});
