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
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
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
      <Button ref={trigger} size="sm" onClick={() => setOpen(true)}>
        {cta}
      </Button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor="inline-create">
        {label}
      </label>
      <Input
        id="inline-create"
        size="sm"
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
        className="min-w-0 flex-1 sm:flex-none sm:w-64"
      />
      <Button
        variant="primary"
        size="sm"
        onClick={submit}
        disabled={!title.trim()}
        busy={busy ? t.common.creating : undefined}
      >
        {t.common.create}
      </Button>
      <Button variant="ghost" size="sm" onClick={close}>
        {t.common.cancel}
      </Button>
    </div>
  );
}
