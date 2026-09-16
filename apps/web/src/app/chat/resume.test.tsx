// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ChatPage from './page';
import { ApiError, type TeachingSession } from '@/lib/api';

vi.mock('next/navigation', () => ({
  usePathname: () => '/chat',
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mocks = vi.hoisted(() => ({
  latestSession: vi.fn(),
  session: vi.fn(),
  professorChat: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    professorChat: mocks.professorChat,
    api: { ...actual.api, latestSession: mocks.latestSession, session: mocks.session },
  };
});

const KEY = 'noema.session.chat';

const lesson: TeachingSession = {
  id: 'sess-1',
  subject: 'Psychology',
  learning_goal: 'Understand Freud',
  current_topic: 'The unconscious',
  current_concept: 'repression',
  ended_at: null,
  last_turn_at: '2026-01-01T00:00:00Z',
  notebook_id: null,
  journey_id: null,
  plan: [],
  turn_count: 2,
  turns: [
    { role: 'learner', content: 'Quero aprender Freud', intent: 'teach', created_at: '2026-01-01T00:00:00Z' },
    { role: 'noema', content: 'Repression is where we start.', intent: 'teach', created_at: '2026-01-01T00:00:01Z' },
  ],
};

afterEach(() => {
  for (const fn of Object.values(mocks)) fn.mockReset();
  window.sessionStorage.clear();
});

describe('ChatPage resume', () => {
  it('picks up the latest open lesson when this tab has no stored session', async () => {
    mocks.latestSession.mockResolvedValue(lesson);
    render(<ChatPage />);

    await screen.findByText('Repression is where we start.');
    expect(mocks.latestSession).toHaveBeenCalledWith(undefined);
    expect(mocks.session).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(KEY)).toBe('sess-1');
    expect(screen.queryByText(/tell mino what you want to learn/i)).not.toBeInTheDocument();
  });

  it('prefers the session this tab was already in', async () => {
    window.sessionStorage.setItem(KEY, 'sess-1');
    mocks.session.mockResolvedValue(lesson);
    render(<ChatPage />);

    await screen.findByText('Repression is where we start.');
    expect(mocks.session).toHaveBeenCalledWith('sess-1');
    expect(mocks.latestSession).not.toHaveBeenCalled();
  });

  it('stays on the empty state when there is no lesson yet', async () => {
    mocks.latestSession.mockRejectedValue(
      new ApiError({ type: 'about:blank', status: 404, title: 'Not found', detail: 'No session.' }),
    );
    render(<ChatPage />);

    await waitFor(() => expect(mocks.latestSession).toHaveBeenCalled());
    expect(screen.getByText(/tell mino what you want to learn/i)).toBeInTheDocument();
    expect(window.sessionStorage.getItem(KEY)).toBeNull();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
