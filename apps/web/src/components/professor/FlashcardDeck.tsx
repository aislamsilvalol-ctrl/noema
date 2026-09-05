'use client';

/**
 * The cards Mino wrote for the part just learned, inside the lesson.
 *
 * Active recall, not reading: the front is shown, the learner tries, then
 * turns the card and grades themselves with the same four ratings the review
 * screen uses. The first turn is what approves the card into their rotation
 * (server-side), and every grade is an FSRS review and a mastery event —
 * this deck and `/review` are one deck. One card at a time; a thin line
 * says how far along the small stack they are.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import type { LessonCard } from '@/lib/api';
import { useT } from '@/lib/i18n';

type Rating = 1 | 2 | 3 | 4;

const RATINGS: { value: Rating; id: 'again' | 'hard' | 'good' | 'easy' }[] = [
  { value: 1, id: 'again' },
  { value: 2, id: 'hard' },
  { value: 3, id: 'good' },
  { value: 4, id: 'easy' },
];

export function FlashcardDeck({
  cards,
  onRecall,
}: {
  cards: LessonCard[];
  onRecall: (cardId: string, rating: Rating) => void;
}) {
  const t = useT();
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const card = cards[index];
  const done = index >= cards.length;

  function rate(rating: Rating) {
    if (!card) return;
    onRecall(card.id, rating);
    setFlipped(false);
    setIndex((i) => i + 1);
  }

  return (
    <section
      aria-label={t.professor.deck.title}
      className="my-3 max-w-md rounded-lg border border-line bg-raised p-5 shadow-elevation-1"
      data-lesson-deck
    >
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-xs uppercase tracking-wide text-signal">{t.professor.deck.title}</p>
        <p className="text-xs text-ink-400">
          {done ? t.professor.deck.done : t.review.position(Math.min(index + 1, cards.length), cards.length)}
        </p>
      </div>
      <div className="mt-2 h-px w-full bg-line">
        <div
          className="h-px bg-signal transition-[width] duration-slow ease-noema"
          style={{ width: `${(Math.min(index, cards.length) / cards.length) * 100}%` }}
        />
      </div>

      {done ? (
        <p className="mt-5 text-sm text-ink-600">{t.professor.deck.doneBody}</p>
      ) : card ? (
        <>
          <button
            type="button"
            onClick={() => setFlipped(true)}
            aria-pressed={flipped}
            className="mt-4 w-full text-left [perspective:1400px] focus-visible:outline-none"
          >
            <div
              className={`grid transition-transform duration-slow ease-noema [transform-style:preserve-3d] ${
                flipped ? '[transform:rotateY(180deg)]' : ''
              }`}
            >
              <div className="col-start-1 row-start-1 rounded-md border border-line bg-surface p-5 [backface-visibility:hidden]">
                <p className="font-serif text-md text-ink-900">{card.front}</p>
                {!flipped && <p className="mt-5 text-xs text-ink-400">{t.review.tryFirst}</p>}
              </div>
              <div className="col-start-1 row-start-1 rounded-md border border-signal bg-surface p-5 [backface-visibility:hidden] [transform:rotateY(180deg)]">
                <p className="text-sm text-ink-500">{card.front}</p>
                <p className="mt-2 font-serif text-md text-ink-900">{card.back}</p>
              </div>
            </div>
          </button>
          {!flipped ? (
            <Button variant="secondary" size="sm" className="mt-3" onClick={() => setFlipped(true)}>
              {t.review.showAnswer}
            </Button>
          ) : (
            <div className="mt-3 grid grid-cols-4 gap-2" role="group" aria-label={t.review.howConfident}>
              {RATINGS.map((rating) => (
                <Button
                  key={rating.id}
                  variant={rating.id === 'good' ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => rate(rating.value)}
                  title={t.review.ratings[rating.id].meaning}
                >
                  {t.review.ratings[rating.id].label}
                </Button>
              ))}
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
