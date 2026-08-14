'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Card, type DueCard, type Notebook } from '@/lib/api';

export default function CardsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const notebookId = params.id;

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [pending, setPending] = useState<DueCard[]>([]);
  const [approved, setApproved] = useState<DueCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, { front: string; back: string }>>({});

  const load = useCallback(async () => {
    try {
      const [nb, pendingCards, approvedCards] = await Promise.all([
        api.notebook(notebookId),
        api.pendingCards(notebookId),
        api.dueCards(notebookId, 100),
      ]);
      setNotebook(nb);
      setPending(pendingCards);
      setApproved(approvedCards);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not load cards.');
    }
  }, [notebookId, router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const drafted = await api.generateCards(notebookId);
      setPending((current) => [...drafted.map(toDue), ...current]);
      if (drafted.length === 0) {
        setError('Nothing new to draft. Add material, or the model found no card worth making.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function approve(card: DueCard) {
    const edits = editing[card.id];
    try {
      // Edits are saved before approval, so what enters the rotation is what the
      // person actually read and agreed to.
      if (edits && (edits.front !== card.front_md || edits.back !== card.back_md)) {
        await api.updateCard(card.id, { front_md: edits.front, back_md: edits.back });
      }
      const saved = await api.approveCard(card.id);
      setPending((current) => current.filter((c) => c.id !== card.id));
      setApproved((current) => [{ ...card, ...saved }, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not approve that card.');
    }
  }

  async function discard(card: DueCard, from: 'pending' | 'approved') {
    await api.deleteCard(card.id);
    const setter = from === 'pending' ? setPending : setApproved;
    setter((current) => current.filter((c) => c.id !== card.id));
  }

  function edit(card: DueCard, field: 'front' | 'back', value: string) {
    setEditing((current) => ({
      ...current,
      [card.id]: {
        front: field === 'front' ? value : (current[card.id]?.front ?? card.front_md),
        back: field === 'back' ? value : (current[card.id]?.back ?? card.back_md),
      },
    }));
  }

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl text-ink-900">Cards</h1>
          <Link
            href={`/notebooks/${notebookId}`}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {notebook?.title ?? 'Notebook'} ←
          </Link>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
        >
          {busy ? 'Drafting…' : 'Draft from material'}
        </button>
      </header>

      {error && (
        <p role="alert" className="mt-4 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      <section className="mt-10 max-w-reading">
        <h2 className="text-lg text-ink-900">
          Waiting for you {pending.length > 0 && <span className="text-ink-400">({pending.length})</span>}
        </h2>
        <p className="mt-2 text-sm text-ink-600">
          Drafted cards do not enter your rotation until you have read them. Spaced
          repetition is very good at making a wrong card permanent — edit anything
          that is off before approving it.
        </p>

        {pending.length === 0 ? (
          <p className="mt-6 text-sm text-ink-500">Nothing waiting.</p>
        ) : (
          <ul className="mt-6 space-y-6">
            {pending.map((card) => (
              <li key={card.id} className="border-t border-line pt-4">
                <textarea
                  value={editing[card.id]?.front ?? card.front_md}
                  onChange={(event) => edit(card, 'front', event.target.value)}
                  rows={2}
                  aria-label="Question"
                  className="w-full resize-none bg-transparent font-serif text-md text-ink-900 outline-none"
                />
                <textarea
                  value={editing[card.id]?.back ?? card.back_md}
                  onChange={(event) => edit(card, 'back', event.target.value)}
                  rows={2}
                  aria-label="Answer"
                  className="mt-2 w-full resize-none border-l-2 border-line bg-transparent pl-3 font-serif text-base text-ink-600 outline-none"
                />
                <div className="mt-3 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void approve(card)}
                    className="rounded-md bg-ink-900 px-3 py-1.5 text-xs font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => void discard(card, 'pending')}
                    className="text-xs text-ink-500 transition-colors duration-state hover:text-critical"
                  >
                    Discard
                  </button>
                  {card.concept_id === null && (
                    <span className="text-xs text-ink-400">no concept matched</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-16 max-w-reading">
        <h2 className="text-lg text-ink-900">
          In rotation {approved.length > 0 && <span className="text-ink-400">({approved.length})</span>}
        </h2>

        {approved.length === 0 ? (
          <p className="mt-4 text-sm text-ink-500">No cards yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {approved.map((card) => (
              <li key={card.id} className="flex items-baseline justify-between gap-4 py-3">
                <span className="min-w-0 flex-1 truncate text-sm text-ink-800">
                  {card.front_md}
                </span>
                <span className="shrink-0 text-xs text-ink-400">
                  {card.reps === 0 ? 'new' : `${card.reps} reviews`}
                </span>
                <button
                  type="button"
                  onClick={() => void discard(card, 'approved')}
                  className="shrink-0 text-xs text-ink-500 transition-colors duration-state hover:text-critical"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Shell>
  );
}

/** A freshly drafted card has no schedule yet; the list only needs the shape. */
function toDue(card: Card): DueCard {
  return {
    ...card,
    due_at: null,
    state: 'new',
    reps: 0,
    preview: { again: 0, hard: 0, good: 0, easy: 0 },
  };
}
