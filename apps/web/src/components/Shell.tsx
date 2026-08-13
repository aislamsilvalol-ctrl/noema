'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { CommandPalette } from '@/components/CommandPalette';

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
    { href: '/today', label: 'Today' },
    { href: '/library', label: 'Library' },
    { href: '/review', label: 'Review' },
    { href: '/explain', label: 'Explain' },
    { href: '/mistakes', label: 'Mistakes' },
    { href: '/progress', label: 'Progress' },
    { href: '/settings', label: 'Settings' },
  ];

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
            Command palette
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
            Sign out
          </button>
        </div>
      </nav>

      {/* Below `md` the sidebar is gone, and until now nothing replaced it: on a
          phone you could open a review and have no way back except the browser's
          own button. A bottom bar rather than a hamburger, because these are four
          destinations someone moves between constantly, not a menu to go hunting
          in. `pb-24` on main keeps the last row of content clear of it. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-surface md:hidden">
        {links.map((link) => {
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
      </nav>

      <main className="min-w-0 flex-1 px-6 pb-24 pt-10 md:px-12 md:pb-10">
        {children}
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
