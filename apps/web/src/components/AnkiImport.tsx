'use client';

/**
 * Importing an Anki deck.
 *
 * The result is reported in numbers someone can check against the deck they
 * exported, not as "done". An importer that swallows several thousand cards and
 * says nothing is asking to be trusted about something nobody will count by
 * hand — and the number that matters most is how many kept their review history,
 * because that is the part that cannot be recreated.
 */

import { useRef, useState } from 'react';
import { importAnki, type AnkiImport as Report } from '@/lib/api';

export function AnkiImport({
  notebookId,
  onImported,
}: {
  notebookId: string;
  onImported?: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function choose(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await importAnki(notebookId, file));
      onImported?.();
    } catch (err) {
      // ApiError already carries the server's `detail` as its message, and those
      // messages each say what to do next, so they are shown as written.
      setError(err instanceof Error ? err.message : 'The deck could not be imported.');
    } finally {
      setBusy(false);
      // Cleared so choosing the same file again re-runs the import; otherwise
      // nothing happens and it looks broken.
      if (input.current) input.current.value = '';
    }
  }

  return (
    <section className="mt-8 border-t border-line pt-6">
      <h3 className="text-xs uppercase tracking-wide text-ink-500">From Anki</h3>
      <p className="mt-2 text-sm text-ink-600">
        Import an <code>.apkg</code> export. Your intervals come with it, so cards you
        already know are not asked again from scratch.
      </p>

      <input
        ref={input}
        type="file"
        accept=".apkg"
        className="sr-only"
        onChange={(event) => void choose(event.target.files?.[0])}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className="mt-4 rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
      >
        {busy ? 'Reading the deck…' : 'Choose a deck'}
      </button>

      {error && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {error}
        </p>
      )}

      {report && (
        <div className="mt-4 text-sm">
          <p className="text-ink-800">{report.summary}</p>
          {report.scheduled > 0 && (
            <p className="mt-2 text-xs text-ink-500">
              The imported intervals are a starting position translated from
              Anki&rsquo;s, not an exact conversion. Your next few reviews correct them.
            </p>
          )}
          {Object.keys(report.skipped).length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-ink-500">
              {Object.entries(report.skipped).map(([reason, count]) => (
                <li key={reason}>
                  {count} skipped — {reason}.
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
