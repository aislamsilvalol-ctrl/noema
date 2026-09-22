'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { CommandPalette } from '@/components/CommandPalette';
import { Wordmark } from '@/components/brand/Wordmark';
import { useT } from '@/lib/i18n';

/**
 * The shell: six places, typeset, on the same ground as the page.
 *
 * The rail is a list, not a panel — bone like everything else, a hairline
 * on its right, the current place in cobalt. Home, Learn, Review, Notes,
 * Progress are the places a learner goes; Goals is the one thing left that
 * is a place and not a way of learning ("Explain", "Socratic", "Mistakes"
 * and "Graph" are actions inside the lesson and tabs under Progress). At
 * the bottom: Settings, the palette, sign out. Appearance and language live
 * in Settings, where a choice made once belongs, not beside every screen.
 *
 * Three regions from `docs/design-system.md`: rail, content at a reading
 * measure, and a context rail the route passes in. The rail collapses on
 * demand (there are no icons in this product, so an icon rail would be a
 * row of initials); below `md` the five places are a bottom bar.
 */
export function Shell({
  children,
  rail,
  focus = false,
}: {
  children: React.ReactNode;
  rail?: React.ReactNode;
  /**
   * Focus Stage: only the wordmark and a way out. No secondary navigation,
   * no palette hint, no tab bar — nothing competing with the lesson.
   */
  focus?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useT();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const tabbar = useRef<HTMLElement>(null);

  // The bar's real height — safe-area padding included, zero once it is
  // hidden — as a CSS variable, so a sticky composer can sit on it without
  // repeating the number (see Lesson.tsx).
  useEffect(() => {
    const bar = tabbar.current;
    if (!bar || typeof ResizeObserver === 'undefined') return;
    const root = document.documentElement;
    const observer = new ResizeObserver(() => {
      root.style.setProperty('--noema-tabbar-height', `${bar.getBoundingClientRect().height}px`);
    });
    observer.observe(bar);
    return () => {
      observer.disconnect();
      root.style.removeProperty('--noema-tabbar-height');
    };
  }, []);

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

  // The places. `match` decides which is "current" for routes that live
  // under a place without sharing its prefix (a notebook is Notes; the
  // Professor inside it is Learn).
  const places = [
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
    { href: '/goals', label: t.nav.goals, match: (p: string) => p.startsWith('/goals') },
  ];
  // The bottom bar has room for five; Goals is one tap away in the palette.
  const barPlaces = places.slice(0, 5);

  const railLink = (active: boolean) =>
    `-ml-5 block border-l-2 py-1.5 pl-[18px] text-base transition-colors duration-state ${
      active
        ? 'border-primary text-primary'
        : 'border-transparent text-ink-600 hover:text-ink-900'
    }`;
  const quiet =
    'block text-sm text-ink-500 transition-colors duration-state hover:text-ink-900';

  return (
    <div className="flex min-h-screen">
      {!collapsed && (
        <nav
          aria-label={t.nav.railLabel}
          className="noema-rail sticky top-0 hidden h-screen w-56 shrink-0 flex-col overflow-y-auto border-r border-line bg-surface px-5 py-6 md:flex"
        >
          <div className="flex items-center justify-between">
            <Wordmark href="/today" size="md" className="text-ink-900" />
            <button
              type="button"
              onClick={toggleRail}
              aria-label={t.nav.collapse}
              className="px-1 text-xs text-ink-400 transition-colors duration-state hover:text-ink-900"
            >
              ‹
            </button>
          </div>

          {focus && (
            <p className="mt-8 text-xs text-ink-500" data-focus-rail>
              {t.nav.focusOn}{' '}
              <Link href="/settings" className="text-ink-900 underline-offset-2 hover:underline">
                {t.nav.focusExit}
              </Link>
            </p>
          )}
          <ul className={`mt-10 space-y-0.5 ${focus ? 'hidden' : ''}`}>
            {places.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={link.match(pathname) ? 'page' : undefined}
                  className={railLink(link.match(pathname))}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>

          <div className="mt-auto space-y-2.5">
            <Link
              href="/settings"
              aria-current={pathname.startsWith('/settings') ? 'page' : undefined}
              className={`${quiet} ${pathname.startsWith('/settings') ? 'text-ink-900' : ''}`}
            >
              {t.nav.settings}
            </Link>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className={`${quiet} flex w-full items-center justify-between ${focus ? 'hidden' : ''}`}
            >
              {t.nav.commandPalette}
              <kbd className="font-mono text-[10px] text-ink-400">⌘K</kbd>
            </button>
            <button
              type="button"
              onClick={async () => {
                await api.logout();
                router.push('/');
              }}
              className={quiet}
            >
              {t.nav.signOut}
            </button>
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

      {/* Below `md`: five places as a bottom bar, plus one item for
          everything else (the palette). Short labels, one line each — a bar
          that wraps is worse than a shorter one. Gone in Focus, like the rail
          lists; padded past the home indicator on phones. */}
      <nav
        ref={tabbar}
        aria-label={t.nav.tabbarLabel}
        className={`noema-tabbar fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden ${
          focus ? 'hidden' : 'flex'
        }`}
      >
        {barPlaces.map((link) => {
          const active = link.match(pathname);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? 'page' : undefined}
              className={`flex-1 whitespace-nowrap py-3 text-center text-xs transition-colors duration-state ${
                active ? 'text-primary' : 'text-ink-500'
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

      <main className="min-w-0 flex-1 px-6 pb-24 pt-10 md:px-12 md:pb-10 lg:px-16">
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
