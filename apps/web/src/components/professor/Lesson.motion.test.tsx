// @vitest-environment jsdom
import { act, render, renderHook, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MinoProvider } from '@/components/mino/Mino';
import { LessonBlock, liveMinoState, MasteryNote } from '@/components/professor/Lesson';
import { CHEER_MS, masteryStep, useLesson, type Turn } from '@/components/professor/useLesson';
import { track } from '@/lib/analytics';
import type { Journey } from '@/lib/api';
import { en } from '@/locales/en';

type Callbacks = Record<string, ((...args: unknown[]) => void) | undefined>;
const stream = vi.hoisted(() => ({ script: (() => {}) as (callbacks: Callbacks) => void }));

vi.mock('@/lib/analytics', () => ({ track: vi.fn() }));
vi.mock('@/lib/api', async (original) => ({
  ...(await original<typeof import('@/lib/api')>()),
  professorChat: vi.fn(async (_body: unknown, callbacks: Callbacks) => stream.script(callbacks)),
}));

function media(reduced: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const wrapper = ({ children }: { children: ReactNode }) => <MinoProvider>{children}</MinoProvider>;

const journey = {
  id: 'j1',
  subject: 'Cálculo',
  concepts: [
    { name: 'Derivada', state: 'learning', evidence: 2, misconceptions: [] },
    { name: 'Limite', state: 'introduced', evidence: 1, misconceptions: [] },
  ],
} as unknown as Journey;

const reply = (segments: Turn['segments']): Turn => ({ role: 'assistant', content: '', segments });

describe('liveMinoState', () => {
  it('prefers a correct answer, then the server, then the stream', () => {
    const base = { streaming: true, waiting: true, server: null, cheering: false };
    expect(liveMinoState(base)).toBe('thinking');
    expect(liveMinoState({ ...base, waiting: false })).toBe('teaching');
    expect(liveMinoState({ ...base, streaming: false })).toBe('idle');
    expect(liveMinoState({ ...base, server: 'questioning' })).toBe('questioning');
    expect(liveMinoState({ ...base, server: 'correcting', cheering: true })).toBe('happy');
  });
});

describe('LessonBlock: the live Mino', () => {
  it('draws the state it is given for the live turn', () => {
    media(false);
    const { container } = render(
      <LessonBlock turn={reply([{ kind: 'text', text: 'Olha.' }])} streaming={false} status={null} mino="questioning" />,
    );
    expect(container.querySelector('[data-mino-state]')?.getAttribute('data-mino-state')).toBe('questioning');
  });

  it('before the first word shows Mino thinking and the status with a quiet ellipsis, not a spinner', () => {
    media(false);
    const { container } = render(<LessonBlock turn={reply([])} streaming status="Preparing an explanation…" />);
    expect(container.querySelector('[data-mino-state]')?.getAttribute('data-mino-state')).toBe('thinking');
    const line = container.querySelector('[data-lesson-thinking]') as HTMLElement;
    expect(line).toHaveAttribute('aria-live', 'polite');
    expect(line.querySelector('.noema-ellipsis')?.children).toHaveLength(3);
    // Read once, whole, by assistive technology.
    expect(screen.getByText('Preparing an explanation…')).toHaveClass('sr-only');
    expect(container.querySelector('.animate-spin')).toBeNull();
  });
});

describe('useLesson: Mino follows the server', () => {
  it('holds the server-named state for the live turn and clears it on the next question', async () => {
    media(false);
    stream.script = (cb) => {
      cb.onMino?.('questioning');
      cb.onToken?.('Qual é a derivada?');
      cb.onDone?.({});
    };
    const { result } = renderHook(() => useLesson({}), { wrapper });
    await act(() => result.current.ask('derivadas'));
    expect(result.current.serverMino).toBe('questioning');

    stream.script = (cb) => {
      cb.onToken?.('Certo.');
      cb.onDone?.({});
    };
    await act(() => result.current.ask('2x'));
    expect(result.current.serverMino).toBeNull();
  });

  it('ignores a state the server may not name', async () => {
    media(false);
    stream.script = (cb) => {
      cb.onMino?.('dancing');
      cb.onDone?.({});
    };
    const { result } = renderHook(() => useLesson({}), { wrapper });
    await act(() => result.current.ask('oi'));
    expect(result.current.serverMino).toBeNull();
  });

  it('a correct quiz answer makes the live Mino happy for a moment, then lets go', () => {
    media(false);
    vi.useFakeTimers();
    stream.script = () => {};
    const { result } = renderHook(() => useLesson({}), { wrapper });
    act(() => result.current.answerQuiz({ question: 'Q', chosen: '2x', concept: 'Derivada', correct: true }));
    expect(result.current.cheering).toBe(true);
    act(() => vi.advanceTimersByTime(CHEER_MS + 10));
    expect(result.current.cheering).toBe(false);
    expect(track).toHaveBeenCalledWith('exercise_answered', { kind: 'quiz', correct: 'true' });
  });

  it('a wrong answer does not cheer', () => {
    media(false);
    vi.useFakeTimers();
    stream.script = () => {};
    const { result } = renderHook(() => useLesson({}), { wrapper });
    act(() => result.current.answerQuiz({ question: 'Q', chosen: 'x', concept: 'Derivada', correct: false }));
    expect(result.current.cheering).toBe(false);
    expect(track).toHaveBeenCalledWith('exercise_answered', { kind: 'quiz', correct: 'false' });
  });
});

describe('mastery moment', () => {
  it('says so only for a real step up', () => {
    expect(masteryStep(journey, { concept: 'derivada', state: 'mastered' })).toBe('mastered');
    expect(masteryStep(journey, { concept: 'Limite', state: 'learning' })).toBe('learning');
    expect(masteryStep(journey, { concept: 'Derivada', state: 'learning' })).toBeNull();
    expect(masteryStep(journey, { concept: 'Limite', state: 'uncertain' })).toBeNull();
    const done = { ...journey, concepts: [{ ...journey.concepts[0]!, state: 'mastered' }] } as Journey;
    expect(masteryStep(done, { concept: 'Derivada', state: 'mastered' })).toBeNull();
  });

  it('a mastered event leaves a line in the reply and updates the journey', async () => {
    media(false);
    stream.script = (cb) => {
      cb.onJourney?.(journey);
      cb.onToken?.('Isso.');
      cb.onDone?.({});
    };
    const { result } = renderHook(() => useLesson({}), { wrapper });
    await act(() => result.current.ask('começar'));

    stream.script = (cb) => {
      cb.onToken?.('Exato.');
      cb.onDone?.({});
      cb.onMastery?.({ concept: 'Derivada', state: 'mastered', evidence: 4 });
    };
    await act(() => result.current.ask('2x'));

    const last = result.current.turns[result.current.turns.length - 1]!;
    expect(last.segments).toContainEqual({ kind: 'mastery', concept: 'Derivada', step: 'mastered' });
    expect(result.current.journey?.concepts[0]?.state).toBe('mastered');
    expect(track).toHaveBeenCalledWith('mastery_updated', { step: 'mastered' });

    const { container } = render(<LessonBlock turn={last} streaming={false} status={null} />);
    const note = container.querySelector('[data-lesson-mastery]') as HTMLElement;
    expect(note).toHaveTextContent(en.professor.mastery.mastered('Derivada'));
    expect(note).toHaveClass('noema-settle-in');
  });

  it('under reduced motion the note is simply there', () => {
    media(true);
    const { container } = render(<MasteryNote concept="Derivada" step="mastered" />);
    const note = container.querySelector('[data-lesson-mastery]') as HTMLElement;
    expect(note).toHaveTextContent(en.professor.mastery.mastered('Derivada'));
    expect(note).not.toHaveClass('noema-settle-in');
  });
});

describe('lesson completion', () => {
  const planned = (statuses: string[]) =>
    ({
      ...journey,
      plan: [{ title: 'M', status: 'current', lessons: statuses.map((status) => ({ title: 'L', status, concepts: [] })) }],
    }) as unknown as Journey;

  it('counts a lesson the plan newly marks done, once', async () => {
    media(false);
    vi.mocked(track).mockClear();
    stream.script = (cb) => {
      cb.onJourney?.(planned(['current', 'planned']));
      cb.onDone?.({});
    };
    const { result } = renderHook(() => useLesson({}), { wrapper });
    await act(() => result.current.ask('começar'));

    stream.script = (cb) => {
      cb.onJourney?.(planned(['done', 'current']));
      cb.onJourney?.(planned(['done', 'current']));
      cb.onDone?.({});
    };
    await act(() => result.current.ask('próxima'));

    const completed = vi.mocked(track).mock.calls.filter(([event]) => event === 'learning_session_completed');
    expect(completed).toEqual([['learning_session_completed', { kind: 'lesson' }]]);
  });
});
