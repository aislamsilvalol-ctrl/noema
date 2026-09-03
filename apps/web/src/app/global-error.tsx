'use client';

/**
 * Only reached if the root layout itself throws -- so unlike error.tsx, this
 * has no access to I18nProvider or any other context the normal tree
 * provides, and has to render its own <html>/<body>. Deliberately minimal:
 * this path should be rare, and the honest, safe choice here is a plain,
 * always-working escape hatch rather than anything that could itself fail to
 * render for the same reason the layout did.
 */

import '@/styles/globals.css';

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
          <h1 className="font-display text-2xl text-ink-900">NOEMA hit an error.</h1>
          <p className="mt-3 max-w-reading text-base text-ink-600">
            Something broke at the page level. Try again, or reload the page.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={reset}
              className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
            >
              Try again
            </button>
            {/* Plain <a>, not <Link>: the root layout itself just threw, so a
                full reload is the one thing here not depending on whatever
                broke. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/"
              className="rounded-md border border-line px-4 py-2 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
            >
              Back to home
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
