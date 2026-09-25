// @vitest-environment jsdom
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ChatPage from './page';
import type { ChatCallbacks, LessonSummary, TeachingSession } from '@/lib/api';

// The address is the lesson: tests move it the way a link or the page would.
let search = '';
vi.mock('next/navigation', () => ({
  usePathname: () => '/chat',
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mocks = vi.hoisted(() => ({
  latestSession: vi.fn(),
  session: vi.fn(),
  openLessons: vi.fn(),
  journey: vi.fn(),
  journeyRecap: vi.fn(),
  professorChat: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    professorChat: mocks.professorChat,
    api: {
      ...actual.api,
      latestSession: mocks.latestSession,
      session: mocks.session,
      openLessons: mocks.openLessons,
      journey: mocks.journey,
      journeyRecap: mocks.journeyRecap,
    },
  };
});

function lesson(id: string, subject: string, line: string, ended = false): TeachingSession {
  return {
    id,
    subject,
    learning_goal: subject,
    current_topic: '',
    current_concept: '',
    ended_at: ended ? '2026-01-02T00:00:00Z' : null,
    last_turn_at: '2026-01-01T00:00:00Z',
    notebook_id: null,
    journey_id: null,
    plan: [],
    turn_count: 2,
    turns: [
      { role: 'learner', content: subject, intent: 'teach', created_at: '2026-01-01T00:00:00Z' },
      { role: 'noema', content: line, intent: 'teach', created_at: '2026-01-01T00:00:01Z' },
    ],
  };
}

function summary(id: string, subject: string): LessonSummary {
  return {
    id,
    journey_id: null,
    learning_goal: subject,
    subject,
    current_topic: '',
    current_concept: '',
    turn_count: 2,
    last_turn_at: '2026-09-20T00:00:00Z',
    created_at: '2026-09-20T00:00:00Z',
  };
}

const python = lesson('py', 'Python', 'Functions take arguments.');
const italian = lesson('it', 'Italiano', 'Ciao means hello.');

beforeEach(() => {
  mocks.openLessons.mockResolvedValue([]);
  mocks.journey.mockResolvedValue(null);
});

afterEach(() => {
  for (const fn of Object.values(mocks)) fn.mockReset();
  search = '';
  window.sessionStorage.clear();
});

describe('Which lesson /chat opens', () => {
  it('opens exactly the lesson in the address, and a refresh opens it again', async () => {
    search = 'session=py';
    mocks.session.mockResolvedValue(python);

    const { unmount } = render(<ChatPage />);
    await screen.findByText('Functions take arguments.');
    expect(mocks.session).toHaveBeenCalledWith('py');
    unmount();

    render(<ChatPage />);
    await screen.findByText('Functions take arguments.');
    expect(mocks.latestSession).not.toHaveBeenCalled();
  });

  it('never resumes the newest lesson on its own: plain /chat lists them by subject', async () => {
    mocks.openLessons.mockResolvedValue([summary('py', 'Python'), summary('it', 'Italiano')]);
    render(<ChatPage />);

    const link = await screen.findByRole('link', { name: /Italiano/ });
    expect(link).toHaveAttribute('href', '/chat?session=it');
    expect(screen.getByRole('link', { name: /Python/ })).toHaveAttribute('href', '/chat?session=py');
    expect(mocks.latestSession).not.toHaveBeenCalled();
    expect(mocks.session).not.toHaveBeenCalled();
    expect(screen.getByText(/tell mino what you want to learn/i)).toBeInTheDocument();
  });

  it('gives a new lesson its address as soon as the server creates it, without restarting it', async () => {
    const replace = vi.spyOn(window.history, 'replaceState');
    mocks.professorChat.mockImplementation(async (_body: unknown, callbacks: ChatCallbacks) => {
      callbacks.onSession?.({ id: 'calc', created: true });
      callbacks.onToken('A derivative is a rate of change.');
      callbacks.onDone?.({ prompt_tokens: 1, completion_tokens: 1 });
    });
    search = 'new=1';
    const { rerender } = render(<ChatPage />);

    await act(async () => {
      screen.getByRole('button', { name: /Python para|Python for/i }).click();
    });
    await screen.findByText('A derivative is a rate of change.');
    expect(replace).toHaveBeenCalledWith(null, '', '/chat?session=calc');

    // The router now reports the address the page wrote; the lesson stays.
    search = 'session=calc';
    rerender(<ChatPage />);
    expect(screen.getByText('A derivative is a rate of change.')).toBeInTheDocument();
    expect(mocks.session).not.toHaveBeenCalled();
    replace.mockRestore();
  });

  it('switching subject opens the other lesson with none of the first one on screen', async () => {
    search = 'session=py';
    mocks.session.mockImplementation(async (id: string) => (id === 'py' ? python : italian));
    const { rerender } = render(<ChatPage />);
    await screen.findByText('Functions take arguments.');

    search = 'session=it';
    rerender(<ChatPage />);

    await screen.findByText('Ciao means hello.');
    expect(screen.queryByText('Functions take arguments.')).not.toBeInTheDocument();
  });

  it('says so when the lesson in the address has ended, and offers the others', async () => {
    search = 'session=old';
    mocks.session.mockResolvedValue(lesson('old', 'Calculus', 'x', true));
    render(<ChatPage />);

    await screen.findByText(/no longer open/i);
    await waitFor(() => expect(mocks.openLessons).toHaveBeenCalled());
  });

  it('stopping for today shows what the lesson left instead of the composer', async () => {
    search = 'session=py';
    mocks.session.mockResolvedValue({ ...python, journey_id: 'j-1' });
    mocks.journey.mockResolvedValue({ id: 'j-1', subject: 'Python', plan: [], concepts: [], current: { module: 0, lesson: 0, concept: '' } });
    mocks.journeyRecap.mockResolvedValue({ know: ['functions'], shaky: [], now: 'arguments', next: ['closures'], parked: [] });
    render(<ChatPage />);
    await screen.findByText('Functions take arguments.');

    act(() => {
      screen.getAllByRole('button', { name: /stop for today/i })[0]!.click();
    });

    expect(await screen.findByText("Today's lesson")).toBeInTheDocument();
    expect(await screen.findByText('closures')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
