'use client';

import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { InlineCreate } from '@/components/InlineCreate';
import { Shell } from '@/components/Shell';
import { AnkiImport } from '@/components/AnkiImport';
import { SourceList } from '@/components/SourceList';
import { TutorPanel } from '@/components/TutorPanel';
import type { SelectionAction } from '@/components/editor/NoteEditor';
import { ApiError, api, streamNoteAction, type Note, type Notebook } from '@/lib/api';

// ProseMirror and KaTeX are ~300 kB and only matter once a note is open, so the
// shell and the note list paint without waiting for them.
const NoteEditor = dynamic(
  () => import('@/components/editor/NoteEditor').then((m) => m.NoteEditor),
  {
    ssr: false,
    loading: () => <div className="h-64 animate-pulse rounded-md bg-ink-100" />,
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

export default function NotebookPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const notebookId = params.id;

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
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
      const first = notePage.items[0];
      if (first) {
        setActiveId(first.id);
        setDraft(first.content_md);
      }
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not open this notebook.');
    }
  }, [notebookId, router]);

  useEffect(() => {
    void load();
  }, [load]);

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
        setError('Could not save. Your text is still here — check your connection.');
      }
    }, AUTOSAVE_MS);

    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [draft, activeId, saved]);

  async function addNote(title: string) {
    const note = await api.createNote(notebookId, title);
    setNotes((current) => [...current, note]);
    setActiveId(note.id);
    setDraft('');
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

  return (
    <Shell rail={<TutorPanel notebookId={notebookId} />}>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl text-ink-900">
            {notebook?.title ?? 'Notebook'}
          </h1>
          {notebook?.description && (
            <p className="mt-1 text-sm text-ink-500">{notebook.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/notebooks/${notebookId}/exam`}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            Exam
          </Link>
          <Link
            href={`/notebooks/${notebookId}/quiz`}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            Quiz
          </Link>
          <Link
            href={`/notebooks/${notebookId}/cards`}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            Cards
          </Link>
          <InlineCreate
            label="Note title"
            placeholder="Cardiac cycle"
            cta="New note"
            onCreate={addNote}
          />
        </div>
      </header>

      {error && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {error}
        </p>
      )}

      {/* Stacked below `md`: a 192px list beside an editor on a 375px screen
          leaves neither of them usable. */}
      <div className="mt-8 flex flex-col gap-8 md:flex-row">
        <div className="w-full shrink-0 md:w-48">
          <ul className="space-y-0.5">
          {notes.map((note) => (
            <li key={note.id}>
              <button
                type="button"
                onClick={() => openNote(note)}
                className={`w-full truncate rounded-md px-2 py-1.5 text-left text-sm transition-colors duration-state ${
                  note.id === activeId
                    ? 'bg-ink-100 text-ink-900'
                    : 'text-ink-600 hover:text-ink-900'
                }`}
              >
                {note.title}
              </button>
            </li>
          ))}
          </ul>

          {/* Uploaded documents sit beside the notes, because they are the other
              half of a notebook's material — and until now the only half you
              could not put in from here. */}
          <SourceList notebookId={notebookId} />

          {/* Cards can arrive from elsewhere too. Someone with an existing deck
              should not have to start empty to try this. */}
          <AnkiImport notebookId={notebookId} />
        </div>

        <div className="min-w-0 flex-1">
          {activeId ? (
            <>
              <NoteEditor
                key={activeId}
                value={draft}
                onChange={(markdown) => {
                  setDraft(markdown);
                  setSaved(false);
                }}
                onAction={runAction}
              />
              <p className="mt-6 text-xs text-ink-400">{saved ? 'Saved' : 'Saving…'}</p>

              {result && (
                <aside className="mt-8 max-w-reading border-t border-line pt-6">
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <h2 className="text-xs font-medium uppercase tracking-wide text-ink-500">
                      {result.action}
                    </h2>
                    <button
                      type="button"
                      onClick={() => setResult(null)}
                      className="text-xs text-ink-400 transition-colors duration-state hover:text-ink-900"
                    >
                      Dismiss
                    </button>
                  </div>

                  <blockquote className="mt-3 border-l-2 border-line pl-3 text-sm text-ink-500">
                    {result.selection.slice(0, 200)}
                    {result.selection.length > 200 && '…'}
                  </blockquote>

                  <p className="mt-4 whitespace-pre-wrap font-serif text-base text-ink-800">
                    {result.output}
                    {result.streaming && (
                      <span className="ml-0.5 inline-block h-4 w-px animate-pulse bg-accent align-middle" />
                    )}
                  </p>

                  {result.error && (
                    <p role="alert" className="mt-3 text-sm text-critical">
                      {result.error}
                    </p>
                  )}

                  {!result.streaming && result.output && (
                    <p className="mt-4 text-xs text-ink-400">
                      Nothing here has been written into your note.
                    </p>
                  )}
                </aside>
              )}
            </>
          ) : (
            <p className="max-w-reading text-base text-ink-600">
              No notes yet. Notes exist to become questions — write what you are trying to
              understand, not what you already know.
            </p>
          )}
        </div>
      </div>
    </Shell>
  );
}
