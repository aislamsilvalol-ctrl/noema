'use client';

/**
 * Documents in a notebook: put one in, watch it become searchable.
 *
 * Ingestion has stages and any of them can fail on a real file, so this shows
 * which stage a source is in and what went wrong when it stops. A spinner that
 * says nothing for four minutes and then silently gives up is how people conclude
 * software is broken when it is merely slow.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api, uploadSource, type Source, type SourceStatus } from '@/lib/api';
import { useT } from '@/lib/i18n';

//: Anything not in a terminal state is still moving, so keep asking.
const IN_PROGRESS: SourceStatus[] = [
  'pending',
  'parsing',
  'chunking',
  'embedding',
  'extracting',
];

export function SourceList({ notebookId }: { notebookId: string }) {
  const t = useT();
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const listed = await api.sources(notebookId);
      // Defensive because this polls: one malformed response should cost a tick,
      // not the whole screen.
      setSources(Array.isArray(listed) ? listed : []);
    } catch (err) {
      if (!(err instanceof ApiError && err.isUnauthorized)) {
        setError(err instanceof Error ? err.message : t.sources.couldNotList);
      }
    }
  }, [notebookId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll only while something is actually working. A notebook of finished
  // documents should not keep a request loop running for as long as the tab is
  // open.
  useEffect(() => {
    if (!sources.some((s) => IN_PROGRESS.includes(s.status))) return;
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [sources, load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);

    try {
      for (const file of Array.from(files)) {
        const source = await uploadSource(notebookId, file);
        // Uploading only stores the file; ingestion is a separate, explicit step
        // that the worker picks up.
        await api.ingest(source.id);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.sources.notAccepted);
    } finally {
      setBusy(false);
      if (picker.current) picker.current.value = '';
    }
  }

  return (
    <section className="mt-10">
      <h2 className="text-xs uppercase tracking-wide text-ink-500">{t.sources.documents}</h2>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void upload(event.dataTransfer.files);
        }}
        className={`mt-3 rounded-lg border border-dashed px-4 py-6 text-center transition-colors duration-state ${
          dragging ? 'border-accent bg-raised' : 'border-line'
        }`}
      >
        <p className="text-sm text-ink-600">
          {busy ? t.sources.uploading : t.sources.dropHere}
        </p>
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={busy}
          className="mt-3 rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
        >
          Choose a file
        </button>
        <input
          ref={picker}
          type="file"
          multiple
          onChange={(event) => void upload(event.target.files)}
          className="hidden"
        />
        <p className="mt-3 text-xs text-ink-400">
          Answers cite the page they came from, so what you put in is what it can
          use.
        </p>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {error}
        </p>
      )}

      {sources.length > 0 && (
        <ul className="mt-6 divide-y divide-line border-y border-line">
          {sources.map((source) => (
            <li key={source.id} className="flex items-baseline justify-between py-3">
              <span className="min-w-0">
                <span className="block truncate text-sm text-ink-800">
                  {source.original_filename ?? t.sources.untitled}
                </span>
                {source.status === 'failed' && source.error?.detail && (
                  // The reason, not just the fact. "Failed" alone leaves someone
                  // re-uploading the same broken file.
                  <span className="mt-0.5 block text-xs text-critical">
                    {source.error.detail}
                  </span>
                )}
              </span>

              <span className="ml-4 shrink-0 text-xs text-ink-500">
                {source.status === 'ready' && source.page_count
                  ? `${source.page_count} pages`
                  : (t.sources.stages[source.status] ?? source.status)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
