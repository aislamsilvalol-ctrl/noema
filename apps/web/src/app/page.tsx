'use client';

// Client-rendered since i18n: the pillars and the lede follow the visitor's
// language, which only the browser knows. The static export still serves the
// English shell for crawlers, which is also what the <html lang> promises.
//
// Pricing is fetched live from GET /billing/plans (public, no auth -- see
// noema/api/v1/billing.py's own docstring: "a plan's price is not a
// secret") rather than duplicated as static copy, so this page can never
// show a price PlanConfig itself does not. Local-mode deployments hide it
// entirely, the same reasoning /settings already uses: there is no account
// to bill self-hosted.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { MinoStage } from '@/components/landing/MinoStage';
import { api, type Meta, type Plan, type PlanPrice } from '@/lib/api';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

export default function LandingPage() {
  const t = useT();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [plans, setPlans] = useState<PlanPrice[]>([]);
  const [plansError, setPlansError] = useState(false);
  // Starts false rather than null: a visitor who is not signed in is the
  // overwhelmingly common case for a marketing page, and `/login` (the
  // signed-out CTA) is exactly right while `api.me()` is still in flight.
  // Flipping to true a moment after render is a cheap, honest correction --
  // guessing "probably signed in" and reverting would flash the wrong CTA
  // the other, more disruptive direction.
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.meta(), api.plans()])
      .then(([m, p]) => {
        if (cancelled) return;
        setMeta(m);
        setPlans(p);
      })
      .catch(() => {
        if (!cancelled) setPlansError(true);
      });
    api
      .me()
      .then(() => {
        if (!cancelled) setSignedIn(true);
      })
      .catch(() => {
        // Not signed in, or the check failed -- either way the signed-out
        // CTA (`/login`) is the safe default already in state.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const primaryHref = signedIn ? '/today' : '/login';
  const primaryLabel = signedIn ? t.landing.continueLearning : t.landing.start;

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
          <Link href={primaryHref} className="transition-colors duration-state hover:text-ink-900">
            {signedIn ? t.landing.continueLearning : t.landing.signIn}
          </Link>
          <LanguageSwitcher />
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl gap-12 px-6 pb-24 pt-20 md:grid-cols-[1.2fr_1fr] md:items-center md:pt-32">
        <div>
          <h1 className="max-w-3xl font-display text-3xl text-ink-900 md:text-4xl">
            {t.landing.title1}
            <br />
            {t.landing.title2}
          </h1>

          <p className="mt-8 max-w-reading font-serif text-md text-ink-600">{t.landing.lede}</p>

          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Link
              href={primaryHref}
              className="rounded-md bg-ink-900 px-5 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
            >
              {primaryLabel}
            </Link>
            <a
              href="https://github.com/aislamsilvalol-ctrl/noema"
              className="rounded-md border border-line px-5 py-2.5 text-sm font-medium text-ink-700 transition-colors duration-state hover:border-ink-400"
            >
              {t.landing.viewGithub}
            </a>
          </div>
        </div>

        <MinoStage state="hero" className="mx-auto w-full max-w-xs md:max-w-sm" />
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-px bg-line px-6 md:grid-cols-2 lg:grid-cols-3">
          {t.landing.pillars.map((pillar) => (
            <article key={pillar.title} className="bg-surface px-2 py-12 md:px-8">
              <h2 className="text-lg text-ink-900">{pillar.title}</h2>
              <p className="mt-3 max-w-reading text-base text-ink-600">{pillar.body}</p>
            </article>
          ))}
        </div>
      </section>

      {!meta?.local && (plans.length > 0 || plansError) && (
        <section className="border-t border-line px-6 py-24">
          <div className="mx-auto max-w-6xl">
            <h2 className="font-display text-2xl text-ink-900">{t.landing.pricingTitle}</h2>
            <p className="mt-3 max-w-reading text-base text-ink-600">{t.landing.pricingLede}</p>

            {plansError ? (
              <p role="alert" className="mt-8 text-sm text-critical">
                {t.landing.plansError}
              </p>
            ) : (
              <ul className="mt-10 grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
                {plans.map((p) => (
                  <li key={p.plan} className="bg-surface p-6">
                    <p className="text-sm font-medium text-ink-900">{planLabel(p.plan, t)}</p>
                    <p className="mt-2 font-display text-xl text-ink-900">
                      {cents(p.monthly_price_cents)}
                      <span className="ml-1 text-sm font-normal text-ink-500">
                        /{t.settings.perMonth}
                      </span>
                    </p>
                    <Link
                      href={primaryHref}
                      className="mt-6 block rounded-md border border-line px-4 py-2 text-center text-sm text-ink-800 transition-colors duration-state hover:border-ink-400"
                    >
                      {primaryLabel}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      <section className="mx-auto max-w-6xl px-6 py-24">
        <p className="max-w-reading font-serif text-md text-ink-600">
          {t.landing.principle1}
          <em className="text-ink-900">{t.landing.principleEm}</em>
          {t.landing.principle2}
        </p>
      </section>

      <section className="border-t border-line px-6 py-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-lg text-ink-900">{t.landing.selfHostTitle}</h2>
          <p className="mt-3 max-w-reading text-base text-ink-600">{t.landing.selfHostBody}</p>
        </div>
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

function cents(value: number): string {
  return (value / 100).toLocaleString(undefined, {
    style: 'currency',
    currency: 'BRL',
  });
}

function planLabel(plan: Plan, t: Dict): string {
  switch (plan) {
    case 'student':
      return t.settings.planStudent;
    case 'pro':
      return t.settings.planPro;
    case 'max':
      return t.settings.planMax;
    default:
      return t.settings.planFree;
  }
}
