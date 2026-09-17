'use client';

/**
 * The landing as a world: nine screens with a breath between them.
 *
 * Valley (the hero) · statement · two routes · Mino teaches · the map ·
 * trail · today · a close-up · horizon. Landscapes are the protagonist; the
 * type sits on them or on bone; the only card on the page is none. One
 * chromatic universe throughout (docs/brand-os.md, 2026-09-17 revision).
 *
 * Honesty rules: the tutor exchange in screen four is a written example
 * labelled as one, and the field under it calls the real tutor; every
 * illustrative number says so; nothing counts users that do not exist.
 */

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Wordmark } from '@/components/brand/Wordmark';
import { Button, ButtonLink } from '@/components/ui/Button';
import { track } from '@/lib/analytics';
import { ApiError, api, demoTeach } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { Markdown } from '@/lib/markdown';
import { rememberPrefill } from '@/lib/prefill';
import { KnowledgeMap } from './KnowledgeMap';
import { Landscape } from './Landscape';
import { bankFor } from './subjects';
import '@/styles/landing.css';

type DemoStatus = 'idle' | 'streaming' | 'live' | 'sample';

/** Adds `is-in` once to every `[data-reveal]` that reaches the viewport; progressive. */
function useReveal() {
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const reduced = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.documentElement.classList.add('js-reveal');
    const nodes = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]:not(.is-in)'));
    if (reduced) {
      for (const node of nodes) node.classList.add('is-in');
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
    );
    for (const node of nodes) {
      if (node.getBoundingClientRect().top < window.innerHeight) node.classList.add('is-in');
      else io.observe(node);
    }
    return () => io.disconnect();
  }, []);
}

export function LandingV5() {
  const { t, locale } = useI18n();
  const copy = t.landing6;
  useReveal();

  const [signedIn, setSignedIn] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [subject, setSubject] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [status, setStatus] = useState<DemoStatus>('idle');
  const abort = useRef<AbortController | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(() => {
        if (!cancelled) setSignedIn(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([entry]) => {
      if (entry) setStuck(!entry.isIntersecting);
    });
    io.observe(node);
    return () => io.disconnect();
  }, []);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const trimmed = subject.trim();
    if (!trimmed || status === 'streaming') return;
    track('cta_clicked', { location: 'teach_ask' });
    setAsked(trimmed);
    setReply('');
    setStatus('streaming');
    abort.current?.abort();
    abort.current = new AbortController();
    let sawToken = false;
    let failed = false;
    try {
      await demoTeach(
        trimmed,
        {
          onToken: (text) => {
            sawToken = true;
            setReply((current) => current + text);
          },
          onError: () => {
            failed = true;
          },
        },
        abort.current.signal,
      );
    } catch (err) {
      failed = !(err instanceof DOMException && err.name === 'AbortError');
      if (err instanceof ApiError) failed = true;
    }
    if (failed || !sawToken) {
      setReply(bankFor(trimmed, locale).sample);
      setStatus('sample');
    } else {
      setStatus('live');
    }
  }

  function start(location: string) {
    if (asked) rememberPrefill(asked);
    track('cta_clicked', { location });
  }

  const primaryHref = signedIn ? '/today' : '/login?mode=register';
  const primaryLabel = signedIn ? copy.nav.continueLearning : copy.nav.start;
  const navLinks: [string, string][] = [
    ['#how', copy.nav.how],
    ['#map', copy.nav.map],
    ['/pricing', copy.nav.pricing],
  ];
  const routesSubject = asked ?? bankFor('Freud', locale).label;

  return (
    <main className="field field-bone min-h-screen">
      <a
        href="#how"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:text-ink-900"
      >
        {copy.nav.how}
      </a>
      <div ref={sentinel} aria-hidden="true" className="absolute top-[70vh] h-px w-px" />

      {/* ── 01 · the valley ───────────────────────────────────────────────── */}
      <section className="scene scene-drift scene-veil-bottom grain min-h-[100svh]">
        <Landscape scene="valley" priority position="72% 62%" />

        <header className={`landing-nav fixed inset-x-0 top-0 z-30 ${stuck ? 'is-stuck text-ink-900' : 'text-[#f6f2ea]'}`}>
          <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-6 py-5 md:px-10">
            <Wordmark size="md" className="text-current" />
            <nav aria-label={copy.nav.menu} className="hidden items-center gap-7 text-sm opacity-90 md:flex">
              {navLinks.map(([href, label]) =>
                href.startsWith('#') ? (
                  <a key={href} href={href} className="transition-opacity duration-fast hover:opacity-100">
                    {label}
                  </a>
                ) : (
                  <Link key={href} href={href} className="transition-opacity duration-fast hover:opacity-100">
                    {label}
                  </Link>
                ),
              )}
            </nav>
            <div className="flex items-center gap-4">
              <LanguageSwitcher className="hidden text-current sm:block" />
              {!signedIn && (
                <Link href="/login" className="hidden text-sm opacity-90 hover:opacity-100 sm:block">
                  {copy.nav.signIn}
                </Link>
              )}
              <ButtonLink
                href={primaryHref}
                size="sm"
                onClick={() => start('header')}
                className="btn-ember hidden sm:inline-flex"
              >
                {primaryLabel}
              </ButtonLink>
              <button
                type="button"
                aria-expanded={menuOpen}
                aria-controls="landing-menu"
                onClick={() => setMenuOpen((open) => !open)}
                className="rounded-md border border-current/40 px-3 py-1.5 text-sm md:hidden"
              >
                {copy.nav.menu}
              </button>
            </div>
          </div>
          {menuOpen && (
            <div id="landing-menu" className="border-t border-line bg-surface px-6 py-4 text-ink-900 md:hidden">
              <nav aria-label={copy.nav.menu} className="flex flex-col gap-3 text-base">
                {navLinks.map(([href, label]) => (
                  <a key={href} href={href} onClick={() => setMenuOpen(false)}>
                    {label}
                  </a>
                ))}
                {!signedIn && <Link href="/login">{copy.nav.signIn}</Link>}
                <ButtonLink href={primaryHref} variant="primary" onClick={() => start('menu')}>
                  {primaryLabel}
                </ButtonLink>
                <LanguageSwitcher className="mt-2" />
              </nav>
            </div>
          )}
        </header>

        <div className="content mx-auto flex min-h-[100svh] max-w-[1400px] flex-col justify-end px-6 pb-14 pt-32 md:px-10 md:pb-20">
          <p className="meta fg-faint mb-6 text-[#f6f2ea]/70">{copy.hero.caption}</p>
          <h1 className="display-1 max-w-[12ch] text-[#f6f2ea]">{copy.hero.line}</h1>
          <p className="mt-5 max-w-[34ch] text-lg text-[#f6f2ea]/85 md:text-xl">{copy.hero.sub}</p>
          <div className="mt-8 flex flex-wrap items-center gap-5">
            <ButtonLink
              href={primaryHref}
              size="lg"
              onClick={() => start('hero')}
              className="btn-ember"
            >
              {signedIn ? copy.nav.continueLearning : copy.hero.cta}
            </ButtonLink>
            <a href="#how" className="text-sm text-[#f6f2ea]/85 underline-offset-4 hover:underline">
              {copy.hero.secondary} →
            </a>
          </div>
        </div>
      </section>

      {/* ── 02 · the statement ────────────────────────────────────────────── */}
      <section className="field field-bone grain">
        <div className="mx-auto max-w-[1400px] px-6 py-28 md:px-10 md:py-44">
          <p className="display-2 max-w-[22ch]" data-reveal>
            {copy.statement.line}
          </p>
        </div>
      </section>

      {/* ── 03 · two routes ───────────────────────────────────────────────── */}
      <section id="how" className="scene scene-veil-top grain">
        <Landscape scene="routes" position="50% 50%" />
        <svg
          aria-hidden="true"
          viewBox="0 0 1600 900"
          preserveAspectRatio="xMidYMid slice"
          className="pointer-events-none absolute inset-0 z-[1] h-full w-full"
        >
          <path d="M 380 900 C 420 720, 520 640, 760 560 S 1000 470, 1120 430" fill="none" stroke="#ffb07a" strokeWidth="3" strokeDasharray="2 10" strokeLinecap="round" />
          <path d="M 1150 900 C 1090 760, 980 700, 900 610 S 880 500, 1110 440" fill="none" stroke="#f6f2ea" strokeWidth="3" strokeDasharray="14 12" strokeLinecap="round" opacity="0.9" />
          <circle cx="1118" cy="432" r="7" fill="#ffb07a" />
        </svg>
        <div className="content mx-auto max-w-[1400px] px-6 py-24 md:px-10 md:py-32">
          <p className="meta text-[#ffb07a]">{copy.routes.kicker}</p>
          <h2 className="display-2 mt-4 max-w-[16ch]" data-reveal>
            {copy.routes.title}
          </h2>
          <p className="mt-6 max-w-[44ch] text-md text-[#f6f2ea]/80" data-reveal>
            {copy.routes.body}
          </p>
          <p className="meta mt-16 text-[#f6f2ea]/60">{routesSubject}</p>
          <div className="mt-4 grid max-w-3xl gap-10 md:grid-cols-2 md:gap-16">
            {[copy.routes.a, copy.routes.b].map((person, index) => (
              <div key={person.name} className="border-t border-[#f6f2ea]/25 pt-5" data-reveal>
                <p className="font-display text-2xl">{person.name}</p>
                <p className="mt-1 text-base text-[#f6f2ea]/75">“{person.said}”</p>
                <ol className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
                  {person.route.map((step, i) => (
                    <li key={step} className="flex items-center gap-3">
                      <span className={i === 0 ? 'text-[#ffb07a]' : ''}>{step}</span>
                      {i < person.route.length - 1 && <span aria-hidden="true" className="text-[#f6f2ea]/40">→</span>}
                    </li>
                  ))}
                </ol>
                {index === 1 && <p className="meta mt-6 text-[#f6f2ea]/50">{copy.routes.note}</p>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 04 · Mino teaches ─────────────────────────────────────────────── */}
      <section className="field field-bone">
        <div className="mx-auto grid max-w-[1400px] gap-14 px-6 py-24 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:px-10 md:py-36">
          <div>
            <p className="meta accent-on">{copy.teach.kicker}</p>
            <h2 className="display-2 mt-4 max-w-[16ch]" data-reveal>
              {copy.teach.title}
            </h2>
            <p className="fg-muted mt-6 max-w-[46ch] text-md" data-reveal>
              {copy.teach.body}
            </p>
            <p className="meta fg-faint mt-12">{copy.teach.signalsLabel}</p>
            <ul className="mt-2 max-w-md">
              {copy.teach.signals.map((line) => (
                <li key={line} className="border-t border-line py-3 text-md text-ink-900" data-reveal>
                  {line}
                </li>
              ))}
            </ul>
          </div>

          <div className="md:pt-16" data-reveal>
            <ol className="max-w-xl">
              {copy.teach.exchange.map((line, index) => (
                <li key={index} className="border-t border-line py-4">
                  <Speaker>{line.who === 'mino' ? 'Mino' : copy.teach.you}</Speaker>
                  <p className={`mt-1 text-md ${line.who === 'mino' ? 'text-ink-900' : 'fg-muted'}`}>{line.text}</p>
                </li>
              ))}
            </ol>

            <form onSubmit={ask} className="mt-10 max-w-xl border-t border-line pt-8">
              <label htmlFor="teach-subject" className="font-display text-xl text-ink-900">
                {t.landing5.hero.label}
              </label>
              <div className="mt-4 flex gap-2">
                <input
                  id="teach-subject"
                  ref={input}
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder={t.landing5.hero.placeholder}
                  autoComplete="off"
                  enterKeyHint="go"
                  className="min-w-0 flex-1 border-b-2 border-line bg-transparent px-0 py-3 text-lg text-ink-900 outline-none transition-colors duration-fast placeholder:text-ink-400 focus:border-primary"
                />
                <Button type="submit" variant="primary" disabled={!subject.trim()} busy={status === 'streaming' ? t.landing5.hero.thinking : undefined}>
                  {t.landing5.hero.submit}
                </Button>
              </div>
              {asked && (
                <div className="mt-6 animate-fade-up" aria-busy={status === 'streaming' || undefined}>
                  <Speaker>Mino</Speaker>
                  <div className="mt-2 min-h-[3rem]">
                    {reply ? <Markdown text={reply} className="text-md" /> : <p className="text-sm text-ink-600">{t.landing5.hero.thinking}</p>}
                  </div>
                  {status !== 'streaming' && (
                    <p className="mt-3 text-sm text-ink-600" aria-live="polite">
                      {status === 'live' ? t.landing5.hero.liveNote : t.landing5.hero.sampleNote}
                    </p>
                  )}
                </div>
              )}
              {!asked && <p className="mt-3 text-sm text-ink-600">{t.landing5.hero.note}</p>}
            </form>
          </div>
        </div>
      </section>

      {/* ── 05 · the map ──────────────────────────────────────────────────── */}
      <section id="map" className="field field-cobalt grain">
        <div className="mx-auto grid max-w-[1400px] gap-12 px-6 py-24 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:items-center md:px-10 md:py-36">
          <div>
            <p className="meta accent-on">{copy.map.kicker}</p>
            <h2 className="display-2 mt-4 max-w-[14ch]" data-reveal>
              {copy.map.title}
            </h2>
            <p className="fg-muted mt-6 max-w-[42ch] text-md" data-reveal>
              {copy.map.body}
            </p>
            <p className="meta fg-faint mt-8">{copy.map.note}</p>
          </div>
          <div data-reveal>
            <KnowledgeMap locale={locale} labels={t.landing5.map.states} now={t.landing5.learns.pathNow} />
          </div>
        </div>
      </section>

      {/* ── 06 · the trail ────────────────────────────────────────────────── */}
      <section className="scene scene-drift scene-veil-bottom grain min-h-[80svh]">
        <Landscape scene="trail" position="70% 55%" />
        <div className="content mx-auto flex min-h-[80svh] max-w-[1400px] flex-col justify-end px-6 pb-16 md:px-10 md:pb-24">
          <p className="display-2 max-w-[20ch]" data-reveal>
            {copy.trail.line}
          </p>
        </div>
      </section>

      {/* ── 07 · today ────────────────────────────────────────────────────── */}
      <section className="field field-bone">
        <div className="mx-auto grid max-w-[1400px] gap-14 px-6 py-24 md:grid-cols-[minmax(0,6fr)_minmax(0,6fr)] md:items-center md:px-10 md:py-36">
          <div>
            <p className="meta accent-on">{copy.today.kicker}</p>
            <h2 className="display-2 mt-4 max-w-[14ch]" data-reveal>
              {copy.today.title}
            </h2>
            <p className="fg-muted mt-6 max-w-[44ch] text-md" data-reveal>
              {copy.today.body}
            </p>
          </div>
          <div className="max-w-md md:justify-self-end" data-reveal>
            <div className="flex items-baseline justify-between">
              <span className="meta fg-faint">{copy.today.kicker}</span>
              <span className="font-display text-3xl text-ink-900">{copy.today.total}</span>
            </div>
            <ol className="mt-4">
              {copy.today.plan.map(([name, minutes], index) => (
                <li key={name} className="flex items-baseline justify-between gap-6 border-t border-line py-4">
                  <span className="flex items-baseline gap-4">
                    <span className="meta fg-faint">{String(index + 1).padStart(2, '0')}</span>
                    <span className="text-md text-ink-900">{name}</span>
                  </span>
                  <span className="meta fg-muted">{minutes}</span>
                </li>
              ))}
            </ol>
            <div className="mt-6 flex items-center gap-4 border-t border-line pt-6">
              <ButtonLink href={primaryHref} variant="primary" onClick={() => start('today')}>
                {copy.today.start}
              </ButtonLink>
              <span className="text-xs text-ink-500">{copy.today.note}</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── 08 · a close-up ───────────────────────────────────────────────── */}
      <section className="scene grain min-h-[70svh]">
        <Landscape scene="closeup" position="60% 45%" />
        <div className="content mx-auto flex min-h-[70svh] max-w-[1400px] items-end px-6 pb-16 md:px-10 md:pb-24">
          <p className="display-3 max-w-[30ch]" data-reveal>
            {copy.close.quote}
          </p>
        </div>
      </section>

      {/* ── 09 · the horizon ──────────────────────────────────────────────── */}
      <section className="scene scene-drift scene-veil-bottom grain">
        <Landscape scene="horizon" position="50% 70%" />
        <div className="content mx-auto max-w-[1400px] px-6 pb-10 pt-40 md:px-10 md:pt-56">
          <h2 className="display-1 max-w-[12ch]">{copy.horizon.line}</h2>
          <p className="mt-5 max-w-[40ch] text-lg text-[#f6f2ea]/85">{copy.horizon.body}</p>
          <ButtonLink
            href={primaryHref}
            size="lg"
            onClick={() => start('landing_close')}
            className="btn-ember mt-8"
          >
            {signedIn ? copy.nav.continueLearning : copy.horizon.cta}
          </ButtonLink>
          <footer className="mt-28 flex flex-wrap items-center justify-between gap-4 border-t border-[#f6f2ea]/25 pt-6 text-sm text-[#f6f2ea]/75">
            <span className="flex items-center gap-4">
              <Wordmark size="sm" className="text-[#f6f2ea]" />
              <span>{copy.footer.license}</span>
            </span>
            <nav className="flex items-center gap-5" aria-label={copy.footer.code}>
              <Link href="/pricing" className="hover:text-[#f6f2ea]">{copy.footer.pricing}</Link>
              <a href="https://github.com/aislamsilvalol-ctrl/noema" className="hover:text-[#f6f2ea]">{copy.footer.code}</a>
              <Link href="/privacy" className="hover:text-[#f6f2ea]">{copy.footer.privacy}</Link>
              <Link href="/terms" className="hover:text-[#f6f2ea]">{copy.footer.terms}</Link>
            </nav>
          </footer>
        </div>
      </section>
    </main>
  );
}

/** Who is speaking, above a line of dialogue. */
function Speaker({ children }: { children: ReactNode }) {
  return <p className="meta accent-on">{children}</p>;
}
