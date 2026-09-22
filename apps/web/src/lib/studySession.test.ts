import { describe, expect, it, vi } from 'vitest';

import { createSessionLifecycle } from '@/lib/studySession';

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function build(overrides: Partial<Parameters<typeof createSessionLifecycle>[0]> = {}) {
  let clock = 1_000_000;
  const start = vi.fn(async () => ({ id: 'session-1' }));
  const complete = vi.fn(async () => ({}));
  const lifecycle = createSessionLifecycle({
    start,
    complete,
    now: () => clock,
    ...overrides,
  });
  return { lifecycle, start, complete, tick: (ms: number) => (clock += ms) };
}

describe('createSessionLifecycle', () => {
  it('starts once, even when begin is called twice', () => {
    const { lifecycle, start } = build();
    lifecycle.begin(7);
    lifecycle.begin(7);
    expect(start).toHaveBeenCalledTimes(1);
    expect(start).toHaveBeenCalledWith(7);
  });

  it('completes with the count and the elapsed seconds, once', async () => {
    const { lifecycle, complete, tick } = build();
    lifecycle.begin();
    tick(92_400);
    lifecycle.finish(12);
    lifecycle.finish(12);
    await settle();
    expect(complete).toHaveBeenCalledTimes(1);
    expect(complete).toHaveBeenCalledWith('session-1', 12, 92);
  });

  it('skips completion when nothing was answered', async () => {
    const { lifecycle, complete } = build();
    lifecycle.begin();
    lifecycle.finish(0);
    await settle();
    expect(complete).not.toHaveBeenCalled();
  });

  it('skips completion when the session never began', async () => {
    const { lifecycle, complete } = build();
    lifecycle.finish(3);
    await settle();
    expect(complete).not.toHaveBeenCalled();
  });

  it('carries on without a session when start fails', async () => {
    const { lifecycle, complete } = build({
      start: vi.fn(async () => {
        throw new Error('down');
      }),
    });
    expect(() => lifecycle.begin()).not.toThrow();
    lifecycle.finish(4);
    await settle();
    expect(complete).not.toHaveBeenCalled();
  });

  it('swallows a failing complete', async () => {
    const { lifecycle } = build({
      complete: vi.fn(async () => {
        throw new Error('down');
      }),
    });
    lifecycle.begin();
    lifecycle.finish(1);
    await settle();
    // Nothing rejected unhandled; reaching here is the assertion.
    expect(true).toBe(true);
  });
});
