// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import NewLearningPage from './page';
import type { Notebook, Preferences, Subject, Workspace } from '@/lib/api';

// Next's real useRouter() is referentially stable; a fresh object per render
// would retrigger every effect that lists it (see goals/page.test.tsx).
const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/learn/new',
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
// The character probes for WebGL on mount; jsdom has no canvas.
vi.mock('@/components/mino/Mino', () => ({
  Mino: () => null,
}));

const mocks = vi.hoisted(() => ({
  workspaces: vi.fn(),
  createWorkspace: vi.fn(),
  createSubject: vi.fn(),
  createNotebook: vi.fn(),
  preferences: vi.fn(),
  updatePreferences: vi.fn(),
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, api: { ...actual.api, ...mocks } };
});

const workspace: Workspace = {
  id: 'ws-1',
  title: 'My learning',
  slug: 'my-learning',
  position: 0,
  created_at: '2026-01-01T00:00:00Z',
};

const subject: Subject = {
  id: 'subj-1',
  workspace_id: 'ws-1',
  title: 'Freud',
  slug: 'freud',
  position: 0,
  created_at: '2026-01-01T00:00:00Z',
};

const notebook: Notebook = {
  id: 'nb-1',
  subject_id: 'subj-1',
  title: 'Freud',
  slug: 'freud',
  description: null,
  ai_provider_override: null,
  retrieval_settings: {},
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const preferences: Preferences = { learning_mode: 'normal', session_minutes: 7 };

afterEach(() => {
  for (const fn of Object.values(mocks)) fn.mockReset();
  push.mockReset();
  window.sessionStorage.clear();
});

describe('NewLearningPage', () => {
  it('walks subject → level → purpose → mode → path and starts the lesson', async () => {
    mocks.workspaces.mockResolvedValue({ items: [workspace], total: 1 });
    mocks.createSubject.mockResolvedValue(subject);
    mocks.createNotebook.mockResolvedValue(notebook);
    mocks.preferences.mockResolvedValue(preferences);
    mocks.updatePreferences.mockResolvedValue({ ...preferences, learning_mode: 'focus' });
    const user = userEvent.setup();
    render(<NewLearningPage />);

    await user.type(screen.getByLabelText(/what do you want to learn/i), 'Freud');
    await user.click(screen.getByRole('button', { name: /^next$/i }));

    await screen.findByText(/where are you with it/i);
    await user.click(screen.getByRole('button', { name: /starting from zero/i }));

    await screen.findByText(/what is it for/i);
    await user.click(screen.getByRole('button', { name: /^skip$/i }));

    // The mode step used to be a dead end: a choice saved the preference and
    // nothing led on. Continue is what this test exists to keep.
    await screen.findByText(/how do you prefer to learn/i);
    await user.click(screen.getByRole('button', { name: /focus/i }));
    await waitFor(() =>
      expect(mocks.updatePreferences).toHaveBeenCalledWith({ learning_mode: 'focus' }),
    );
    await user.click(screen.getByRole('button', { name: /^continue$/i }));

    const start = await screen.findByRole('button', { name: /start learning freud/i });
    await user.click(start);

    // An ordinary lesson, not a notebook made on the learner's behalf.
    await waitFor(() => expect(push).toHaveBeenCalledWith('/chat?new=1'));
    expect(mocks.createNotebook).not.toHaveBeenCalled();
  });

  it('goes back from the mode step without losing the subject', async () => {
    mocks.preferences.mockResolvedValue(preferences);
    const user = userEvent.setup();
    render(<NewLearningPage />);

    await user.type(screen.getByLabelText(/what do you want to learn/i), 'Freud');
    await user.click(screen.getByRole('button', { name: /^next$/i }));
    await user.click(await screen.findByRole('button', { name: /^skip$/i }));
    await user.click(await screen.findByRole('button', { name: /^skip$/i }));
    await screen.findByText(/how do you prefer to learn/i);

    await user.click(screen.getByRole('button', { name: /^back$/i }));
    await screen.findByText(/what is it for/i);
  });
});
