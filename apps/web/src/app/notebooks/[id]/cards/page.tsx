'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Card, type DueCard, type Notebook } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function CardsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const notebookId = params.id;

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [pending, setPending] = useState<DueCard[]>([]);
  const [approved, setApproved] = useState<DueCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, { front: string; back: string }>>({});
  const [newFront, setNewFront] = useState('');
  const [newBack, setNewBack] = useState('');
  const [creating, setCreating] = useState(false);

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
      setError(err instanceof Error ? err.message : t.cards.couldNotLoad);
    }
  }, [notebookId, router, t]);

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
        setError(t.cards.nothingToDraft);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t.cards.generationFailed);
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
      setError(err instanceof Error ? err.message : t.cards.couldNotApprove);
    }
  }

  async function discard(card: DueCard, from: 'pending' | 'approved') {
    await api.deleteCard(card.id);
    const setter = from === 'pending' ? setPending : setApproved;
    setter((current) => current.filter((c) => c.id !== card.id));
  }

  async function createOwnCard(event: FormEvent) {
    event.preventDefault();
    if (!newFront.trim() || !newBack.trim()) return;

    setCreating(true);
    setError(null);
    try {
      // A card someone wrote is approved by writing it — no drafted-and-waiting
      // step, unlike an AI-generated one. It goes straight into rotation.
      const card = await api.createCard(notebookId, newFront.trim(), newBack.trim());
      setApproved((current) => [toDue(card), ...current]);
      setNewFront('');
      setNewBack('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t.cards.couldNotCreate);
    } finally {
      setCreating(false);
    }
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
          <h1 className="font-display text-2xl text-ink-900">{t.cards.title}</h1>
          <Link
            href={`/notebooks/${notebookId}`}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {notebook?.title ?? t.notebook.fallbackTitle} ←
          </Link>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
        >
          {busy ? t.cards.drafting : t.cards.draft}
        </button>
      </header>

      {error && (
        <p role="alert" className="mt-4 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      <section className="mt-8 max-w-reading">
        <h2 className="text-lg text-ink-900">{t.cards.writeOwn}</h2>
        <form onSubmit={(event) => void createOwnCard(event)} className="mt-3 space-y-2">
          <textarea
            value={newFront}
            onChange={(event) => setNewFront(event.target.value)}
            placeholder={t.cards.frontPlaceholder}
            rows={2}
            aria-label={t.cards.question}
            className="w-full resize-none rounded-md border border-line bg-transparent p-2 font-serif text-md text-ink-900 outline-none"
          />
          <textarea
            value={newBack}
            onChange={(event) => setNewBack(event.target.value)}
            placeholder={t.cards.backPlaceholder}
            rows={2}
            aria-label={t.cards.answer}
            className="w-full resize-none rounded-md border border-line bg-transparent p-2 font-serif text-base text-ink-700 outline-none"
          />
          <button
            type="submit"
            disabled={creating || !newFront.trim() || !newBack.trim()}
            className="rounded-md bg-ink-900 px-3 py-1.5 text-xs font-medium text-ink-50 transition-opacity duration-state hover:opacity-90 disabled:opacity-50"
          >
            {creating ? t.cards.adding : t.cards.addCard}
          </button>
        </form>
      </section>

      <section className="mt-10 max-w-reading">
        <h2 className="text-lg text-ink-900">
          {t.cards.waiting}{' '}
          {pending.length > 0 && <span className="text-ink-400">({pending.length})</span>}
        </h2>
        <p className="mt-2 text-sm text-ink-600">
          {t.cards.waitingLede}
        </p>

        {pending.length === 0 ? (
          <p className="mt-6 text-sm text-ink-500">{t.cards.nothingWaiting}</p>
        ) : (
          <ul className="mt-6 space-y-6">
            {pending.map((card) => (
              <li key={card.id} className="border-t border-line pt-4">
                <textarea
                  value={editing[card.id]?.front ?? card.front_md}
                  onChange={(event) => edit(card, 'front', event.target.value)}
                  rows={2}
                  aria-label={t.cards.question}
                  className="w-full resize-none bg-transparent font-serif text-md text-ink-900 outline-none"
                />
                <textarea
                  value={editing[card.id]?.back ?? card.back_md}
                  onChange={(event) => edit(card, 'back', event.target.value)}
                  rows={2}
                  aria-label={t.cards.answer}
                  className="mt-2 w-full resize-none border-l-2 border-line bg-transparent pl-3 font-serif text-base text-ink-600 outline-none"
                />
                <div className="mt-3 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void approve(card)}
                    className="rounded-md bg-ink-900 px-3 py-1.5 text-xs font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
                  >
                    {t.cards.approve}
                  </button>
                  <button
                    type="button"
                    onClick={() => void discard(card, 'pending')}
                    className="text-xs text-ink-500 transition-colors duration-state hover:text-critical"
                  >
                    {t.cards.discard}
                  </button>
                  {card.concept_id === null && (
                    <span className="text-xs text-ink-400">{t.cards.noConcept}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-16 max-w-reading">
        <h2 className="text-lg text-ink-900">
          {t.cards.inRotation}{' '}
          {approved.length > 0 && <span className="text-ink-400">({approved.length})</span>}
        </h2>

        {approved.length === 0 ? (
          <p className="mt-4 text-sm text-ink-500">{t.cards.noCards}</p>
        ) : (
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {approved.map((card) => (
              <li key={card.id} className="flex items-baseline justify-between gap-4 py-3">
                <span className="min-w-0 flex-1 truncate text-sm text-ink-800">
                  {card.front_md}
                </span>
                <span className="shrink-0 text-xs text-ink-400">
                  {card.reps === 0 ? t.cards.newCard : t.cards.reviews(card.reps)}
                </span>
                <button
                  type="button"
                  onClick={() => void discard(card, 'approved')}
                  className="shrink-0 text-xs text-ink-500 transition-colors duration-state hover:text-critical"
                >
                  {t.common.delete}
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
