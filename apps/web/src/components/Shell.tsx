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
    { href: '/library', label: 'Library' },
    { href: '/settings', label: 'Settings' },
  ];

  return (
    <div className="flex min-h-screen">
      <nav className="hidden w-60 shrink-0 flex-col border-r border-line px-4 py-6 md:flex">
        <Link href="/library" className="px-2 font-display text-lg text-ink-900">
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

      <main className="min-w-0 flex-1 px-6 py-10 md:px-12">{children}</main>

      {rail && (
        <aside className="hidden w-80 shrink-0 border-l border-line px-6 py-10 xl:block">
          {rail}
        </aside>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
