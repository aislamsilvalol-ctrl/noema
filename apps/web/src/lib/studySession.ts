/**
 * A study session, opened and closed around a review queue.
 *
 * The planner predicts how long a session takes and how many items it holds;
 * this is what gives those predictions an outcome to be judged against. It
 * opens once, when the first card is shown, and closes once, when the queue
 * empties or the learner leaves — never on an idle page load, which would
 * write a session per visit and poison the completion data it exists for.
 *
 * Neither call may get in the way of reviewing: a failed start means there is
 * no session to close, and a failed close is simply lost.
 */

export type SessionLifecycle = {
  /** Opens the session. Later calls are ignored. */
  begin(minutes?: number): void;
  /** Closes the session with what was answered. Idempotent; a no-op before
   *  `begin` and when nothing was answered. */
  finish(itemsCompleted: number): void;
};

export function createSessionLifecycle(deps: {
  start: (minutes?: number) => Promise<{ id: string }>;
  complete: (id: string, itemsCompleted: number, seconds: number) => Promise<unknown>;
  now?: () => number;
}): SessionLifecycle {
  const now = deps.now ?? Date.now;
  let opening: Promise<string | null> | null = null;
  let startedAt = 0;
  let finished = false;

  return {
    begin(minutes) {
      if (opening) return;
      startedAt = now();
      opening = deps.start(minutes).then(
        (session) => session.id,
        () => null,
      );
    },
    finish(itemsCompleted) {
      if (!opening || finished || itemsCompleted <= 0) return;
      finished = true;
      const seconds = Math.max(0, Math.round((now() - startedAt) / 1000));
      void opening.then((id) => {
        if (!id) return;
        return deps.complete(id, itemsCompleted, seconds).catch(() => undefined);
      });
    },
  };
}
