'use client';

/**
 * Progress is one place with four views — the map of a journey, what you
 * know, the concept graph, and where it went wrong. The routes stay what
 * they were (`/progress`, `/graph`, `/mistakes`); this row just says they
 * belong together, and the Shell already treats all three as the Progress
 * place.
 *
 * Map and Overview both live on `/progress`. When that page renders the row
 * it passes the current view and a setter, and the two become buttons that
 * switch in place; from `/graph` or `/mistakes` they are plain links back,
 * `?view=overview` carrying the choice across the navigation.
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useT } from '@/lib/i18n';

export type ProgressView = 'map' | 'overview';

const TAB =
  '-mb-px border-b-2 px-3 py-2 text-sm transition-colors duration-fast';
const ACTIVE = 'border-primary text-ink-900';
const IDLE = 'border-transparent text-ink-600 hover:text-ink-900';

export function ProgressTabs({
  view,
  onView,
}: {
  /** The in-page view, when rendered by /progress itself. */
  view?: ProgressView;
  onView?: (view: ProgressView) => void;
}) {
  const pathname = usePathname() ?? '';
  const t = useT();
  const onProgress = pathname.startsWith('/progress');

  const views: { id: ProgressView; label: string; href: string }[] = [
    { id: 'map', label: t.progress.tabs.map, href: '/progress' },
    { id: 'overview', label: t.progress.tabs.overview, href: '/progress?view=overview' },
  ];
  const routes = [
    { href: '/graph', label: t.terrain.graphTab },
    { href: '/mistakes', label: t.progress.tabs.mistakes },
  ];

  return (
    <nav aria-label={t.nav.progress} className="mt-6 flex gap-1 border-b border-line">
      {views.map((tab) =>
        onProgress && onView ? (
          <button
            key={tab.id}
            type="button"
            onClick={() => onView(tab.id)}
            aria-current={view === tab.id ? 'page' : undefined}
            className={`${TAB} ${view === tab.id ? ACTIVE : IDLE}`}
          >
            {tab.label}
          </button>
        ) : (
          <Link key={tab.id} href={tab.href} className={`${TAB} ${IDLE}`}>
            {tab.label}
          </Link>
        ),
      )}
      {routes.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={`${TAB} ${active ? ACTIVE : IDLE}`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
