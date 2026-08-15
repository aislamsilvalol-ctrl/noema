'use client';

/**
 * "Give it a name" without leaving the page.
 *
 * Replaces `window.prompt`, which was the one unstyled OS dialog in an interface
 * that is otherwise carefully set — and which no automated test can fill, which
 * is how it was found.
 *
 * Escape cancels, Enter submits, focus lands in the field and returns to the
 * button that opened it. A modal you cannot leave by keyboard is worse than the
 * prompt it replaced.
 */

import { useEffect, useRef, useState } from 'react';
import { useT } from '@/lib/i18n';

export function InlineCreate({
  label,
  placeholder,
  cta,
  onCreate,
}: {
  label: string;
  placeholder: string;
  cta: string;
  onCreate: (title: string) => Promise<void> | void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const field = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);

  function close() {
    setOpen(false);
    setTitle('');
    // Focus goes back where it came from, or a keyboard user is left at the top
    // of the document wondering what happened.
    trigger.current?.focus();
  }

  async function submit() {
    const trimmed = title.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await onCreate(trimmed);
      close();
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
      >
        {cta}
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor="inline-create">
        {label}
      </label>
      <input
        id="inline-create"
        ref={field}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            void submit();
          } else if (event.key === 'Escape') {
            event.preventDefault();
            close();
          }
        }}
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-md border border-line bg-raised px-3 py-1.5 text-sm text-ink-900 sm:flex-none sm:w-64"
      />
      <button
        type="button"
        onClick={submit}
        disabled={busy || !title.trim()}
        className="rounded-md bg-ink-900 px-3 py-1.5 text-sm font-medium text-ink-50 disabled:opacity-40"
      >
        {busy ? t.common.creating : t.common.create}
      </button>
      <button
        type="button"
        onClick={close}
        className="px-2 py-1.5 text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
      >
        {t.common.cancel}
      </button>
    </div>
  );
}
