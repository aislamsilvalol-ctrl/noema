'use client';

/**
 * The Focus mode home: one question, three answers.
 *
 * WHAT DO I DO NOW? — Continue (~N min), a quick recall (2 min: the journey's
 * due cards, right here), or start something new. Everything else on the home
 * screen stays below and secondary. No percentages, no streaks; momentum is
 * a plain count of what landed today.
 */

import { useState } from 'react';
import { FlashcardDeck } from '@/components/professor/FlashcardDeck';
import { ButtonLink, Button } from '@/components/ui/Button';
import { api, type DueCard, type Journey } from '@/lib/api';
import { useT } from '@/lib/i18n';

export function FocusHome({
  journey,
  minutes,
  due,
}: {
  journey: Journey | null;
  minutes: number;
  due: number;
}) {
  const t = useT();
  const copy = t.today.focus;
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [loadingCards, setLoadingCards] = useState(false);

  async function quickRecall() {
    if (!journey) return;
    setLoadingCards(true);
    try {
      setCards(await api.journeyDueCards(journey.id, 5));
    } catch {
      setCards([]);
    } finally {
      setLoadingCards(false);
    }
  }

  const concept = journey?.current.concept;
  return (
    <div data-focus-home>
      <p className="text-xs uppercase tracking-wide text-signal">{copy.question}</p>
      <div className="mt-3 grid gap-3">
        {journey ? (
          <ButtonLink href="/chat" variant="primary" size="lg" className="justify-between">
            <span>{copy.continueFor(minutes)}</span>
            <span className="text-sm opacity-80">{concept ? concept : journey.subject}</span>
          </ButtonLink>
        ) : (
          <ButtonLink href="/learn/new" variant="primary" size="lg">
            {copy.justStart}
          </ButtonLink>
        )}
        {journey && (
          <Button
            variant="secondary"
            size="lg"
            onClick={() => void quickRecall()}
            busy={loadingCards ? t.common.loading : undefined}
            className="justify-between"
          >
            <span>{copy.quickRecall}</span>
            <span className="text-sm text-ink-500">{copy.quickRecallTime}</span>
          </Button>
        )}
        <ButtonLink href="/learn/new" variant="ghost" size="lg">
          {copy.startNew}
        </ButtonLink>
      </div>
      {journey && (
        <p className="mt-3 text-xs text-ink-500">
          {copy.momentum(journey.momentum.mastered_today, journey.momentum.events_today)}
          {due > 0 ? ` · ${t.today.reviewsDue(due)}` : ''}
        </p>
      )}
      {cards !== null &&
        (cards.length > 0 ? (
          <FlashcardDeck
            cards={cards.map((c) => ({
              id: c.id,
              front: c.front_md,
              back: c.back_md,
              concept: c.concept_name ?? '',
            }))}
            onRecall={(id, rating) => {
              if (journey) void api.recallCard(journey.id, id, rating).catch(() => undefined);
            }}
          />
        ) : (
          <p className="mt-3 text-sm text-ink-600">{copy.nothingToRecall}</p>
        ))}
    </div>
  );
}
