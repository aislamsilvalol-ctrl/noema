'use client';

/**
 * Reviews: a card you turn over, and an honest grade.
 *
 * The scheduling is untouched — the same four ratings with their interval
 * previews, the same confidence step asked only after a rating, the same
 * keyboard (space, 1–4), the same offline queue. What changed is that the
 * card is now an object: it turns over when revealed (a real rotation,
 * natural rather than showy, and none at all under reduced motion), the
 * targets are big enough for a thumb, a thin line shows how far the session
 * has come, and Mino sits small at the top — reviewing, with one short
 * spring when a card came back easily. No confetti.
 */

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Mino, type MinoState } from '@/components/mino/Mino';
import { Shell } from '@/components/Shell';
import { Button } from '@/components/ui/Button';
import { Notice } from '@/components/ui/Notice';
import { ApiError, api, cardImageUrl, type DueCard, type IntervalPreview } from '@/lib/api';
import { clozeBack, clozeFront, hasDeletions } from '@/lib/cloze';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';
import { offlineQueue, type QueuedReview } from '@/lib/offlineQueue';

type Rating = 1 | 2 | 3 | 4;

const RATINGS: {
  value: Rating;
  id: 'again' | 'hard' | 'good' | 'easy';
  key: string;
  interval: keyof IntervalPreview;
}[] = [
  { value: 1, id: 'again', key: '1', interval: 'again' },
  { value: 2, id: 'hard', key: '2', interval: 'hard' },
  { value: 3, id: 'good', key: '3', interval: 'good' },
  { value: 4, id: 'easy', key: '4', interval: 'easy' },
];

// How long Mino's spring lasts after an easy recall. Shorter than the time
// it takes to read the confidence row, so it never competes with it.
const CELEBRATE_MS = 900;

function formatInterval(days: number): string {
  if (days < 1) return `${Math.max(Math.round(days * 24 * 60), 1)}m`;
  if (days < 30) return `${Math.round(days)}d`;
  if (days < 365) return `${Math.round(days / 30)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

export default function ReviewPage() {
  const router = useRouter();
  const t = useT();
  const [queue, setQueue] = useState<DueCard[]>([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(0);
  const [pendingRating, setPendingRating] = useState<Rating | null>(null);
  const [queuedCount, setQueuedCount] = useState(0);
  const [mino, setMino] = useState<MinoState>('reviewing');
  const shownAt = useRef<number>(Date.now());
  const celebrateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const card = queue[index];

  const flushQueue = useCallback(async () => {
    try {
      await offlineQueue.flush((batch) => api.reviewBatch(batch));
    } catch {
      // Still offline, or the server rejected the batch — leave it queued
      // and try again on the next successful review or `online` event.
    } finally {
      setQueuedCount(offlineQueue.size());
    }
  }, []);

  useEffect(() => {
    setQueuedCount(offlineQueue.size());
    void flushQueue();
    const onOnline = () => void flushQueue();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, [flushQueue]);

  const load = useCallback(async () => {
    try {
      setQueue(await api.dueCards());
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(humanError(err, t, 'load'));
    } finally {
      setLoading(false);
    }
  }, [router, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    shownAt.current = Date.now();
  }, [index]);

  useEffect(
    () => () => {
      if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
    },
    [],
  );

  const advance = useCallback(() => {
    setRevealed(false);
    setPendingRating(null);
    setDone((count) => count + 1);
    setIndex((current) => current + 1);
  }, []);

  // The grade is the learner's; Mino only reacts to it. Good and Easy earn
  // one short spring, then back to work; Again gets focus, not a face.
  const rate = useCallback((rating: Rating) => {
    setPendingRating(rating);
    if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
    if (rating >= 3) {
      setMino('celebrating');
      celebrateTimer.current = setTimeout(() => setMino('reviewing'), CELEBRATE_MS);
    } else {
      setMino(rating === 1 ? 'focused' : 'reviewing');
    }
  }, []);

  const submit = useCallback(
    async (rating: Rating, confidence?: number) => {
      if (!card) return;
      const elapsed = Date.now() - shownAt.current;
      const entry: QueuedReview = {
        card_id: card.id,
        rating,
        elapsed_ms: elapsed,
        confidence,
      };

      // Advance immediately: waiting on the network between cards is what turns a
      // twenty-card session into a chore.
      advance();
      try {
        await api.review(entry.card_id, entry.rating, entry.elapsed_ms, entry.confidence);
        // A request just reached the server — a good moment to flush any
        // backlog too, in case the `online` event never fired for it.
        if (offlineQueue.size() > 0) void flushQueue();
      } catch (err) {
        if (err instanceof ApiError) {
          // The server was reached and rejected the request — retrying the
          // same payload later would not help, unlike a network failure.
          setError(t.review.saveFailed);
          return;
        }
        offlineQueue.enqueue(entry);
        setQueuedCount(offlineQueue.size());
      }
    },
    [card, advance, t, flushQueue],
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
        rate(rating.value);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [card, revealed, pendingRating, rate]);

  if (loading) {
    return (
      <Shell>
        <p className="text-sm text-ink-500">{t.common.loading}</p>
      </Shell>
    );
  }

  if (!card) {
    return (
      <Shell>
        <Notice
          kind="empty"
          title={done > 0 ? t.review.sessionComplete : t.review.nothingDue}
          body={done > 0 ? t.review.reviewedCount(done) : t.review.nothingDueBody}
          mino={<Mino state={done > 0 ? 'celebrating' : 'sleeping'} size="lg" />}
          action={{ label: t.nav.home, href: '/today' }}
        />
        {queuedCount > 0 && (
          <p role="status" className="mt-4 text-xs text-ink-500">
            {t.review.queued(queuedCount)}
          </p>
        )}
      </Shell>
    );
  }

  const progress = queue.length > 0 ? (done / queue.length) * 100 : 0;

  // A cloze card stored raw (imported before the importer rendered them) is
  // still reviewable: blank the deletions on the front, reveal them behind.
  const raw = !card.back_md && hasDeletions(card.front_md);
  const front = raw ? clozeFront(card.front_md) : card.front_md;
  const back = raw ? clozeBack(card.front_md) : card.back_md;

  return (
    <Shell>
      <div className="mx-auto flex min-h-[70vh] max-w-reading flex-col pt-2">
        <div className="flex items-center gap-3">
          <Mino state={mino} size="sm" />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between text-xs text-ink-500">
              <span>{t.review.position(done + 1, queue.length)}</span>
              {card.state === 'new' && <span className="text-signal">{t.review.newTag}</span>}
            </div>
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={queue.length}
              aria-valuenow={done}
              className="mt-1.5 h-0.5 w-full overflow-hidden rounded-full bg-sunken"
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-normal ease-noema"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>

        {error && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {error}
          </p>
        )}

        {queuedCount > 0 && (
          <p role="status" className="mt-4 text-xs text-ink-500">
            {t.review.queued(queuedCount)}
          </p>
        )}

        {/* The card. Both faces occupy the same grid cell so the object is as
            tall as its taller side and nothing jumps when it turns. The turn
            is a rotation on the Y axis; `globals.css` collapses it under
            reduced motion, leaving a plain swap. */}
        <div className="flex flex-1 flex-col justify-center py-8">
          <button
            type="button"
            onClick={() => !revealed && setRevealed(true)}
            aria-label={revealed ? undefined : t.review.showAnswer}
            className="w-full text-left [perspective:1400px] focus-visible:outline-none"
          >
            <div
              className={`grid transition-transform duration-slow ease-noema [transform-style:preserve-3d] ${
                revealed ? '[transform:rotateY(180deg)]' : ''
              }`}
            >
              <div className="col-start-1 row-start-1 rounded-lg border border-line bg-raised p-6 shadow-elevation-1 [backface-visibility:hidden] sm:p-8">
                {card.has_image && (
                  // A session cookie authenticates this request; next/image's own
                  // remote loader does not send one, so a plain <img> is correct here.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={cardImageUrl(card.id)}
                    alt={t.review.cardImageAlt}
                    className="mb-6 max-h-[40vh] w-full rounded-md border border-line object-contain"
                  />
                )}
                <p className="font-serif text-lg leading-relaxed text-ink-900">{front}</p>
                {!revealed && (
                  <p className="mt-8 text-xs text-ink-400">
                    {t.review.showAnswer}{' '}
                    <kbd className="ml-1 font-mono text-[10px] text-ink-400">{t.review.space}</kbd>
                  </p>
                )}
              </div>
              <div
                aria-hidden={!revealed}
                className="col-start-1 row-start-1 rounded-lg border border-signal bg-raised p-6 shadow-elevation-2 [backface-visibility:hidden] [transform:rotateY(180deg)] sm:p-8"
              >
                <p className="text-sm text-ink-500">{front}</p>
                <p className="mt-4 whitespace-pre-wrap font-serif text-md leading-relaxed text-ink-900">
                  {back}
                </p>
              </div>
            </div>
          </button>
        </div>

        {!revealed ? (
          <Button variant="primary" size="lg" className="w-full" onClick={() => setRevealed(true)}>
            {t.review.showAnswer}
          </Button>
        ) : pendingRating === null ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {/* 2 columns below `sm`: each button already carries four lines
                (label, interval, meaning, shortcut) and a phone-width quarter
                column left no room for them. */}
            {RATINGS.map((rating) => (
              <button
                key={rating.value}
                type="button"
                onClick={() => rate(rating.value)}
                className="rounded-md border border-line bg-raised px-2 py-4 text-center transition-colors duration-fast hover:border-ink-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal focus-visible:ring-offset-2"
              >
                <span className="block text-sm font-medium text-ink-900">
                  {t.review.ratings[rating.id].label}
                </span>
                {/* The cost of each answer, so the choice is informed rather than
                    a guess about what the scheduler will do with it. */}
                <span className="mt-0.5 block font-mono text-xs text-signal">
                  {formatInterval(card.preview[rating.interval])}
                </span>
                <span className="mt-0.5 block text-xs text-ink-500">
                  {t.review.ratings[rating.id].meaning}
                </span>
                <kbd className="mt-1 block font-mono text-[10px] text-ink-400">{rating.key}</kbd>
              </button>
            ))}
          </div>
        ) : (
          <div>
            {/* Asked after the rating, never before: knowing how sure you were is
                only meaningful once you have committed to an answer. */}
            <p className="mb-2 text-xs text-ink-500">{t.review.howConfident}</p>
            {/* 3 columns below `sm`: "Somewhat" and "Confident" have no room
                to stay on one line split six ways on a phone. */}
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {t.review.confidence.map((label, i) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => void submit(pendingRating, i + 1)}
                  className="rounded-md border border-line bg-raised px-1 py-3 text-xs text-ink-800 transition-colors duration-fast hover:border-ink-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal focus-visible:ring-offset-2"
                >
                  {label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => void submit(pendingRating)}
                className="rounded-md px-1 py-3 text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
              >
                {t.common.skip}
              </button>
            </div>
          </div>
        )}

        <p className="mt-6 text-center text-xs text-ink-400">
          {revealed ? t.review.rateHonestly : t.review.tryFirst}
        </p>
      </div>
    </Shell>
  );
}
