// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProfessorPage from './page';
import type { ChatCallbacks, Notebook } from '@/lib/api';

// Next's real useRouter()/useParams() are referentially stable across
// renders; a fresh object literal here would give this page's effects a new
// dependency identity every render and retrigger them in a loop (see
// cards/page.test.tsx and notebooks/[id]/page.test.tsx, where this bit).
const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'nb-1' }),
  useRouter: () => router,
  usePathname: () => '/notebooks/nb-1/professor',
}));

vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const notebook: Notebook = {
  id: 'nb-1',
  subject_id: 'subj-1',
  title: 'Cell Biology',
  slug: 'cell-biology',
  description: null,
  ai_provider_override: null,
  retrieval_settings: {},
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const { professorChat } = vi.hoisted(() => ({ professorChat: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    professorChat,
    api: { ...actual.api, notebook: vi.fn(), createNote: vi.fn() },
  };
});

import { api } from '@/lib/api';

afterEach(() => {
  vi.mocked(api.notebook).mockReset();
  vi.mocked(api.createNote).mockReset();
  professorChat.mockReset();
});

async function renderLoaded() {
  vi.mocked(api.notebook).mockResolvedValue(notebook);
  render(<ProfessorPage />);
  await screen.findByText(notebook.title);
}

describe('ProfessorPage', () => {
  it('shows the empty lede before any message is sent', async () => {
    await renderLoaded();
    expect(
      screen.getByText(/ask anything about this notebook/i),
    ).toBeInTheDocument();
  });

  it('streams tokens from the classified intent into the assistant turn', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onIntent?.('explain');
        callbacks.onToken('Mitosis ');
        callbacks.onToken('is cell division.');
        callbacks.onDone?.({ prompt_tokens: 10, completion_tokens: 5 });
      },
    );
    const user = userEvent.setup();
    await renderLoaded();

    // A single change event rather than per-keystroke typing -- this test is
    // about the SSE handling, not about exercising realistic keyboard input,
    // and per-keystroke typing of a full sentence pushed this test past the
    // default timeout under load (the same class of environment slowness
    // this session has hit before in cards/page.test.tsx).
    const textarea = screen.getByPlaceholderText(/ask professor noema/i);
    await user.click(textarea);
    await user.paste('mitosis?');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText('Mitosis is cell division.');
    expect(professorChat).toHaveBeenCalledWith(
      {
        notebook_id: 'nb-1',
        messages: [{ role: 'user', content: 'mitosis?' }],
      },
      expect.anything(),
      expect.anything(),
    );
  });

  it('renders a generated-questions action with a link to the quiz', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onIntent?.('quiz_me');
        callbacks.onAction?.({ intent: 'quiz_me', count: 3, items: [] });
      },
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(screen.getByPlaceholderText(/ask professor noema/i), 'Test me');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText('3 questions created.');
    expect(screen.getByRole('link', { name: /open quiz/i })).toHaveAttribute(
      'href',
      '/notebooks/nb-1/quiz',
    );
  });

  it('renders a generated exam with a link to sit it', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onIntent?.('create_exam');
        callbacks.onAction?.({
          intent: 'create_exam',
          count: 1,
          items: [],
          exam_id: 'exam-1',
          minutes: 20,
        });
      },
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(
      screen.getByPlaceholderText(/ask professor noema/i),
      'Quero fazer uma prova',
    );
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText('A 20-minute exam is ready.');
    expect(screen.getByRole('link', { name: /start exam/i })).toHaveAttribute(
      'href',
      '/notebooks/nb-1/exam?examId=exam-1',
    );
  });

  it('saves an assistant turn as a note quoting the question that prompted it', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onIntent?.('explain');
        callbacks.onToken('Mitosis is cell division.');
        callbacks.onDone?.({ prompt_tokens: 10, completion_tokens: 5 });
      },
    );
    vi.mocked(api.createNote).mockResolvedValue({
      id: 'note-1',
      notebook_id: 'nb-1',
      title: 'mitosis?',
      content_md: '> mitosis?\n\nMitosis is cell division.',
      content_json: null,
      links: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });
    const user = userEvent.setup();
    await renderLoaded();

    const textarea = screen.getByPlaceholderText(/ask professor noema/i);
    await user.click(textarea);
    await user.paste('mitosis?');
    await user.click(screen.getByRole('button', { name: /^send$/i }));
    await screen.findByText('Mitosis is cell division.');

    await user.click(screen.getByRole('button', { name: /save to notes/i }));

    await screen.findByText(/saved to notes/i);
    expect(api.createNote).toHaveBeenCalledWith(
      'nb-1',
      'mitosis?',
      '> mitosis?\n\nMitosis is cell division.',
    );
    expect(screen.getByRole('link', { name: /open notebook/i })).toHaveAttribute(
      'href',
      '/notebooks/nb-1',
    );
  });

  it('shows a retryable error when saving a note fails', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onIntent?.('explain');
        callbacks.onToken('Mitosis is cell division.');
        callbacks.onDone?.({ prompt_tokens: 10, completion_tokens: 5 });
      },
    );
    vi.mocked(api.createNote).mockRejectedValueOnce(new Error('network'));
    vi.mocked(api.createNote).mockResolvedValueOnce({
      id: 'note-1',
      notebook_id: 'nb-1',
      title: 'mitosis?',
      content_md: '',
      content_json: null,
      links: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByPlaceholderText(/ask professor noema/i));
    await user.paste('mitosis?');
    await user.click(screen.getByRole('button', { name: /^send$/i }));
    await screen.findByText('Mitosis is cell division.');

    await user.click(screen.getByRole('button', { name: /save to notes/i }));
    const retry = await screen.findByRole('alert');
    expect(retry).toHaveTextContent(/could not save/i);

    await user.click(retry);
    await screen.findByText(/saved to notes/i);
    expect(api.createNote).toHaveBeenCalledTimes(2);
  });

  it('shows the monthly limit banner and drops the pending turn when blocked', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onBlocked?.({ used_units: 200, limit_units: 200 });
      },
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(screen.getByPlaceholderText(/ask professor noema/i), 'Hi');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText(/used this month's professor noema time/i);
    // No empty assistant bubble left over from the optimistic turn the
    // blocked turn never filled -- "You" is the only speaker label on screen.
    expect(screen.queryByText('NOEMA')).not.toBeInTheDocument();
  });

  it('shows a soft warning without blocking when close to the monthly limit', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onWarning?.({ used_units: 190, limit_units: 200 });
        callbacks.onIntent?.('explain');
        callbacks.onToken('Mitosis is cell division.');
        callbacks.onDone?.({ prompt_tokens: 10, completion_tokens: 5 });
      },
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(screen.getByPlaceholderText(/ask professor noema/i), 'mitosis?');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await screen.findByText('Mitosis is cell division.');
    expect(screen.getByText('10 Professor Noema replies left this month.')).toBeInTheDocument();
    expect(
      screen.queryByText(/used this month's professor noema time/i),
    ).not.toBeInTheDocument();
  });

  it('surfaces an error and leaves the composer usable when the stream fails', async () => {
    professorChat.mockImplementation(
      async (_body: unknown, callbacks: ChatCallbacks) => {
        callbacks.onError?.('The tutor is unavailable.');
      },
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(screen.getByPlaceholderText(/ask professor noema/i), 'Hi');
    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('The tutor is unavailable.'),
    );
    expect(screen.getByRole('button', { name: /^send$/i })).toBeEnabled();
  });
});
