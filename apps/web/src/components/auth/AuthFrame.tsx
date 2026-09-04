/**
 * The frame around signing in, creating an account and resetting a password.
 *
 * On a wide screen the form sits beside a quiet panel with Mino at rest and
 * one sentence — enough to say you are entering a learning space, not a
 * generic form. On a phone the panel is gone and the form has the screen.
 * The language control lives here so every auth screen has it in the same
 * place. No logic: each page keeps its own.
 */

import type { ReactNode } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Wordmark } from '@/components/brand/Wordmark';
import { Mino } from '@/components/mino/Mino';

export function AuthFrame({ aside, children }: { aside: string; children: ReactNode }) {
  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="hidden bg-sunken lg:flex lg:flex-col lg:justify-between lg:px-12 lg:py-12">
        <Wordmark size="md" className="text-ink-900" />
        <div>
          <Mino state="idle" size="lg" />
          <p className="mt-6 max-w-xs font-serif text-md text-ink-700">{aside}</p>
        </div>
        <span className="text-xs text-ink-500">Open source · AGPL</span>
      </aside>

      <div className="flex min-h-screen flex-col justify-center px-6 py-12 lg:px-16">
        <span className="mb-10 lg:hidden">
          <Wordmark size="md" className="text-ink-900" />
        </span>
        <div className="w-full max-w-sm">{children}</div>
        <div className="mt-12 max-w-sm">
          <LanguageSwitcher />
        </div>
      </div>
    </main>
  );
}
