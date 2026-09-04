'use client';

/**
 * A subject's home: where you are, what to do next, and the material —
 * in that order. It used to open straight into the notes editor with a row
 * of buttons above it (audit §3.7); the notes and the editor are still here,
 * unchanged, but they come after the lesson and the reviews, and the editor
 * appears when a note is chosen rather than swallowing the page on load.
 *
 * Everything reads endpoints that already exist: the open teaching session
 * for this notebook (`/ai/sessions/latest?notebook_id`), the cards due here,
 * the notes. Autosave, selection actions and the tutor rail are as before.
 */

import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { InlineCreate } from '@/components/InlineCreate';
import { Shell } from '@/components/Shell';
import { AnkiImport } from '@/components/AnkiImport';
import { SourceList } from '@/components/SourceList';
import { TutorPanel } from '@/components/TutorPanel';
import { ButtonLink } from '@/components/ui/Button';
import { PathStrip } from '@/components/ui/PathStrip';
import type { SelectionAction } from '@/components/editor/NoteEditor';
import {
  ApiError,
  api,
  streamNoteAction,
  type Note,
  type Notebook,
  type TeachingSession,
} from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

// ProseMirror and KaTeX are ~300 kB and only matter once a note is open, so the
// shell and the note list paint without waiting for them.
const NoteEditor = dynamic(
  () => import('@/components/editor/NoteEditor').then((m) => m.NoteEditor),
  {
    ssr: false,
    loading: () => <div className="h-64 animate-pulse rounded-md bg-sunken" />,
  },
);

const AUTOSAVE_MS = 1200;

interface ActionResult {
  action: SelectionAction;
  selection: string;
  output: string;
  streaming: boolean;
  error?: string;
}

/** "3 hours ago", in the page's language, without a library. */
function relative(iso: string, lang: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ];
  const format = new Intl.RelativeTimeFormat(lang || undefined, { numeric: 'auto' });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return format.format(0, 'minute');
}

export default function NotebookPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const notebookId = params.id;

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [lesson, setLesson] = useState<TeachingSession | null>(null);
  const [due, setDue] = useState<number | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [saved, setSaved] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const [nb, notePage] = await Promise.all([
        api.notebook(notebookId),
        api.notes(notebookId),
      ]);
      setNotebook(nb);
      setNotes(notePage.items);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(humanError(err, t, 'load'));
    }
  }, [notebookId, router, t]);

  useEffect(() => {
    void load();
  }, [load]);

  // The lesson and the reviews are courtesies on top of the notebook: either
  // may be missing or fail without taking the page with it.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([api.latestSession(notebookId), api.dueCards(notebookId, 200)]).then(
      ([session, cards]) => {
        if (cancelled) return;
        if (session.status === 'fulfilled') setLesson(session.value);
        if (cards.status === 'fulfilled') setDue(cards.value.length);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [notebookId]);

  // Debounced autosave. Notes are the user's writing, so losing keystrokes to a
  // forgotten save button is not an acceptable failure mode.
  useEffect(() => {
    if (!activeId || saved) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);

    saveTimer.current = setTimeout(async () => {
      try {
        const updated = await api.updateNote(activeId, { content_md: draft });
        setNotes((current) => current.map((n) => (n.id === updated.id ? updated : n)));
        setSaved(true);
      } catch {
        setError(t.notebook.couldNotSave);
      }
    }, AUTOSAVE_MS);

    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [draft, activeId, saved, t]);

  async function addNote(title: string) {
    try {
      const note = await api.createNote(notebookId, title);
      setNotes((current) => [...current, note]);
      setActiveId(note.id);
      setDraft('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t.notebook.couldNotCreateNote);
    }
  }

  function openNote(note: Note) {
    setActiveId(note.id);
    setDraft(note.content_md);
    setSaved(true);
    setResult(null);
  }

  async function runAction(action: SelectionAction, selection: string) {
    if (!activeId) return;

    // "Ask" is a conversation, so it belongs in the tutor rail rather than as a
    // one-shot rewrite.
    if (action === 'ask') {
      window.dispatchEvent(
        new CustomEvent('noema:ask', { detail: { text: selection } }),
      );
      return;
    }
    if (action !== 'explain' && action !== 'simplify' && action !== 'expand') return;

    setResult({ action, selection, output: '', streaming: true });
    try {
      await streamNoteAction(activeId, action, selection, {
        onToken: (text) =>
          setResult((current) =>
            current ? { ...current, output: current.output + text } : current,
          ),
        onError: (message) =>
          setResult((current) => (current ? { ...current, error: message } : current)),
      });
    } finally {
      setResult((current) => (current ? { ...current, streaming: false } : current));
    }
  }

  const professorHref = `/notebooks/${notebookId}/professor`;
  const activeNote = notes.find((note) => note.id === activeId) ?? null;
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : '';

  return (
    <Shell rail={<TutorPanel notebookId={notebookId} />}>
      <header className="max-w-reading">
        <h1 className="font-display text-2xl text-ink-900">
          {notebook?.title ?? t.notebook.fallbackTitle}
        </h1>
        {notebook?.description && (
          <p className="mt-1 text-sm text-ink-500">{notebook.description}</p>
        )}
      </header>

      {error && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {error}
        </p>
      )}

      {/* Where you are, and the one action. A live lesson resumes; nothing
          yet means the first thing to do is start one. */}
      <section className="mt-8 max-w-reading rounded-lg border border-line bg-raised p-6 shadow-elevation-1">
        <p className="text-xs uppercase tracking-wide text-ink-500">{t.notebook.whereYouAre}</p>
        {lesson ? (
          <>
            <h2 className="mt-2 font-display text-xl text-ink-900">
              {lesson.current_concept || lesson.current_topic || lesson.subject || notebook?.title}
            </h2>
            {lesson.last_turn_at && (
              <p className="mt-1 text-sm text-ink-600">
                {t.notebook.lastLesson(relative(lesson.last_turn_at, lang))}
              </p>
            )}
            <PathStrip plan={lesson.plan} className="mt-4" />
            <ButtonLink href={professorHref} variant="primary" className="mt-5">
              {t.notebook.continueLesson}
            </ButtonLink>
          </>
        ) : (
          <>
            <h2 className="mt-2 font-display text-xl text-ink-900">{t.notebook.noLessonYet}</h2>
            <p className="mt-1 text-sm text-ink-600">{t.notebook.noLessonLede}</p>
            <ButtonLink href={professorHref} variant="primary" className="mt-5">
              {t.notebook.startLesson}
            </ButtonLink>
          </>
        )}
      </section>

      {/* Practice: reviews due here, then the ways to test yourself. */}
      <section className="mt-10 max-w-reading">
        <p className="text-xs uppercase tracking-wide text-ink-500">{t.notebook.practice}</p>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-y border-line py-4">
          <span className="text-md text-ink-900">
            {due === null
              ? t.common.loading
              : due > 0
                ? t.today.reviewsDue(due)
                : t.today.reviewsNone}
          </span>
          {due !== null && due > 0 && (
            <ButtonLink href="/review" variant="secondary" size="sm">
              {t.today.reviewsCta}
            </ButtonLink>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <ButtonLink href={`/notebooks/${notebookId}/cards`} variant="ghost" size="sm">
            {t.notebook.cards}
          </ButtonLink>
          <ButtonLink href={`/notebooks/${notebookId}/quiz`} variant="ghost" size="sm">
            {t.notebook.quiz}
          </ButtonLink>
          <ButtonLink href={`/notebooks/${notebookId}/exam`} variant="ghost" size="sm">
            {t.notebook.exam}
          </ButtonLink>
        </div>
      </section>

      {/* Notes: the list, and the editor once one is chosen. */}
      <section className="mt-10">
        <div className="flex max-w-reading flex-wrap items-baseline justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-ink-500">{t.notebook.notesTitle}</p>
          <InlineCreate
            label={t.notebook.noteTitle}
            placeholder={t.notebook.notePlaceholder}
            cta={t.notebook.newNote}
            onCreate={addNote}
          />
        </div>

        {notes.length === 0 ? (
          <p className="mt-3 max-w-reading text-base text-ink-600">{t.notebook.noNotes}</p>
        ) : (
          <ul className="mt-3 max-w-reading divide-y divide-line border-y border-line">
            {notes.map((note) => (
              <li key={note.id}>
                <button
                  type="button"
                  onClick={() => openNote(note)}
                  aria-current={note.id === activeId ? 'true' : undefined}
                  className={`flex w-full items-baseline justify-between py-2.5 text-left text-sm transition-colors duration-fast ${
                    note.id === activeId ? 'text-ink-900' : 'text-ink-700 hover:text-ink-900'
                  }`}
                >
                  <span className="truncate">{note.title}</span>
                  {note.id === activeId && (
                    <span className="ml-3 shrink-0 text-xs text-signal">{t.notebook.editing}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}

        {activeId && (
          <div className="mt-6">
            <div className="flex max-w-reading items-baseline justify-between gap-3">
              <h2 className="font-display text-lg text-ink-900">{activeNote?.title}</h2>
              <button
                type="button"
                onClick={() => {
                  setActiveId(null);
                  setResult(null);
                }}
                className="text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
              >
                {t.notebook.closeNote}
              </button>
            </div>
            <div className="mt-3">
              <NoteEditor
                key={activeId}
                value={draft}
                onChange={(markdown) => {
                  setDraft(markdown);
                  setSaved(false);
                }}
                onAction={runAction}
              />
            </div>
            <p className="mt-6 text-xs text-ink-400">{saved ? t.notebook.saved : t.notebook.saving}</p>

            {result && (
              <aside className="mt-8 max-w-reading border-t border-line pt-6">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="text-xs font-medium uppercase tracking-wide text-ink-500">
                    {result.action}
                  </h2>
                  <button
                    type="button"
                    onClick={() => setResult(null)}
                    className="text-xs text-ink-400 transition-colors duration-fast hover:text-ink-900"
                  >
                    {t.notebook.dismiss}
                  </button>
                </div>

                <blockquote className="mt-3 border-l-2 border-line pl-3 text-sm text-ink-500">
                  {result.selection.slice(0, 200)}
                  {result.selection.length > 200 && '…'}
                </blockquote>

                <p className="mt-4 whitespace-pre-wrap font-serif text-base text-ink-800">
                  {result.output}
                  {result.streaming && (
                    <span className="ml-0.5 inline-block h-4 w-px animate-pulse bg-signal align-middle" />
                  )}
                </p>

                {result.error && (
                  <p role="alert" className="mt-3 text-sm text-critical">
                    {result.error}
                  </p>
                )}

                {!result.streaming && result.output && (
                  <p className="mt-4 text-xs text-ink-400">{t.notebook.nothingWritten}</p>
                )}
              </aside>
            )}
          </div>
        )}
      </section>

      {/* Material: documents and imported decks, folded until wanted. */}
      <details className="mt-10 max-w-reading">
        <summary className="cursor-pointer text-xs uppercase tracking-wide text-ink-500">
          {t.notebook.materials}
        </summary>
        <div className="mt-3">
          <SourceList notebookId={notebookId} />
          <AnkiImport notebookId={notebookId} />
        </div>
      </details>

      <p className="mt-10">
        <Link href="/library" className="text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900">
          {t.nav.library} →
        </Link>
      </p>
    </Shell>
  );
}
