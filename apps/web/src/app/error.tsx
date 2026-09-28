'use client';

/**
 * Next's error boundary for everything under the root layout: one broken
 * component replaces this segment instead of taking the app to a blank
 * screen or the raw dev overlay.
 *
 * A real failure, so no scene and no joke: the bone ground, one line that
 * says what happened and what is safe, a way to retry, and the digest Next
 * attaches to server errors so a report can be matched to the log — and a
 * way to send that report from right here, digest already filled in.
 */

import { useEffect, useState } from 'react';
import { FeedbackDialog } from '@/components/FeedbackDialog';
import { Mino } from '@/components/mino/Mino';
import { Wordmark } from '@/components/brand/Wordmark';
import { Button } from '@/components/ui/Button';
import { useT } from '@/lib/i18n';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useT();
  const [reporting, setReporting] = useState(false);

  useEffect(() => {
    console.error(error);
  }, [error]);

  const reportOpening = error.digest
    ? `${t.feedback.fromError} ${t.errorBoundary.reference} ${error.digest}\n\n`
    : `${t.feedback.fromError}\n\n`;

  return (
    <main className="min-h-[100svh] bg-surface text-ink-900">
      <div className="mx-auto flex min-h-[100svh] max-w-[1400px] flex-col px-6 md:px-10">
        <header className="py-5">
          {/* A plain <a>: from a broken render a full reload is the escape
              hatch that does not depend on client routing state. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a href="/" aria-label="NOEMA">
            <Wordmark size="md" />
          </a>
        </header>

        <div className="flex flex-1 flex-col justify-center pb-[12svh]">
          <Mino state="concerned" size="md" />
          <h1 className="mt-8 max-w-[20ch] font-display text-2xl font-medium md:text-3xl">
            {t.errorBoundary.title}
          </h1>
          <p className="mt-4 max-w-[46ch] text-md text-ink-600">{t.errorBoundary.body}</p>

          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Button variant="primary" size="lg" onClick={reset}>
              {t.errorBoundary.retry}
            </Button>
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a href="/" className="text-base text-ink-700 underline-offset-4 hover:underline">
              {t.errorBoundary.backHome}
            </a>
            <button
              type="button"
              onClick={() => setReporting(true)}
              className="text-base text-ink-700 underline-offset-4 hover:underline"
            >
              {t.errorBoundary.report}
            </button>
          </div>

          {error.digest && (
            <p className="mt-12 font-mono text-xs text-ink-500">
              {t.errorBoundary.reference} {error.digest}
            </p>
          )}
        </div>
      </div>

      <FeedbackDialog
        open={reporting}
        onClose={() => setReporting(false)}
        kind="bug"
        message={reportOpening}
      />
    </main>
  );
}
