'use client';

/**
 * Progress is one place with three views — what you know, the map of it,
 * and where it went wrong. The routes stay what they were (`/progress`,
 * `/graph`, `/mistakes`); this row just says they belong together, and the
 * Shell already treats all three as the Progress place.
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useT } from '@/lib/i18n';

export function ProgressTabs() {
  const pathname = usePathname() ?? '';
  const t = useT();
  const tabs = [
    { href: '/progress', label: t.progress.tabs.overview },
    { href: '/graph', label: t.progress.tabs.map },
    { href: '/mistakes', label: t.progress.tabs.mistakes },
  ];
  return (
    <nav aria-label={t.nav.progress} className="mt-6 flex gap-1 border-b border-line">
      {tabs.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors duration-fast ${
              active
                ? 'border-primary text-ink-900'
                : 'border-transparent text-ink-600 hover:text-ink-900'
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
