'use client';

/**
 * Next's per-segment error boundary -- catches a render/runtime exception
 * anywhere under the root layout and replaces just that segment, so one
 * broken component doesn't take the whole app down to a blank screen or
 * Next's raw dev overlay in production.
 */

import { useEffect } from 'react';
import { useT } from '@/lib/i18n';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useT();

  useEffect(() => {
    // eslint-disable-next-line no-console -- the one place a client error is
    // allowed to reach the console: there is no server-side log for a
    // client-render exception otherwise, and this app has no external error
    // tracker wired up yet.
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <h1 className="font-display text-2xl text-ink-900">{t.errorBoundary.title}</h1>
      <p className="mt-3 max-w-reading text-base text-ink-600">{t.errorBoundary.body}</p>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
        >
          {t.errorBoundary.retry}
        </button>
        {/* A plain <a>, not next/link's <Link>: this fires from a broken
            render state, so a full page reload is the safer escape hatch --
            it doesn't depend on client-side routing state that may itself be
            part of what's broken. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a
          href="/"
          className="rounded-md border border-line px-4 py-2 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
        >
          {t.errorBoundary.backHome}
        </a>
      </div>
    </main>
  );
}
