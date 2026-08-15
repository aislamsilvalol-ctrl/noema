'use client';

// Client-rendered since i18n: the pillars and the lede follow the visitor's
// language, which only the browser knows. The static export still serves the
// English shell for crawlers, which is also what the <html lang> promises.

import Link from 'next/link';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useT } from '@/lib/i18n';

export default function LandingPage() {
  const t = useT();

  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <span className="font-display text-lg tracking-tight text-ink-900">NOEMA</span>
        <nav className="flex items-center gap-4 text-sm text-ink-600 sm:gap-6">
          <a
            href="https://github.com/aislamsilvalol-ctrl/noema"
            className="transition-colors duration-state hover:text-ink-900"
          >
            GitHub
          </a>
          <Link href="/login" className="transition-colors duration-state hover:text-ink-900">
            {t.landing.signIn}
          </Link>
          <LanguageSwitcher />
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-6 pb-24 pt-20 md:pt-32">
        <h1 className="max-w-3xl font-display text-3xl text-ink-900 md:text-4xl">
          {t.landing.title1}
          <br />
          {t.landing.title2}
        </h1>

        <p className="mt-8 max-w-reading font-serif text-md text-ink-600">
          {t.landing.lede}
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-4">
          <Link
            href="/login"
            className="rounded-md bg-ink-900 px-5 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
          >
            {t.landing.start}
          </Link>
          <a
            href="https://github.com/aislamsilvalol-ctrl/noema"
            className="rounded-md border border-line px-5 py-2.5 text-sm font-medium text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            {t.landing.viewGithub}
          </a>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-px bg-line px-6 md:grid-cols-2">
          {t.landing.pillars.map((pillar) => (
            <article key={pillar.title} className="bg-surface px-2 py-12 md:px-8">
              <h2 className="text-lg text-ink-900">{pillar.title}</h2>
              <p className="mt-3 max-w-reading text-base text-ink-600">{pillar.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-24">
        <p className="max-w-reading font-serif text-md text-ink-600">
          {t.landing.principle1}
          <em className="text-ink-900">{t.landing.principleEm}</em>
          {t.landing.principle2}
        </p>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-ink-500">
          <span>{t.landing.license}</span>
          <span className="font-display">{t.landing.tagline}</span>
        </div>
      </footer>
    </main>
  );
}
