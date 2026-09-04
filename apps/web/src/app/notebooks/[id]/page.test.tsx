// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import NotebookPage from './page';
import { ApiError, type Note, type Notebook } from '@/lib/api';

// A fresh object from useRouter() on every render would give the page's
// `load` useCallback a new identity each time, retriggering its mount effect
// in a loop -- Next's real useRouter() is referentially stable, so the mock
// has to be too (see the sibling cards/page.test.tsx for where this bit).
const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'nb-1' }),
  useRouter: () => router,
  usePathname: () => '/notebooks/nb-1',
}));

// This page's rail/sidebar components each do their own thing on mount
// (chat, source polling, dynamic import); none of that is what this test is
// about, so they're stubbed out to isolate the note-list/InlineCreate logic.
vi.mock('@/components/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/TutorPanel', () => ({ TutorPanel: () => null }));
vi.mock('@/components/SourceList', () => ({ SourceList: () => null }));
vi.mock('@/components/AnkiImport', () => ({ AnkiImport: () => null }));
vi.mock('@/components/editor/NoteEditor', () => ({ NoteEditor: () => null }));

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

const existingNote: Note = {
  id: 'note-1',
  notebook_id: 'nb-1',
  title: 'Mitosis',
  content_md: 'Cells divide.',
  content_json: null,
  links: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const newNote: Note = {
  id: 'note-2',
  notebook_id: 'nb-1',
  title: 'Meiosis',
  content_md: '',
  content_json: null,
  links: [],
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const { createNote } = vi.hoisted(() => ({ createNote: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      notebook: vi.fn(),
      notes: vi.fn(),
      createNote,
      updateNote: vi.fn(),
      // The home's courtesies: no open lesson, nothing due.
      latestSession: vi.fn().mockResolvedValue(null),
      dueCards: vi.fn().mockResolvedValue([]),
    },
  };
});

import { api } from '@/lib/api';

afterEach(() => {
  vi.mocked(api.notebook).mockReset();
  vi.mocked(api.notes).mockReset();
  createNote.mockReset();
});

async function renderLoaded() {
  vi.mocked(api.notebook).mockResolvedValue(notebook);
  vi.mocked(api.notes).mockResolvedValue({ items: [existingNote], next_cursor: null });

  render(<NotebookPage />);
  await screen.findByText(existingNote.title);
}

describe('NotebookPage addNote', () => {
  it('adds the note to the list when creation succeeds', async () => {
    createNote.mockResolvedValue(newNote);
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: 'New note' }));
    await user.type(screen.getByLabelText('Note title'), newNote.title);
    await user.click(screen.getByRole('button', { name: 'Create' }));

    // In the list, and — because a new note opens for writing — as the
    // editor's heading too.
    await waitFor(() => expect(screen.getAllByText(newNote.title).length).toBeGreaterThan(0));
    expect(screen.getByRole('button', { name: /Meiosis/ })).toHaveAttribute('aria-current', 'true');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces an error and keeps the create dialog usable when creation fails', async () => {
    // Regression: addNote() had no try/catch at all, unlike load() and the
    // autosave handler in this same file (and unlike the sibling InlineCreate
    // call site in library/page.tsx's createNotebook) -- a rejected
    // createNote() call became an unhandled promise rejection with no
    // user-facing feedback at all.
    createNote.mockRejectedValue(
      new ApiError({ type: 'about:blank', title: 'Server Error', status: 500, detail: 'boom' }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: 'New note' }));
    await user.type(screen.getByLabelText('Note title'), 'Meiosis');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    expect(screen.queryByText('Meiosis')).not.toBeInTheDocument();
  });
});
