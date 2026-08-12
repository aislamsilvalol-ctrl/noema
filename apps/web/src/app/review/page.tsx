'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Shell } from '@/components/Shell';
import { ApiError, api, type DueCard, type IntervalPreview } from '@/lib/api';

type Rating = 1 | 2 | 3 | 4;

const RATINGS: {
  value: Rating;
  label: string;
  meaning: string;
  key: string;
  interval: keyof IntervalPreview;
}[] = [
  { value: 1, label: 'Again', meaning: 'could not recall', key: '1', interval: 'again' },
  { value: 2, label: 'Hard', meaning: 'with effort', key: '2', interval: 'hard' },
  { value: 3, label: 'Good', meaning: 'recalled', key: '3', interval: 'good' },
  { value: 4, label: 'Easy', meaning: 'instant', key: '4', interval: 'easy' },
];

const CONFIDENCE = [
  { value: 1, label: 'Guess' },
  { value: 2, label: 'Unsure' },
  { value: 3, label: 'Somewhat' },
  { value: 4, label: 'Confident' },
  { value: 5, label: 'Certain' },
];

function formatInterval(days: number): string {
  if (days < 1) return `${Math.max(Math.round(days * 24 * 60), 1)}m`;
  if (days < 30) return `${Math.round(days)}d`;
  if (days < 365) return `${Math.round(days / 30)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

export default function ReviewPage() {
  const router = useRouter();
  const [queue, setQueue] = useState<DueCard[]>([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(0);
  const [pendingRating, setPendingRating] = useState<Rating | null>(null);
  const shownAt = useRef<number>(Date.now());

  const card = queue[index];

  const load = useCallback(async () => {
    try {
      setQueue(await api.dueCards());
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not load your cards.');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    shownAt.current = Date.now();
  }, [index]);

  const advance = useCallback(() => {
    setRevealed(false);
    setPendingRating(null);
    setDone((count) => count + 1);
    setIndex((current) => current + 1);
  }, []);

  const submit = useCallback(
    async (rating: Rating, confidence?: number) => {
      if (!card) return;
      const elapsed = Date.now() - shownAt.current;

      // Advance immediately: waiting on the network between cards is what turns a
      // twenty-card session into a chore.
      advance();
      try {
        await api.review(card.id, rating, elapsed, confidence);
      } catch {
        setError('A review could not be saved. It will need answering again.');
      }
    },
    [card, advance],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!card) return;
      if (event.key === ' ' && !revealed) {
        event.preventDefault();
        setRevealed(true);
        return;
      }
      if (!revealed || pendingRating !== null) return;

      const rating = RATINGS.find((r) => r.key === event.key);
      if (rating) {
        event.preventDefault();
        setPendingRating(rating.value);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [card, revealed, pendingRating]);

  if (loading) {
    return (
      <Shell>
        <p className="text-sm text-ink-500">Loading…</p>
      </Shell>
    );
  }

  if (!card) {
    return (
      <Shell>
        <div className="mx-auto max-w-reading pt-16">
          <h1 className="font-display text-2xl text-ink-900">
            {done > 0 ? 'Session complete.' : 'Nothing due.'}
          </h1>
          <p className="mt-3 text-base text-ink-600">
            {done > 0
              ? `${done} ${done === 1 ? 'card' : 'cards'} reviewed. The next ones are scheduled for when you are about to forget them.`
              : 'No cards are due right now. Come back when something is — reviewing early does not help you remember longer.'}
          </p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mx-auto flex min-h-[70vh] max-w-reading flex-col pt-8">
        <div className="flex items-baseline justify-between text-xs text-ink-400">
          <span>
            {done + 1} of {queue.length}
          </span>
          {card.state === 'new' && <span>new</span>}
        </div>

        {error && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {error}
          </p>
        )}

        <div className="flex flex-1 flex-col justify-center py-12">
          <p className="font-serif text-lg text-ink-900">{card.front_md}</p>

          {revealed && (
            <div className="mt-8 animate-fade-up border-t border-line pt-8">
              <p className="whitespace-pre-wrap font-serif text-md text-ink-700">
                {card.back_md}
              </p>
            </div>
          )}
        </div>

        {!revealed ? (
          <button
            type="button"
            onClick={() => setRevealed(true)}
            className="w-full rounded-md border border-line py-3 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            Show answer <kbd className="ml-2 font-mono text-xs text-ink-400">space</kbd>
          </button>
        ) : pendingRating === null ? (
          <div className="grid grid-cols-4 gap-2">
            {RATINGS.map((rating) => (
              <button
                key={rating.value}
                type="button"
                onClick={() => setPendingRating(rating.value)}
                className="rounded-md border border-line px-2 py-3 text-center transition-colors duration-state hover:border-ink-400"
              >
                <span className="block text-sm text-ink-900">{rating.label}</span>
                {/* The cost of each answer, so the choice is informed rather than
                    a guess about what the scheduler will do with it. */}
                <span className="mt-0.5 block font-mono text-xs text-accent">
                  {formatInterval(card.preview[rating.interval])}
                </span>
                <span className="mt-0.5 block text-xs text-ink-400">{rating.meaning}</span>
                <kbd className="mt-1 block font-mono text-[10px] text-ink-400">
                  {rating.key}
                </kbd>
              </button>
            ))}
          </div>
        ) : (
          <div>
            {/* Asked after the rating, never before: knowing how sure you were is
                only meaningful once you have committed to an answer. */}
            <p className="mb-2 text-xs text-ink-500">How confident were you?</p>
            <div className="grid grid-cols-6 gap-2">
              {CONFIDENCE.map((level) => (
                <button
                  key={level.value}
                  type="button"
                  onClick={() => void submit(pendingRating, level.value)}
                  className="rounded-md border border-line px-1 py-2 text-xs text-ink-700 transition-colors duration-state hover:border-ink-400"
                >
                  {level.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => void submit(pendingRating)}
                className="rounded-md px-1 py-2 text-xs text-ink-400 transition-colors duration-state hover:text-ink-900"
              >
                Skip
              </button>
            </div>
          </div>
        )}

        <p className="mt-6 text-center text-xs text-ink-400">
          {revealed
            ? 'Rate honestly — the schedule is only as good as the grade you give it.'
            : 'Try to recall it before revealing. The effort is the point.'}
        </p>
      </div>
    </Shell>
  );
}
