// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { offlineQueue, type QueuedReview } from '@/lib/offlineQueue';

function review(card_id: string): QueuedReview {
  return { card_id, rating: 3, elapsed_ms: 1200 };
}

beforeEach(() => {
  localStorage.clear();
});

describe('enqueue / size', () => {
  it('starts empty', () => {
    expect(offlineQueue.size()).toBe(0);
  });

  it('grows with each enqueue and survives being read fresh', () => {
    offlineQueue.enqueue(review('card-1'));
    offlineQueue.enqueue(review('card-2'));

    expect(offlineQueue.size()).toBe(2);
  });

  it('does not lose a queue already on disk from a previous session', () => {
    localStorage.setItem('noema.review-queue.v1', JSON.stringify([review('card-1')]));

    expect(offlineQueue.size()).toBe(1);
  });

  it('treats a corrupt stored value as an empty queue rather than throwing', () => {
    localStorage.setItem('noema.review-queue.v1', 'not json');

    expect(offlineQueue.size()).toBe(0);
  });
});

describe('flush', () => {
  it('submits the whole queue in one call and empties it on success', async () => {
    offlineQueue.enqueue(review('card-1'));
    offlineQueue.enqueue(review('card-2'));
    const submitBatch = vi.fn().mockResolvedValue(undefined);

    const flushed = await offlineQueue.flush(submitBatch);

    expect(flushed).toBe(2);
    expect(submitBatch).toHaveBeenCalledOnce();
    expect(submitBatch).toHaveBeenCalledWith([review('card-1'), review('card-2')]);
    expect(offlineQueue.size()).toBe(0);
  });

  it('is a no-op on an empty queue — never calls the submitter', async () => {
    const submitBatch = vi.fn();

    const flushed = await offlineQueue.flush(submitBatch);

    expect(flushed).toBe(0);
    expect(submitBatch).not.toHaveBeenCalled();
  });

  it('leaves the queue intact when the submit rejects — still offline', async () => {
    offlineQueue.enqueue(review('card-1'));
    const submitBatch = vi.fn().mockRejectedValue(new Error('network down'));

    await expect(offlineQueue.flush(submitBatch)).rejects.toThrow('network down');
    expect(offlineQueue.size()).toBe(1);
  });

  it('keeps a review enqueued during the flush rather than dropping it', async () => {
    offlineQueue.enqueue(review('card-1'));
    const submitBatch = vi.fn().mockImplementation(async () => {
      // A card gets reviewed while the in-flight batch is still uploading.
      offlineQueue.enqueue(review('card-2'));
    });

    const flushed = await offlineQueue.flush(submitBatch);

    expect(flushed).toBe(1);
    expect(offlineQueue.size()).toBe(1);
    expect(submitBatch).toHaveBeenCalledWith([review('card-1')]);
  });

  it('chunks a queue larger than the backend batch cap', async () => {
    for (let i = 0; i < 250; i++) offlineQueue.enqueue(review(`card-${i}`));
    const submitBatch = vi.fn().mockResolvedValue(undefined);

    const flushed = await offlineQueue.flush(submitBatch);

    expect(flushed).toBe(250);
    expect(submitBatch).toHaveBeenCalledTimes(2);
    expect((submitBatch.mock.calls[0]?.[0] as unknown[]).length).toBe(200);
    expect((submitBatch.mock.calls[1]?.[0] as unknown[]).length).toBe(50);
    expect(offlineQueue.size()).toBe(0);
  });
});
