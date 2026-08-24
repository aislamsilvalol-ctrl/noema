/**
 * A review taken with no network survives the tab: it is written to
 * `localStorage` immediately and flushed through `POST /reviews/batch` the
 * next time a submit succeeds or the browser reports `online`. The review
 * page decides *when* to flush; this module only owns *what's queued*.
 *
 * Reviews are evidence (see `noema/study/review.py`'s own module docstring —
 * "the evidence row is written; it is the only durable fact here") — losing one
 * because a train went through a tunnel is a worse failure than a moment of
 * stale storage, so this fails toward keeping the queue over losing it.
 */

const STORAGE_KEY = 'noema.review-queue.v1';

// Matches the backend's own cap (`MAX_BATCH` in `noema/api/v1/study.py`) —
// flushing chunks it, so a long offline session still gets through.
const MAX_BATCH = 200;

export interface QueuedReview {
  card_id: string;
  rating: 1 | 2 | 3 | 4;
  elapsed_ms: number;
  confidence?: number;
}

function readQueue(): QueuedReview[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as QueuedReview[]) : [];
  } catch {
    // Private browsing can throw on access rather than just returning null,
    // and a corrupt value is no better than an empty queue.
    return [];
  }
}

function writeQueue(queue: QueuedReview[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue));
  } catch {
    // Storage full or unavailable: the queue stops persisting across a reload,
    // but review() still returns normally and the in-memory session continues.
  }
}

export const offlineQueue = {
  size(): number {
    return readQueue().length;
  },

  enqueue(review: QueuedReview): void {
    writeQueue([...readQueue(), review]);
  },

  /**
   * Submits everything currently queued, in chunks of at most `MAX_BATCH`, and
   * removes only what was actually submitted. A review enqueued while this is
   * in flight is appended after the snapshot this call took, so it survives
   * even though the snapshot's own entries get cleared first.
   *
   * Throws (and leaves the queue as it was for that chunk onward) if a chunk
   * fails partway — still offline, or the server rejected it — so a caller
   * that catches and ignores the error is exactly as safe as never calling
   * flush at all.
   */
  async flush(submitBatch: (reviews: QueuedReview[]) => Promise<unknown>): Promise<number> {
    const snapshot = readQueue();
    let flushed = 0;
    while (flushed < snapshot.length) {
      const chunk = snapshot.slice(flushed, flushed + MAX_BATCH);
      await submitBatch(chunk);
      flushed += chunk.length;
      writeQueue(readQueue().slice(chunk.length));
    }
    return flushed;
  },
};
