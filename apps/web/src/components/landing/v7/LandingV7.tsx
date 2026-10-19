'use client';

/**
 * The landing, v7 (2026-10-19): the same world, a shorter film, the product
 * in the second screen. Audit and plan: docs/landing-v7.md.
 *
 * 01 Terraces — the promise, Mino, one action. The camera walks toward him.
 * 02 A lesson, played — Mino asks, the learner errs, Mino changes approach,
 *    the learner gets it; then the visitor asks the real tutor.
 * 03 Why it works — three ideas over three frames of the same land, each
 *    with the piece of the product that proves it.
 * 04 ADHD mode — five minutes, one thing, on the bleached frame.
 * 05 Territory → map.
 * 06 Horizon — the close.
 *
 * Mechanics are v6's: `useSceneProgress` writes `--p` on the pinned scenes
 * and CSS moves transform, opacity and clip-path from it; `.v6-motion` gates
 * every scroll-linked effect, so reduced motion gets complete, still scenes.
 * Nothing here counts users or invents results.
 */

import Link from 'next/link';
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Wordmark } from '@/components/brand/Wordmark';
import { ButtonLink } from '@/components/ui/Button';
import { track } from '@/lib/analytics';
import { api } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { KnowledgeMap } from '../v5/KnowledgeMap';
import { useReveal } from '../v5/LandingV5';
import { Landscape } from '../v5/Landscape';
import { SceneFilm, type Film } from '../v5/SceneFilm';
import { prefersReducedMotion, refreshScenes, useSceneProgress } from '../v6/useSceneProgress';
import { FocusDemo } from './FocusDemo';
import { Hero } from './Hero';
import { LessonDemo } from './LessonDemo';
import '@/styles/landing.css';
import '@/styles/landing-v6.css';
import '@/styles/landing-v7.css';

const FILMS: Record<'routes' | 'horizon', Film> = {
  routes: { src: '/brand/film/routes', mobile: true },
  horizon: { src: '/brand/film/horizon', mobile: true },
};

const STATE_MARK: Record<string, [string, string]> = {
  mastered: ['●', 'text-positive'],
  learning: ['◐', 'text-signal'],
  unknown: ['○', 'text-ink-300'],
};

function vars(values: Record<string, string | number>): CSSProperties {
  return values as CSSProperties;
}

export function LandingV7() {
  const { t, locale } = useI18n();
  const copy = t.landing7;
  const footer = t.landing6.footer;
  const states = t.landing5.map.states as Record<string, string>;
  useReveal();

  const [motion, setMotion] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [pastHero, setPastHero] = useState(false);
  const [atClose, setAtClose] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);

  const hero = useRef<HTMLElement>(null);
  const why = useRef<HTMLElement>(null);
  const territory = useRef<HTMLElement>(null);
  const horizon = useRef<HTMLElement>(null);
  useSceneProgress(hero);
  useSceneProgress(why);
  useSceneProgress(territory);
  useSceneProgress(horizon);

  useEffect(() => {
    if (!prefersReducedMotion()) setMotion(true);
  }, []);
  useEffect(() => {
    if (motion) refreshScenes();
  }, [motion]);

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

  // The header turns to bone once the hero has passed; the phone's action
  // bar shows between the hero and the close, which carries its own.
  useEffect(() => {
    const top = sentinel.current;
    const close = horizon.current;
    if (!top || !close || typeof IntersectionObserver === 'undefined') return;
    const watchTop = new IntersectionObserver(([entry]) => entry && setPastHero(!entry.isIntersecting));
    const watchClose = new IntersectionObserver(([entry]) => entry && setAtClose(entry.isIntersecting), {
      rootMargin: '0px 0px -40% 0px',
    });
    watchTop.observe(top);
    watchClose.observe(close);
    return () => {
      watchTop.disconnect();
      watchClose.disconnect();
    };
  }, []);

  function start(location: string) {
    track('cta_clicked', { location });
  }

  const primaryHref = signedIn ? '/today' : '/login?mode=register';
  const primaryLabel = signedIn ? copy.nav.continueLearning : copy.hero.cta;

  return (
    <main className={`landing-light landing-v6 landing-v7 min-h-screen ${motion ? 'v6-motion' : ''}`}>
      <a
        href="#demo"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:text-ink-900"
      >
        {copy.demo.kicker}
      </a>
      <div ref={sentinel} aria-hidden="true" className="absolute top-[70vh] h-px w-px" />

      <header className={`landing-nav fixed inset-x-0 top-0 z-30 ${pastHero ? 'is-stuck text-ink-900' : 'text-[#f6f2ea]'}`}>
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-5 py-4 md:px-10 md:py-5">
          <Wordmark size="md" className="text-current" />
          <nav aria-label={copy.nav.main} className="flex items-center gap-5 text-sm md:gap-7">
            <Link href="/pricing" className="hidden opacity-90 hover:opacity-100 sm:block">
              {copy.nav.pricing}
            </Link>
            {!signedIn && (
              <Link href="/login" className="l7-tap opacity-90 hover:opacity-100">
                {copy.nav.signIn}
              </Link>
            )}
            <LanguageSwitcher className="hidden text-current lg:block" />
            <ButtonLink href={primaryHref} size="sm" onClick={() => start('header')} className="btn-ember hidden sm:inline-flex">
              {signedIn ? copy.nav.continueLearning : copy.nav.start}
            </ButtonLink>
          </nav>
        </div>
      </header>

      {/* ── 01 · the terraces, in layers ──────────────────────────────────── */}
      <Hero
        sectionRef={hero}
        href={primaryHref}
        label={primaryLabel}
        showNote={!signedIn}
        onStart={() => start('hero')}
      />

      {/* ── 02 · a lesson, played ─────────────────────────────────────────── */}
      <section id="demo" className="field field-bone l7-demo-section">
        <div className="v6-shell">
          <div className="l7-head">
            <p className="meta fg-faint" data-reveal>
              {copy.demo.kicker}
            </p>
            <h2 className="v6-display mt-4 max-w-[14ch]" data-reveal>
              {copy.demo.title}
            </h2>
          </div>
          <LessonDemo />
        </div>
      </section>

      {/* ── 03 · why it works ─────────────────────────────────────────────── */}
      <section ref={why} className="v6-pin l7-why" data-steps={3} data-step={0} style={vars({ '--len': '320vh' })}>
        <div className="v6-frame l7-why-frame">
          {/* One path, walked: the camera travels along the trail as the
              three ideas pass, instead of cutting between frames. */}
          <div className="l7-why-stills" aria-hidden="true">
            <div className="l7-why-walk">
              <Landscape scene="trail" position="61% 62%" />
            </div>
          </div>
          <div className="l7-why-copy">
            <p className="meta fg-faint">{copy.why.kicker}</p>
            <ol className="l7-beats">
              {copy.why.items.map((item, index) => (
                <li key={item.title} className="l7-beat" data-beat={index}>
                  <h2 className="v6-display l7-beat-title">{item.title}</h2>
                  <p className="v6-body l7-beat-body">{item.body}</p>
                  <div className="l7-proof">
                    {index === 0 && (
                      <ul className="l7-states">
                        {copy.why.concepts.map(([concept, state]) => {
                          const [mark, tone] = STATE_MARK[state!] ?? STATE_MARK.unknown!;
                          return (
                            <li key={concept}>
                              <span className={tone}>{mark}</span>
                              <span className="text-ink-900">{concept}</span>
                              <span className="ml-auto font-mono text-xs text-ink-500">{states[state!]}</span>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                    {index === 1 && (
                      <ul className="l7-chips">
                        {copy.why.strategies.map((strategy, i) => (
                          <li key={strategy} className={i === 0 ? 'is-on' : ''}>
                            {strategy}
                          </li>
                        ))}
                      </ul>
                    )}
                    {index === 2 && (
                      <div className="l7-review">
                        <p className="font-mono text-xs text-signal">{copy.why.review.label}</p>
                        <p className="mt-1 font-display text-xl text-ink-900">{copy.why.review.concept}</p>
                        <p className="mt-1 text-sm text-ink-700">{copy.why.review.when}</p>
                        <p className="mt-3 font-mono text-xs text-ink-500">{copy.why.review.streak}</p>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="l7-why-progress" aria-hidden="true">
              <span className="l7-why-fill" />
            </div>
          </div>
        </div>
      </section>

      {/* ── 04 · ADHD mode ────────────────────────────────────────────────── */}
      <section className="l7-focus" id="focus">
        <div className="l7-focus-land" aria-hidden="true">
          <Landscape scene="bleach" position="80% 72%" />
        </div>
        <div className="v6-shell l7-focus-grid">
          <div>
            <p className="meta l7-kicker-ink" data-reveal>
              {copy.focus.kicker}
            </p>
            <h2 className="v6-display mt-4 max-w-[10ch]" data-reveal>
              {copy.focus.title}
            </h2>
            <p className="v6-body mt-6 max-w-[30ch] text-ink-700" data-reveal>
              {copy.focus.body}
            </p>
            <p className="mt-4 text-sm text-ink-500" data-reveal>
              {copy.focus.note}
            </p>
          </div>
          <div data-reveal>
            <FocusDemo />
          </div>
        </div>
      </section>

      {/* ── 05 · the territory becomes the map ────────────────────────────── */}
      <section id="map" ref={territory} className="v6-pin v6-map" style={vars({ '--len': '220vh' })}>
        <div className="v6-frame v6-map-frame">
          <div className="v6-map-land scene" aria-hidden="true">
            <div className="v6-push">
              <SceneFilm scene="routes" film={FILMS.routes} position="50% 40%" />
            </div>
          </div>
          <div className="v6-map-title content v6-shell">
            <p className="meta accent-on">{copy.map.kicker}</p>
            <h2 className="v6-display mt-4 max-w-[13ch]">{copy.map.title}</h2>
          </div>
          <div className="v6-map-field field field-cobalt">
            <div className="v6-shell v6-map-grid">
              <div className="v6-map-words">
                <p className="v6-body fg-muted max-w-[32ch]">{copy.map.body}</p>
                <p className="mt-4 text-sm fg-faint">{copy.map.note}</p>
              </div>
              <KnowledgeMap locale={locale} labels={t.landing5.map.states} now={t.landing5.learns.pathNow} className="v6-knowledge" />
            </div>
          </div>
        </div>
      </section>

      {/* ── 06 · the horizon ──────────────────────────────────────────────── */}
      <section ref={horizon} className="v6-pin v6-horizon" style={vars({ '--len': '120vh' })}>
        <div className="v6-frame scene">
          <div className="v6-push">
            <SceneFilm scene="horizon" film={FILMS.horizon} position="70% 70%" />
          </div>
          <div className="v6-veil-ground" aria-hidden="true" />
          <div className="content v6-shell v6-horizon-type">
            <div className="v6-horizon-call">
              <h2 className="v6-mega">{copy.close.line}</h2>
              <div className="v6-hero-foot">
                <p className="v6-lede">{copy.close.body}</p>
                <ButtonLink href={primaryHref} size="lg" onClick={() => start('landing_close')} className="btn-ember">
                  {signedIn ? copy.nav.continueLearning : copy.close.cta}
                </ButtonLink>
              </div>
            </div>
            <footer className="v6-footer">
              <span className="flex items-center gap-4">
                <Wordmark size="sm" className="text-[#f6f2ea]" />
                <span>{footer.license}</span>
              </span>
              <nav className="flex flex-wrap items-center gap-x-5 gap-y-2" aria-label={footer.code}>
                <Link href="/pricing" className="hover:text-[#f6f2ea]">
                  {footer.pricing}
                </Link>
                <a href="https://github.com/aislamsilvalol-ctrl/noema" className="hover:text-[#f6f2ea]">
                  {footer.code}
                </a>
                <Link href="/privacy" className="hover:text-[#f6f2ea]">
                  {footer.privacy}
                </Link>
                <Link href="/terms" className="hover:text-[#f6f2ea]">
                  {footer.terms}
                </Link>
                <LanguageSwitcher className="text-current" />
              </nav>
            </footer>
          </div>
        </div>
      </section>

      {/* The phone's action, in reach of the thumb between hero and close. */}
      <div className={`l7-dock ${pastHero && !atClose ? 'is-shown' : ''}`} aria-hidden={!pastHero || atClose}>
        <ButtonLink
          href={primaryHref}
          size="lg"
          variant="primary"
          onClick={() => start('dock')}
          className="w-full"
          tabIndex={pastHero && !atClose ? 0 : -1}
        >
          {primaryLabel}
        </ButtonLink>
      </div>
    </main>
  );
}
