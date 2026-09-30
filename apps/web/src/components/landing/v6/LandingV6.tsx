'use client';

/**
 * The landing as a film in eight scenes (v6, 2026-09-30).
 *
 * Terraces (the hero, the camera pushes toward Mino) · the manifesto, word by
 * word on bone · Mino, who speaks · how it works, four beats over four
 * frames · the territory that becomes the map · one question to the real
 * tutor · today · the horizon.
 *
 * One mechanic carries it: a pinned scene whose inside follows the scroll.
 * `useSceneProgress` writes `--p` (0→1) on each pinned section and the CSS in
 * styles/landing-v6.css reads it — transform, opacity and clip-path only.
 * One transition repeats between grounds: the next ground rises from the
 * bottom of the frame as a clip (`.v6-curtain`). Everything scroll-linked is
 * scoped under `.v6-motion`, which is set only when the visitor allows
 * motion; without it every scene is a static, complete composition.
 *
 * Honesty rules as before: the field in the tutor scene calls the real tutor
 * and says when it could not; every illustration says so; nothing counts
 * users that do not exist.
 */

import Link from 'next/link';
import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Wordmark } from '@/components/brand/Wordmark';
import { Mino } from '@/components/mino/Mino';
import { Button, ButtonLink } from '@/components/ui/Button';
import { track } from '@/lib/analytics';
import { ApiError, api, demoTeach } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { Markdown } from '@/lib/markdown';
import { rememberPrefill } from '@/lib/prefill';
import { KnowledgeMap } from '../v5/KnowledgeMap';
import { useReveal } from '../v5/LandingV5';
import { Landscape, type Scene } from '../v5/Landscape';
import { SceneFilm, type Film } from '../v5/SceneFilm';
import { bankFor } from '../v5/subjects';
import { prefersReducedMotion, refreshScenes, useSceneProgress } from './useSceneProgress';
import '@/styles/landing.css';
import '@/styles/landing-v6.css';

/** Each film starts and ends on its still, so it loops without a seam;
 * phones get a vertical cut. */
const FILMS: Record<'terraces' | 'valley' | 'mino' | 'bleach' | 'routes' | 'trail' | 'horizon', Film> = {
  terraces: { src: '/brand/film/terraces', mobile: true },
  valley: { src: '/brand/film/valley', mobile: true },
  mino: { src: '/brand/film/mino', mobile: true },
  bleach: { src: '/brand/film/bleach', mobile: true },
  routes: { src: '/brand/film/routes', mobile: true },
  trail: { src: '/brand/film/trail', mobile: true },
  horizon: { src: '/brand/film/horizon', mobile: true },
};

/** The four frames behind "how it works", one per beat, framed on Mino. */
const HOW_FRAMES: [Scene, string][] = [
  ['valley', '76% 70%'],
  ['trail', '61% 62%'],
  ['bleach', '80% 72%'],
  ['horizon', '84% 80%'],
];

type DemoStatus = 'idle' | 'streaming' | 'live' | 'sample';

/** A CSS custom property as an inline style. */
function vars(values: Record<string, string | number>): CSSProperties {
  return values as CSSProperties;
}

export function LandingV6() {
  const { t, locale } = useI18n();
  const copy = t.landing6;
  const mino = t.landing5.mino;
  const learns = t.landing5.learns;
  useReveal();

  const [motion, setMotion] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [rotating, setRotating] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [subject, setSubject] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [status, setStatus] = useState<DemoStatus>('idle');
  const abort = useRef<AbortController | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  const hero = useRef<HTMLElement>(null);
  const manifesto = useRef<HTMLElement>(null);
  const meet = useRef<HTMLElement>(null);
  const how = useRef<HTMLElement>(null);
  const territory = useRef<HTMLElement>(null);
  const horizon = useRef<HTMLElement>(null);
  useSceneProgress(hero);
  useSceneProgress(manifesto);
  useSceneProgress(meet);
  useSceneProgress(how);
  useSceneProgress(territory);
  useSceneProgress(horizon);

  // Pinning is a motion effect: it switches on only when motion is welcome.
  useEffect(() => {
    if (!prefersReducedMotion()) setMotion(true);
  }, []);
  // The pins only get their length once pinning is on: measure again then.
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

  // The subject under the line turns over: the promise is any subject, and
  // the word makes it concrete.
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const timer = window.setInterval(() => setRotating((i) => (i + 1) % t.landing4.hero.subjects.length), 2600);
    return () => window.clearInterval(timer);
  }, [t.landing4.hero.subjects.length]);

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
  const words = copy.statement.line.split(' ');

  return (
    <main className={`landing-light landing-v6 min-h-screen ${motion ? 'v6-motion' : ''}`}>
      <a
        href="#how"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:text-ink-900"
      >
        {copy.nav.how}
      </a>
      <div ref={sentinel} aria-hidden="true" className="absolute top-[70vh] h-px w-px" />

      <header className={`landing-nav fixed inset-x-0 top-0 z-30 ${stuck ? 'is-stuck text-ink-900' : 'text-[#f6f2ea]'}`}>
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-6 py-5 md:px-10">
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
            <ButtonLink href={primaryHref} size="sm" onClick={() => start('header')} className="btn-ember hidden sm:inline-flex">
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

      {/* ── 01 · the terraces: the camera walks toward Mino ─────────────────── */}
      <section ref={hero} className="v6-pin v6-hero" style={vars({ '--len': '180vh' })}>
        <div className="v6-frame scene">
          <div className="v6-push">
            <SceneFilm scene="terraces" film={FILMS.terraces} priority position="72% 62%" />
          </div>
          <div className="v6-veil" aria-hidden="true" />
          <div className="content v6-hero-type">
            <h1 className="v6-mega">
              {copy.hero.line}
              <span className="v6-subject" aria-live="off">
                <span key={rotating} className="inline-block animate-fade-up">
                  {t.landing4.hero.subjects[rotating] ?? ''}
                </span>
              </span>
            </h1>
            <div className="v6-hero-foot">
              <p className="v6-lede">{copy.hero.sub}</p>
              <ButtonLink href={primaryHref} size="lg" onClick={() => start('hero')} className="btn-ember">
                {signedIn ? copy.nav.continueLearning : copy.hero.cta}
              </ButtonLink>
            </div>
          </div>
          <div className="v6-curtain" style={vars({ '--from': 0.6 })} aria-hidden="true" />
        </div>
      </section>

      {/* ── 02 · the manifesto, word by word ───────────────────────────────── */}
      <section ref={manifesto} className="v6-pin v6-manifesto field field-bone" style={vars({ '--len': '200vh' })}>
        <div className="v6-frame v6-shell v6-manifesto-frame">
          <p className="meta fg-faint">{copy.routes.kicker}</p>
          <p className="v6-statement" style={vars({ '--n': words.length })}>
            <span className="sr-only">{copy.statement.line}</span>
            <span aria-hidden="true">
              {words.map((word, index) => (
                <span key={index} className="v6-word" style={vars({ '--i': index })}>
                  {word}{' '}
                </span>
              ))}
            </span>
          </p>
        </div>
      </section>

      {/* ── 03 · Mino, who speaks ──────────────────────────────────────────── */}
      <section ref={meet} className="v6-pin v6-meet" style={vars({ '--len': '220vh' })}>
        <div className="v6-frame scene">
          <div className="v6-push">
            <SceneFilm scene="mino" film={FILMS.mino} position="72% 62%" />
          </div>
          <div className="v6-veil-sky" aria-hidden="true" />
          <div className="content v6-shell v6-meet-type">
            <div>
              <p className="meta accent-on">{mino.kicker}</p>
              <h2 className="v6-display mt-5">{mino.title}</h2>
              <p className="v6-lede mt-5 max-w-[40ch]">{mino.body}</p>
            </div>
            <ol className="v6-says" aria-label={mino.saysLabel}>
              {mino.says.map((line, index) => (
                <li
                  key={index}
                  className="v6-say"
                  style={vars({ '--i': index, '--last': index === mino.says.length - 1 ? 1 : 0 })}
                >
                  <span className="v6-say-mark" aria-hidden="true">
                    —
                  </span>
                  {line}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* ── 04 · how it works, four beats over four frames ─────────────────── */}
      <section
        id="how"
        ref={how}
        className="v6-pin v6-how field field-bone"
        data-steps={4}
        data-step={0}
        style={vars({ '--len': '400vh' })}
      >
        <div className="v6-frame v6-how-frame">
          <div className="v6-stills" aria-hidden="true">
            {HOW_FRAMES.map(([scene, position], index) => (
              <div key={scene} className="v6-still" data-beat={index}>
                <Landscape scene={scene} position={position} />
              </div>
            ))}
          </div>
          <div className="v6-how-copy">
            <div>
              <p className="meta fg-faint">{learns.kicker}</p>
              <h2 className="v6-display-2 mt-4 max-w-[18ch]">{copy.trail.line}</h2>
            </div>
            <ol className="v6-beats">
              {learns.beats.map((beat, index) => (
                <li key={beat.n} className="v6-beat" data-beat={index}>
                  <span className="v6-num" aria-hidden="true">
                    {beat.n}
                  </span>
                  <div className="v6-beat-text">
                    <h3 className="v6-display-3">{beat.title}</h3>
                    <p className="v6-body mt-3 max-w-[38ch]">{beat.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="v6-progress" aria-hidden="true">
              <span className="v6-progress-fill" />
              {learns.beats.map((beat) => (
                <span key={beat.n} className="v6-tick" />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── 05 · the territory becomes the map ─────────────────────────────── */}
      <section id="map" ref={territory} className="v6-pin v6-map" style={vars({ '--len': '250vh' })}>
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
                <p className="v6-body fg-muted max-w-[40ch]">{copy.map.body}</p>
                <p className="mt-4 text-sm fg-faint">{copy.map.note}</p>
              </div>
              <KnowledgeMap
                locale={locale}
                labels={t.landing5.map.states}
                now={t.landing5.learns.pathNow}
                className="v6-knowledge"
              />
            </div>
          </div>
          <div className="v6-curtain" style={vars({ '--from': 0.86 })} aria-hidden="true" />
        </div>
      </section>

      {/* ── 06 · one question, to the real tutor ───────────────────────────── */}
      <section className="field field-bone v6-tutor">
        <div className="v6-shell">
          <div className="v6-tutor-head">
            <div>
              <p className="meta fg-faint" data-reveal>
                {copy.teach.kicker}
              </p>
              <h2 className="v6-display mt-5 max-w-[14ch]" data-reveal>
                {copy.teach.title}
              </h2>
            </div>
            <p className="v6-body fg-muted max-w-[44ch]" data-reveal>
              {copy.teach.body}
            </p>
          </div>

          <form onSubmit={ask} className="v6-ask" data-reveal>
            <label htmlFor="teach-subject" className="meta fg-faint">
              {t.landing5.hero.label}
            </label>
            <div className="v6-ask-line">
              <input
                id="teach-subject"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                placeholder={t.landing5.hero.placeholder}
                autoComplete="off"
                enterKeyHint="go"
                className="v6-ask-input"
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="w-full shrink-0 sm:w-auto"
                disabled={!subject.trim()}
                busy={status === 'streaming' ? t.landing5.hero.thinking : undefined}
              >
                {t.landing5.hero.submit}
              </Button>
            </div>

            {asked ? (
              <div className="v6-answer animate-fade-up" aria-busy={status === 'streaming' || undefined}>
                <div className="v6-answer-who">
                  <Mino state="teaching" size="md" />
                  <Speaker>Mino</Speaker>
                </div>
                <div className="v6-answer-text">
                  {reply ? <Markdown text={reply} className="v6-reading" /> : <p className="text-sm text-ink-600">{t.landing5.hero.thinking}</p>}
                  {status !== 'streaming' && (
                    <p className="mt-6 text-sm text-ink-600" aria-live="polite">
                      {status === 'live' ? t.landing5.hero.liveNote : t.landing5.hero.sampleNote}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <>
                <p className="mt-4 text-sm text-ink-600">{t.landing5.hero.note}</p>
                {/* What a first exchange sounds like, until the visitor asks
                    their own: Mino finds the gap before the subject. */}
                <ol className="v6-exchange" aria-label={copy.teach.kicker}>
                  {copy.teach.exchange.map((line, index) => (
                    <li key={index} className={line.who === 'mino' ? 'is-mino' : 'is-you'}>
                      <Speaker>{line.who === 'mino' ? 'Mino' : copy.teach.you}</Speaker>
                      <p className="v6-exchange-line">{line.text}</p>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </form>
        </div>
      </section>

      {/* ── 07 · today ─────────────────────────────────────────────────────── */}
      <section className="field field-bone v6-today">
        <div className="v6-shell">
          <p className="meta fg-faint" data-reveal>
            {copy.today.kicker}
          </p>
          <h2 className="v6-display mt-5 max-w-[16ch]" data-reveal>
            {copy.today.title}
          </h2>
          <p className="v6-body fg-muted mt-6 max-w-[44ch]" data-reveal>
            {copy.today.body}
          </p>
          <ol className="v6-plan" data-reveal>
            {copy.today.plan.map(([label, minutes], index) => (
              <li key={label}>
                <span className="v6-plan-n">{String(index + 1).padStart(2, '0')}</span>
                <span className="v6-plan-label">{label}</span>
                <span className="v6-plan-min">{minutes}</span>
              </li>
            ))}
          </ol>
          <div className="v6-plan-foot" data-reveal>
            <span className="font-mono">{copy.today.total}</span>
            <span>{copy.today.note}</span>
          </div>
        </div>
      </section>

      {/* ── 08 · the horizon ───────────────────────────────────────────────── */}
      <section ref={horizon} className="v6-pin v6-horizon" style={vars({ '--len': '150vh' })}>
        <div className="v6-frame scene">
          <div className="v6-push">
            <SceneFilm scene="horizon" film={FILMS.horizon} position="70% 70%" />
          </div>
          <div className="v6-veil-ground" aria-hidden="true" />
          <div className="content v6-shell v6-horizon-type">
            <div className="v6-horizon-call">
              <h2 className="v6-mega">{copy.horizon.line}</h2>
              <div className="v6-hero-foot">
                <p className="v6-lede">{copy.horizon.body}</p>
                <ButtonLink href={primaryHref} size="lg" onClick={() => start('landing_close')} className="btn-ember">
                  {signedIn ? copy.nav.continueLearning : copy.horizon.cta}
                </ButtonLink>
              </div>
            </div>
            <footer className="v6-footer">
              <span className="flex items-center gap-4">
                <Wordmark size="sm" className="text-[#f6f2ea]" />
                <span>{copy.footer.license}</span>
              </span>
              <nav className="flex items-center gap-5" aria-label={copy.footer.code}>
                <Link href="/pricing" className="hover:text-[#f6f2ea]">
                  {copy.footer.pricing}
                </Link>
                <a href="https://github.com/aislamsilvalol-ctrl/noema" className="hover:text-[#f6f2ea]">
                  {copy.footer.code}
                </a>
                <Link href="/privacy" className="hover:text-[#f6f2ea]">
                  {copy.footer.privacy}
                </Link>
                <Link href="/terms" className="hover:text-[#f6f2ea]">
                  {copy.footer.terms}
                </Link>
              </nav>
            </footer>
          </div>
        </div>
      </section>
    </main>
  );
}

/** Who is speaking, above a line of dialogue. */
function Speaker({ children }: { children: ReactNode }) {
  return <p className="meta accent-on">{children}</p>;
}
