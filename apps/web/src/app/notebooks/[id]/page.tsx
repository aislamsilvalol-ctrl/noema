'use client';

import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Shell } from '@/components/Shell';
import { TutorPanel } from '@/components/TutorPanel';
import { ApiError, api, type Note, type Notebook } from '@/lib/api';

const AUTOSAVE_MS = 1200;

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

  async function addNote() {
    const title = window.prompt('Note title');
    if (!title) return;
    const note = await api.createNote(notebookId, title);
    setNotes((current) => [...current, note]);
    setActiveId(note.id);
    setDraft('');
  }

  function openNote(note: Note) {
    setActiveId(note.id);
    setDraft(note.content_md);
    setSaved(true);
  }

  return (
    <Shell rail={<TutorPanel notebookId={notebookId} />}>
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="font-display text-2xl text-ink-900">
            {notebook?.title ?? 'Notebook'}
          </h1>
          {notebook?.description && (
            <p className="mt-1 text-sm text-ink-500">{notebook.description}</p>
          )}
        </div>
        <button
          type="button"
          onClick={addNote}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
        >
          New note
        </button>
      </header>

      {error && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {error}
        </p>
      )}

      <div className="mt-8 flex gap-8">
        <ul className="w-48 shrink-0 space-y-0.5">
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

        <div className="min-w-0 flex-1">
          {activeId ? (
            <>
              <textarea
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setSaved(false);
                }}
                spellCheck
                placeholder="Write in Markdown. Link concepts with [[double brackets]]."
                className="min-h-[60vh] w-full resize-none bg-transparent font-serif text-md leading-relaxed text-ink-800 outline-none placeholder:text-ink-400"
              />
              <p className="text-xs text-ink-400">{saved ? 'Saved' : 'Saving…'}</p>
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
