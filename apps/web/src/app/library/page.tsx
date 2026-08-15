'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { InlineCreate } from '@/components/InlineCreate';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Notebook, type Subject } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function LibraryPage() {
  const router = useRouter();
  const t = useT();
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
      setError(err instanceof Error ? err.message : t.library.couldNotLoad);
    } finally {
      setLoading(false);
    }
  }, [router, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createNotebook(title: string) {
    try {
      let subject = subjects[0];
      if (!subject) {
        // A first-run account has a workspace but no subject yet.
        const workspaces = await api.workspaces();
        const workspace = workspaces.items[0];
        if (!workspace) return;
        subject = await api.createSubject(workspace.id, t.library.defaultSubject);
        setSubjects([subject]);
      }
      const notebook = await api.createNotebook(subject.id, title);
      setNotebooks((current) => [...current, notebook]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.library.couldNotCreate);
    }
  }

  // Subjects first, in their own order; anything whose subject is missing goes
  // last rather than disappearing.
  const grouped = [
    ...subjects.map((subject) => ({
      subject,
      items: notebooks.filter((n) => n.subject_id === subject.id),
    })),
    {
      subject: null,
      items: notebooks.filter((n) => !subjects.some((s) => s.id === n.subject_id)),
    },
  ].filter((group) => group.items.length > 0);

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.library.title}</h1>
        <InlineCreate
          label={t.library.notebookTitle}
          placeholder={t.library.notebookPlaceholder}
          cta={t.library.newNotebook}
          onCreate={createNotebook}
        />
      </header>

      {due > 0 && (
        <Link
          href="/review"
          className="mt-6 flex items-baseline justify-between border-y border-line py-4 transition-colors duration-state hover:border-ink-400"
        >
          <span className="text-md text-ink-900">{t.library.cardsDue(due)}</span>
          <span className="text-sm text-accent">{t.library.startReviewing}</span>
        </Link>
      )}

      {error && (
        <p role="alert" className="mt-6 text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">{t.common.loading}</p>
      ) : notebooks.length === 0 ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">{t.library.emptyTitle}</h2>
          <p className="mt-2 text-base text-ink-600">
            {t.library.emptyBody}
          </p>
        </div>
      ) : (
        grouped.map(({ subject, items }) => (
          <section key={subject?.id ?? 'loose'} className="mt-12">
            {/* The hierarchy is the product's organising idea. A flat list reads
                fine with five notebooks and loses the structure with fifty. */}
            <h2 className="text-xs uppercase tracking-wide text-ink-500">
              {subject?.title ?? t.library.unfiled}
            </h2>
            <ul className="mt-3 divide-y divide-line border-y border-line">
              {items.map((notebook) => (
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
          </section>
        ))
      )}
    </Shell>
  );
}
