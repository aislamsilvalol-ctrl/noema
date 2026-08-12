'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Notebook, type Subject } from '@/lib/api';

export default function LibraryPage() {
  const router = useRouter();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [due, setDue] = useState(0);

  const load = useCallback(async () => {
    try {
      const [subjectPage, notebookPage] = await Promise.all([
        api.subjects(),
        api.notebooks(),
      ]);
      setSubjects(subjectPage.items);
      setNotebooks(notebookPage.items);
      setDue((await api.dueCards(undefined, 200)).length);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not load your library.');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createNotebook() {
    const title = window.prompt('Notebook title');
    if (!title) return;

    try {
      let subject = subjects[0];
      if (!subject) {
        // A first-run account has a workspace but no subject yet.
        const workspaces = await api.workspaces();
        const workspace = workspaces.items[0];
        if (!workspace) return;
        subject = await api.createSubject(workspace.id, 'General');
        setSubjects([subject]);
      }
      const notebook = await api.createNotebook(subject.id, title);
      setNotebooks((current) => [...current, notebook]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the notebook.');
    }
  }

  return (
    <Shell>
      <header className="flex items-baseline justify-between">
        <h1 className="font-display text-2xl text-ink-900">Library</h1>
        <button
          type="button"
          onClick={createNotebook}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
        >
          New notebook
        </button>
      </header>

      {due > 0 && (
        <Link
          href="/review"
          className="mt-6 flex items-baseline justify-between border-y border-line py-4 transition-colors duration-state hover:border-ink-400"
        >
          <span className="text-md text-ink-900">
            {due} {due === 1 ? 'card' : 'cards'} due
          </span>
          <span className="text-sm text-accent">Start reviewing →</span>
        </Link>
      )}

      {error && (
        <p role="alert" className="mt-6 text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">Loading…</p>
      ) : notebooks.length === 0 ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">Nothing here yet.</h2>
          <p className="mt-2 text-base text-ink-600">
            A notebook is one subject you are working on — a course, a paper, a chapter.
            Put material in it and NOEMA starts building a picture of what you know.
          </p>
        </div>
      ) : (
        <ul className="mt-10 divide-y divide-line border-y border-line">
          {notebooks.map((notebook) => (
            <li key={notebook.id}>
              <Link
                href={`/notebooks/${notebook.id}`}
                className="group flex items-baseline justify-between py-4 transition-colors duration-state"
              >
                <span>
                  <span className="text-md text-ink-900 group-hover:text-accent">
                    {notebook.title}
                  </span>
                  {notebook.description && (
                    <span className="mt-1 block text-sm text-ink-500">
                      {notebook.description}
                    </span>
                  )}
                </span>
                <time className="text-xs text-ink-400" dateTime={notebook.updated_at}>
                  {new Date(notebook.updated_at).toLocaleDateString()}
                </time>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}
