'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { CommandPalette } from '@/components/CommandPalette';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useT } from '@/lib/i18n';

/**
 * The three-region shell from `docs/design-system.md`: navigation, content at a
 * reading measure, and a context rail. The rail is passed in rather than assembled
 * here so each route decides what belongs beside its content.
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

  const links = [
    { href: '/chat', label: t.nav.chat },
    { href: '/today', label: t.nav.today },
    { href: '/library', label: t.nav.library },
    { href: '/goals', label: t.nav.goals },
    { href: '/review', label: t.nav.review },
    { href: '/explain', label: t.nav.explain },
    { href: '/socratic', label: t.nav.socratic },
    { href: '/mistakes', label: t.nav.mistakes },
    { href: '/graph', label: t.nav.graph },
    { href: '/progress', label: t.nav.progress },
    { href: '/settings', label: t.nav.settings },
  ];

  //: Four fit across a phone with their labels legible. Ten did not — they
  //: rendered as one unbroken word — and a bar nobody can read is worse than a
  //: shorter one. The rest are a tap away through the palette, which is already
  //: this app's way of getting anywhere.
  const primary = links.slice(0, 4);

  return (
    <div className="flex min-h-screen">
      <nav className="hidden w-60 shrink-0 flex-col border-r border-line px-4 py-6 md:flex">
        <Link href="/today" className="px-2 font-display text-lg text-ink-900">
          NOEMA
        </Link>

        <ul className="mt-8 space-y-0.5">
          {links.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className={`block rounded-md px-2 py-1.5 text-sm transition-colors duration-state ${
                    active ? 'bg-ink-100 text-ink-900' : 'text-ink-600 hover:text-ink-900'
                  }`}
                >
                  {link.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="mt-auto space-y-2 px-2">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex w-full items-center justify-between text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
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
            className="text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {t.nav.signOut}
          </button>
          <LanguageSwitcher />
        </div>
      </nav>

      {/* Below `md` the sidebar is gone, and until now nothing replaced it: on a
          phone you could open a review and have no way back except the browser's
          own button. A bottom bar rather than a hamburger, because these are four
          destinations someone moves between constantly, not a menu to go hunting
          in. `pb-24` on main keeps the last row of content clear of it. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-surface md:hidden">
        {primary.map((link) => {
          const active = pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? 'page' : undefined}
              className={`flex-1 py-3 text-center text-xs transition-colors duration-state ${
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
          className="flex-1 py-3 text-center text-xs text-ink-500 transition-colors duration-state"
        >
          {t.nav.more}
        </button>
      </nav>

      <main className="min-w-0 flex-1 px-6 pb-24 pt-10 md:px-12 md:pb-10">
        {children}

        {/* Below `xl` the rail has nowhere to stand, and it used to simply not
            render — which meant the tutor, the product's headline feature, did
            not exist on a laptop under 1280px or on any phone at all. It moves
            under the content instead of disappearing. */}
        {rail && (
          <section className="mt-12 border-t border-line pt-8 xl:hidden">
            {rail}
          </section>
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
