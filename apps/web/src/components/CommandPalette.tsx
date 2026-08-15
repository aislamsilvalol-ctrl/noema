'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useT } from '@/lib/i18n';

interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
  /** Phase-gated commands stay visible but inert, so the roadmap is legible in the UI. */
  available?: boolean;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const t = useT();
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo<Command[]>(
    () => [
      { id: 'today', label: t.palette.todaySession, run: () => router.push('/today') },
      { id: 'library', label: t.palette.goLibrary, run: () => router.push('/library') },
      { id: 'settings', label: t.palette.settingsKeys, run: () => router.push('/settings') },
      { id: 'review', label: t.palette.reviewDue, run: () => router.push('/review') },
      {
        id: 'quiz',
        label: t.palette.quizMe,
        hint: t.palette.quizHint,
        run: () => router.push('/library'),
      },
      {
        id: 'session',
        label: t.palette.startSession,
        run: () => router.push('/today'),
      },
      {
        id: 'explain',
        label: t.palette.explainBack,
        run: () => router.push('/explain'),
      },
      {
        id: 'goals',
        label: t.palette.goalsByWhen,
        run: () => router.push('/goals'),
      },
      {
        id: 'socratic',
        label: t.palette.socraticQuestion,
        run: () => router.push('/socratic'),
      },
      {
        id: 'graph',
        label: t.palette.showMap,
        run: () => router.push('/graph'),
      },
      {
        id: 'progress',
        label: t.palette.whatDoIKnow,
        run: () => router.push('/progress'),
      },
      {
        id: 'mistakes',
        label: t.palette.reviewMistakes,
        run: () => router.push('/mistakes'),
      },
    ],
    [router, t],
  );

  const matches = commands.filter((c) =>
    c.label.toLowerCase().includes(query.trim().toLowerCase()),
  );

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelected(0);
      inputRef.current?.focus();
    }
  }, [open]);

  if (!open) return null;

  function choose(command: Command | undefined) {
    if (!command || command.available === false) return;
    command.run();
    onClose();
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.palette.ariaLabel}
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink-900/20 pt-[15vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg animate-fade-up overflow-hidden rounded-lg border border-line bg-raised shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setSelected(0);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') onClose();
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setSelected((i) => Math.min(i + 1, matches.length - 1));
            }
            if (event.key === 'ArrowUp') {
              event.preventDefault();
              setSelected((i) => Math.max(i - 1, 0));
            }
            if (event.key === 'Enter') choose(matches[selected]);
          }}
          placeholder={t.palette.searchPlaceholder}
          className="w-full border-b border-line bg-transparent px-4 py-3.5 text-base text-ink-900 outline-none placeholder:text-ink-400"
        />

        <ul className="max-h-80 overflow-y-auto py-1">
          {matches.length === 0 && (
            <li className="px-4 py-3 text-sm text-ink-500">{t.palette.noMatch}</li>
          )}
          {matches.map((command, index) => {
            const disabled = command.available === false;
            return (
              <li key={command.id}>
                <button
                  type="button"
                  disabled={disabled}
                  onMouseEnter={() => setSelected(index)}
                  onClick={() => choose(command)}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm transition-colors duration-state ${
                    index === selected && !disabled ? 'bg-ink-100' : ''
                  } ${disabled ? 'text-ink-400' : 'text-ink-800'}`}
                >
                  {command.label}
                  {command.hint && (
                    <span className="text-xs text-ink-400">{command.hint}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
