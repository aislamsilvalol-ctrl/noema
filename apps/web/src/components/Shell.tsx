'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { CommandPalette } from '@/components/CommandPalette';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { ThemeToggle } from '@/components/ThemeToggle';
import { useT } from '@/lib/i18n';

/**
 * The shell: five areas, and everything else one level down.
 *
 * Eleven peer destinations was the audit's clearest finding about navigation:
 * "Explain", "Socratic", "Mistakes" and "Graph" are ways of learning and views
 * of progress, not places. So the rail names five places — Home, Learn,
 * Review, Notes, Progress — and lists the rest under a heading rather than
 * hiding them (recognition over recall: a learner should still *see* that
 * Socratic mode exists). Every old route keeps working; only the map changed.
 *
 * Three regions from `docs/design-system.md`: rail, content at a reading
 * measure, and a context rail the route passes in. The rail collapses to
 * nothing on demand (there are no icons in this product, so an icon rail
 * would be a row of initials); below `md` it is a five-item bottom bar.
 */
export function Shell({
  children,
  rail,
}: {
  children: React.ReactNode;
  rail?: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useT();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem('noema.rail') === 'collapsed');
    } catch {
      // storage blocked: the rail stays open, which is the safe default
    }
  }, []);

  function toggleRail() {
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem('noema.rail', next ? 'collapsed' : 'open');
      } catch {
        // the choice still applies to this visit
      }
      return next;
    });
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // The five places. `match` decides which is "current" for routes that live
  // under a place without sharing its prefix (a notebook is Notes; the
  // Professor inside it is Learn).
  const primary = [
    { href: '/today', label: t.nav.home, match: (p: string) => p.startsWith('/today') },
    {
      href: '/chat',
      label: t.nav.learn,
      match: (p: string) => p.startsWith('/chat') || p.includes('/professor'),
    },
    { href: '/review', label: t.nav.review, match: (p: string) => p.startsWith('/review') },
    {
      href: '/library',
      label: t.nav.notes,
      match: (p: string) =>
        p.startsWith('/library') || (p.startsWith('/notebooks') && !p.includes('/professor')),
    },
    {
      href: '/progress',
      label: t.nav.progress,
      match: (p: string) =>
        p.startsWith('/progress') || p.startsWith('/mistakes') || p.startsWith('/graph'),
    },
  ];

  // The rest: visible, one level down, so nothing a learner could do is hidden
  // behind a search box they would have to know to open.
  const secondary = [
    { href: '/goals', label: t.nav.goals },
    { href: '/explain', label: t.nav.explain },
    { href: '/socratic', label: t.nav.socratic },
    { href: '/mistakes', label: t.nav.mistakes },
    { href: '/graph', label: t.nav.graph },
  ];

  const linkClass = (active: boolean) =>
    `block rounded-md px-2 py-1.5 text-sm transition-colors duration-state ${
      active ? 'bg-ink-100 text-ink-900' : 'text-ink-600 hover:text-ink-900'
    }`;

  return (
    <div className="flex min-h-screen">
      {!collapsed && (
        <nav className="hidden w-60 shrink-0 flex-col border-r border-line px-4 py-6 md:flex">
          <div className="flex items-center justify-between px-2">
            <Link href="/today" className="font-display text-lg text-ink-900">
              NOEMA
            </Link>
            <button
              type="button"
              onClick={toggleRail}
              aria-label={t.nav.collapse}
              className="text-xs text-ink-400 transition-colors duration-state hover:text-ink-900"
            >
              ‹
            </button>
          </div>

          <ul className="mt-8 space-y-0.5">
            {primary.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={link.match(pathname) ? 'page' : undefined}
                  className={linkClass(link.match(pathname))}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>

          <p className="mt-8 px-2 text-xs uppercase tracking-wide text-ink-400">
            {t.nav.moreAreas}
          </p>
          <ul className="mt-2 space-y-0.5">
            {secondary.map((link) => {
              const active = pathname.startsWith(link.href);
              return (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    aria-current={active ? 'page' : undefined}
                    className={linkClass(active)}
                  >
                    {link.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          <div className="mt-auto space-y-3 px-2">
            <Link
              href="/settings"
              className={`${linkClass(pathname.startsWith('/settings'))} -mx-2`}
            >
              {t.nav.settings}
            </Link>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="flex w-full items-center justify-between text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
            >
              {t.nav.commandPalette}
              <kbd className="font-mono text-[10px] text-ink-400">⌘K</kbd>
            </button>
            <ThemeToggle />
            <div className="flex items-center justify-between">
              <LanguageSwitcher />
              <button
                type="button"
                onClick={async () => {
                  await api.logout();
                  router.push('/');
                }}
                className="text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
              >
                {t.nav.signOut}
              </button>
            </div>
          </div>
        </nav>
      )}

      {collapsed && (
        <button
          type="button"
          onClick={toggleRail}
          aria-label={t.nav.expand}
          className="fixed left-3 top-4 z-20 hidden rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink-500 transition-colors duration-state hover:text-ink-900 md:block"
        >
          ›
        </button>
      )}

      {/* Below `md`: the same five places as a bottom bar, plus one item for
          everything else (the palette). Short labels, one line each — a bar
          that wraps is worse than a shorter one. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-surface md:hidden">
        {primary.map((link) => {
          const active = link.match(pathname);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? 'page' : undefined}
              className={`flex-1 whitespace-nowrap py-3 text-center text-xs transition-colors duration-state ${
                active ? 'text-ink-900' : 'text-ink-500'
              }`}
            >
              {link.label}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="flex-1 whitespace-nowrap py-3 text-center text-xs text-ink-500 transition-colors duration-state"
        >
          {t.nav.more}
        </button>
      </nav>

      <main className="min-w-0 flex-1 px-6 pb-24 pt-10 md:px-12 md:pb-10">
        {children}

        {/* Below `xl` the context rail moves under the content instead of
            disappearing — it holds the tutor, which cannot be the thing that
            vanishes on a laptop. */}
        {rail && (
          <section className="mt-12 border-t border-line pt-8 xl:hidden">{rail}</section>
        )}
      </main>

      {rail && (
        <aside className="hidden w-80 shrink-0 border-l border-line px-6 py-10 xl:block">
          {rail}
        </aside>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
