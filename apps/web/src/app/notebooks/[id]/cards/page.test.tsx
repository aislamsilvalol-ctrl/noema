// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CardsPage from './page';
import { ApiError, type Card, type DueCard, type Notebook } from '@/lib/api';

// A fresh object from useRouter() on every render would give the page's
// `load` useCallback a new identity each time, retriggering its effect in
// an infinite fetch loop -- Next's real useRouter() is referentially
// stable, so the mock has to be too.
const push = vi.fn();
const router = { push };
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'nb-1' }),
  useRouter: () => router,
  usePathname: () => '/notebooks/nb-1/cards',
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

const approvedCard: Card = {
  id: 'card-1',
  notebook_id: 'nb-1',
  concept_id: null,
  type: 'basic',
  front_md: 'What is mitosis?',
  back_md: 'Cell division producing two identical daughter cells.',
  origin: 'user',
  approved_at: '2026-01-01T00:00:00Z',
  suspended_at: null,
  has_image: false,
  source_chunk_ids: [],
  created_at: '2026-01-01T00:00:00Z',
};

const approvedDueCard: DueCard = {
  ...approvedCard,
  due_at: null,
  state: 'new',
  reps: 0,
  preview: { again: 0, hard: 0, good: 0, easy: 0 },
};

const { deleteCard } = vi.hoisted(() => ({ deleteCard: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    createImageCard: vi.fn(),
    api: {
      notebook: vi.fn(),
      pendingCards: vi.fn(),
      dueCards: vi.fn(),
      concepts: vi.fn(),
      deleteCard,
      generateCards: vi.fn(),
      approveCard: vi.fn(),
      updateCard: vi.fn(),
      createCard: vi.fn(),
      createCloze: vi.fn(),
    },
  };
});

import { api } from '@/lib/api';

afterEach(() => {
  vi.mocked(api.notebook).mockReset();
  vi.mocked(api.pendingCards).mockReset();
  vi.mocked(api.dueCards).mockReset();
  vi.mocked(api.concepts).mockReset();
  deleteCard.mockReset();
});

async function renderLoaded() {
  vi.mocked(api.notebook).mockResolvedValue(notebook);
  vi.mocked(api.pendingCards).mockResolvedValue([]);
  vi.mocked(api.dueCards).mockResolvedValue([approvedDueCard]);
  vi.mocked(api.concepts).mockResolvedValue([]);

  render(<CardsPage />);
  await screen.findByText(approvedCard.front_md);
}

describe('CardsPage discard', () => {
  it('removes the card from the list when the delete call succeeds', async () => {
    deleteCard.mockResolvedValue(undefined);
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: /delete/i }));

    await waitFor(() =>
      expect(screen.queryByText(approvedCard.front_md)).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces an error and keeps the card when the delete call fails', async () => {
    // Regression: discard() used to have no try/catch at all, unlike every
    // other async handler on this page (generate/approve/createOwnCard) --
    // a rejected deleteCard() call became an unhandled promise rejection
    // instead of a message the user could see.
    deleteCard.mockRejectedValue(
      new ApiError({ type: 'about:blank', title: 'Server Error', status: 500, detail: 'boom' }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(screen.getByRole('button', { name: /delete/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    expect(screen.getByText(approvedCard.front_md)).toBeInTheDocument();
  });
});
