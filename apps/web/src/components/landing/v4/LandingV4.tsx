'use client';

/**
 * The landing: the story of a lesson, told once, with the character in it.
 *
 * Structure (docs/brand-os.md, docs/product-audit-2026-09.md): the opening
 * line and the live tutor; everyone learns differently; meet Mino; how NOEMA
 * learns you, with real fragments; explain differently; the knowledge map;
 * the modes; mastery, not completion; sources; pricing from the API; the
 * questions; the close. The page changes ground as it scrolls — cream,
 * cobalt, mineral, black — and stays one brand because the type, the
 * character and the rhythm do not change.
 *
 * Honesty rules applied: the hero calls the real tutor (a written sample when
 * it cannot, and says so); every illustrative number is labelled as one;
 * pricing comes from `/billing/plans` or is not shown; nothing counts users
 * that do not exist.
 */

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Wordmark } from '@/components/brand/Wordmark';
import { MINO_RENDERS, MINO_RENDER_SIZE, minoPosterSet, type MinoRenderPose } from '@/brand/mino';
import { MinoLive, MinoProvider, useMino } from '@/components/mino/Mino';
import type { MinoState } from '@/components/mino/machine';
import { Button, ButtonLink } from '@/components/ui/Button';
import { track } from '@/lib/analytics';
import { ApiError, api, demoTeach, type PlanPrice } from '@/lib/api';
import { useI18n, type Locale } from '@/lib/i18n';
import { Markdown } from '@/lib/markdown';
import { rememberPrefill } from '@/lib/prefill';
import { KnowledgeMap, type MapState } from './KnowledgeMap';
import { bankFor, type SubjectBank } from './subjects';
import { useActiveSection } from './useActiveSection';
import '@/styles/landing.css';

const SECTIONS = [
  'ask',
  'different',
  'meet',
  'learn-1',
  'learn-2',
  'learn-3',
  'learn-4',
  'explain',
  'map',
  'modes',
  'mastery',
  'sources',
  'pricing',
  'faq',
  'close',
] as const;
type Section = (typeof SECTIONS)[number];

// What Mino is doing while each part of the page is in view.
const SECTION_STATE: Record<Section, MinoState> = {
  ask: 'idle',
  different: 'curious',
  meet: 'pointing',
  'learn-1': 'listening',
  'learn-2': 'writing',
  'learn-3': 'questioning',
  'learn-4': 'thinking',
  explain: 'teaching',
  map: 'pointing',
  modes: 'focused',
  mastery: 'happy',
  sources: 'reading',
  pricing: 'idle',
  faq: 'curious',
  close: 'wave',
};

const REMEMBERED_DAYS = 9;
const NEXT_REVIEW_DAYS = 11;

type DemoStatus = 'idle' | 'streaming' | 'live' | 'sample';
type ExplainMode = 'plain' | 'simpler' | 'analogy' | 'example' | 'steps';
const EXPLAIN_MODES: ExplainMode[] = ['plain', 'simpler', 'analogy', 'example', 'steps'];

const CURRENCY: Record<Locale, string> = { pt: 'pt-BR', en: 'en-US', es: 'es' };

export function LandingV4() {
  return (
    <MinoProvider>
      <Page />
    </MinoProvider>
  );
}

/**
 * Adds `is-in` once to every `[data-reveal]` that reaches the viewport.
 *
 * Progressive: the hidden state exists only after `html.js-reveal` is set
 * here, so a page without script, or one whose observer never fires, shows
 * everything. Anything already inside the viewport when it is observed is
 * shown at once rather than waiting for a callback. Re-run when `deps`
 * change, because blocks rendered later (pricing, after the plans arrive)
 * must be observed too.
 */
function useReveal(deps: unknown[]) {
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const reduced =
      typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps is the caller's list
  }, deps);
}

function Page() {
  const { t, locale } = useI18n();
  const copy = t.landing5;
  const mino = useMino();
  const { active, register } = useActiveSection(SECTIONS);

  const [signedIn, setSignedIn] = useState(false);
  const [subject, setSubject] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [status, setStatus] = useState<DemoStatus>('idle');
  const [answer, setAnswer] = useState<number | null>(null);
  const [sure, setSure] = useState<boolean | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [explainMode, setExplainMode] = useState<ExplainMode>('plain');
  const [demoMode, setDemoMode] = useState<'normal' | 'focus'>('normal');
  const [plans, setPlans] = useState<PlanPrice[] | null>(null);
  useReveal([plans]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  const bank: SubjectBank = bankFor(asked ?? 'Freud', locale);
  const freud: SubjectBank = bankFor('Freud', locale);
  const answered = answer !== null && sure !== null;
  const correct = answer === bank.correct;
  const lessonText = reply || bank.sample;

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(() => {
        if (!cancelled) setSignedIn(true);
      })
      .catch(() => undefined);
    api
      .plans()
      .then((list) => {
        if (!cancelled) setPlans(list);
      })
      .catch(() => {
        if (!cancelled) setPlans([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The header gains its ground once the top of the page has scrolled away.
  useEffect(() => {
    const node = sentinel.current;
    if (!node || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([entry]) => {
      if (!entry) return;
      setStuck(!entry.isIntersecting);
      if (!entry.isIntersecting) setScrolled(true);
    });
    io.observe(node);
    return () => io.disconnect();
  }, []);

  // Scroll moves the character between parts — unless it is busy with the
  // demo, or the visitor is in the field, which directs it itself.
  useEffect(() => {
    if (status === 'streaming') return;
    if (active === 'learn-3' && answered) return;
    if (active === 'ask' && document.activeElement === input.current) return;
    mino.setState(SECTION_STATE[active as Section] ?? 'idle');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `mino` is stable; status/answered gate only
  }, [active]);

  function onType(value: string) {
    setSubject(value);
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    if (!value.trim()) {
      mino.on('input_focus');
      return;
    }
    mino.on('input_typing');
    mino.focus(input.current);
    pauseTimer.current = setTimeout(() => mino.on('input_pause'), 800);
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const trimmed = subject.trim();
    if (!trimmed || status === 'streaming') return;
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    track('cta_clicked', { location: 'hero_ask' });

    setAsked(trimmed);
    setReply('');
    setAnswer(null);
    setSure(null);
    setFlipped(false);
    setStatus('streaming');
    mino.on('request_started');

    abort.current?.abort();
    abort.current = new AbortController();
    let sawToken = false;
    let failed = false;
    try {
      await demoTeach(
        trimmed,
        {
          onToken: (text) => {
            if (!sawToken) {
              sawToken = true;
              mino.on('response_streaming');
            }
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
    mino.on('response_done');
    mino.setState('teaching');
  }

  function changeSubject() {
    abort.current?.abort();
    setAsked(null);
    setReply('');
    setStatus('idle');
    setSubject('');
    mino.reset();
    input.current?.focus();
  }

  function pick(index: number) {
    if (answered) return;
    setAnswer(index);
    mino.on('input_pause');
  }

  function confirm(wasSure: boolean) {
    if (answer === null) return;
    setSure(wasSure);
    mino.react(answer === bank.correct ? 'correct' : 'wrong');
  }

  function start(location: string) {
    if (asked) rememberPrefill(asked);
    track('cta_clicked', { location });
  }

  const primaryHref = signedIn ? '/today' : '/login?mode=register';
  const primaryLabel = signedIn ? copy.nav.continueLearning : copy.nav.start;
  const money = new Intl.NumberFormat(CURRENCY[locale], { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  const navLinks: [string, string][] = [
    ['#product', copy.nav.product],
    ['#how', copy.nav.how],
    ['#modes', copy.nav.modes],
    ['#pricing', copy.nav.pricing],
  ];
  const explainText =
    explainMode === 'plain' ? freud.sample : copy.explain.variants[explainMode];
  const beatAt = (i: number) => copy.learns.beats[i] ?? { n: String(i + 1), title: '', body: '' };

  return (
    <main className="atmo atmo-cream min-h-screen">
      <a
        href="#ask"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:text-ink-900"
      >
        {copy.hero.label}
      </a>
      <div ref={sentinel} aria-hidden="true" className="h-px" />

      {/* ── navigation ─────────────────────────────────────────────────── */}
      <header className={`landing-nav sticky top-0 z-30 ${stuck ? 'is-stuck' : ''}`}>
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <Wordmark size="md" className="text-ink-900" />
          <nav aria-label={copy.nav.menu} className="hidden items-center gap-6 text-sm text-ink-600 md:flex">
            {navLinks.map(([href, label]) => (
              <a key={href} href={href} className="transition-colors duration-fast hover:text-ink-900">
                {label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <LanguageSwitcher className="hidden sm:block" />
            {!signedIn && (
              <Link
                href="/login"
                onClick={() => track('cta_clicked', { location: 'header_signin' })}
                className="hidden text-sm text-ink-600 transition-colors duration-fast hover:text-ink-900 sm:block"
              >
                {copy.nav.signIn}
              </Link>
            )}
            <ButtonLink
              href={primaryHref}
              variant="primary"
              size="sm"
              onClick={() => start('header')}
              className="hidden sm:inline-flex"
            >
              {primaryLabel}
            </ButtonLink>
            <button
              type="button"
              aria-expanded={menuOpen}
              aria-controls="landing-menu"
              onClick={() => setMenuOpen((open) => !open)}
              className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-800 md:hidden"
            >
              {copy.nav.menu}
            </button>
          </div>
        </div>
        {menuOpen && (
          <div id="landing-menu" className="border-t border-line bg-surface px-6 py-4 md:hidden">
            <nav aria-label={copy.nav.menu} className="flex flex-col gap-3 text-base text-ink-800">
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

      {/* ── the opening ─────────────────────────────────────────────────── */}
      <section
        id="ask"
        ref={register('ask')}
        className="mx-auto grid max-w-6xl gap-8 px-6 pb-24 pt-6 md:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] md:items-center md:pb-32 md:pt-16"
      >
        <div className="min-w-0">
          <h1 className="display-1 text-ink-900">
            {copy.hero.title}
            <span className="mt-3 block text-accent" style={{ fontSize: '0.5em', lineHeight: 1.1, letterSpacing: '-0.02em' }}>
              {copy.hero.line}
            </span>
          </h1>
          <p className="mt-8 max-w-reading text-md text-ink-600">{copy.hero.lead}</p>

          <form onSubmit={ask} className="mt-10">
            <label htmlFor="ask-subject" className="block font-display text-xl text-ink-900">
              {copy.hero.label}
            </label>
            <div className="mt-4 flex max-w-xl gap-2">
              <input
                id="ask-subject"
                ref={input}
                value={subject}
                onChange={(event) => onType(event.target.value)}
                onFocus={() => {
                  mino.on('input_focus');
                  mino.focus(input.current);
                }}
                onBlur={() => !subject && mino.on('input_blur')}
                placeholder={copy.hero.placeholder}
                autoComplete="off"
                enterKeyHint="go"
                className="min-w-0 flex-1 border-b-2 border-line bg-transparent px-0 py-3 text-lg text-ink-900 outline-none transition-colors duration-fast placeholder:text-ink-400 focus:border-signal"
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={!subject.trim()}
                busy={status === 'streaming' ? copy.hero.thinking : undefined}
              >
                {copy.hero.submit}
              </Button>
            </div>
            {!asked && <p className="mt-3 text-sm text-ink-600">{copy.hero.note}</p>}
          </form>

          {asked && (
            <div className="mt-8 max-w-xl animate-fade-up">
              <Speaker>Mino</Speaker>
              <div className="mt-2 min-h-[4rem]" aria-busy={status === 'streaming' || undefined}>
                {reply ? (
                  <Markdown text={reply} className="text-md" />
                ) : (
                  <p className="text-sm text-ink-600">{copy.hero.thinking}</p>
                )}
                {status === 'streaming' && reply && (
                  <span aria-hidden="true" className="ml-0.5 inline-block h-4 w-px animate-pulse bg-signal align-middle" />
                )}
              </div>
              {status !== 'streaming' && (
                <div className="mt-4 flex flex-wrap items-center gap-4" aria-live="polite">
                  <p className="text-sm text-ink-600">{status === 'live' ? copy.hero.liveNote : copy.hero.sampleNote}</p>
                  <button
                    type="button"
                    onClick={changeSubject}
                    className="text-sm text-ink-600 underline-offset-2 transition-colors duration-fast hover:text-ink-900 hover:underline"
                  >
                    {copy.hero.change}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* On a phone the figure is small and first, at the right, so it shares
            the first screen with the opening line. From md up it takes the
            right column, lit like an object on the page. */}
        <div className="order-first -mb-2 ml-auto w-36 md:order-none md:mx-auto md:mb-0 md:w-full md:max-w-sm">
          <MinoLive size="xl" primary priority className="w-full" />
        </div>
      </section>

      {/* ── everyone learns differently ──────────────────────────────────── */}
      <section id="product" ref={register('different')} className="atmo atmo-cobalt grain">
        <div className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <Kicker>{copy.different.kicker}</Kicker>
          <h2 className="display-2 mt-4 max-w-4xl" data-reveal>
            {copy.different.title}
          </h2>
          <p className="fg-muted mt-6 max-w-reading text-md" data-reveal>
            {copy.different.body}
          </p>
          <p className="mt-10 font-mono text-xs fg-faint">{copy.different.subject(asked ?? bank.label)}</p>
          <div className="mt-4 grid gap-10 md:grid-cols-2 md:gap-16">
            {[copy.different.a, copy.different.b].map((person, index) => (
              <div key={person.name} className="rule border-t pt-6" data-reveal>
                <p className="font-display text-2xl">{person.name}</p>
                <p className="fg-muted mt-2 font-serif text-md italic">{person.said}</p>
                <ol className="mt-6">
                  {person.route.map((step, i) => (
                    <li key={step} className="rule flex items-baseline gap-4 border-t py-3">
                      <span className="w-6 shrink-0 font-mono text-xs fg-faint">{String(i + 1).padStart(2, '0')}</span>
                      <span className={`text-base ${i === 0 ? 'accent-on' : ''}`}>{step}</span>
                    </li>
                  ))}
                </ol>
                {index === 1 && <p className="fg-faint mt-4 text-xs">{copy.different.note}</p>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── meet Mino ───────────────────────────────────────────────────── */}
      <section ref={register('meet')} className="atmo atmo-cream">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:items-center md:py-28">
          <div className="mx-auto w-full max-w-[16rem] md:max-w-sm" data-reveal>
            <Poster pose="wave" sizes="(min-width: 768px) 384px, 256px" />
          </div>
          <div>
            <Kicker>{copy.mino.kicker}</Kicker>
            <h2 className="display-2 mt-4 text-ink-900" data-reveal>
              {copy.mino.title}
            </h2>
            <p className="mt-6 max-w-reading text-md text-ink-600" data-reveal>
              {copy.mino.body}
            </p>
            <p className="mt-10 font-mono text-xs text-ink-500">{copy.mino.saysLabel}</p>
            <ul className="mt-2 max-w-reading">
              {copy.mino.says.map((line) => (
                <li key={line} className="border-t border-line py-3 font-serif text-md text-ink-900" data-reveal>
                  {line}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ── how NOEMA learns you ────────────────────────────────────────── */}
      <section id="how" className="atmo atmo-mineral grain">
        <div className="mx-auto max-w-6xl px-6 pt-20 md:pt-28">
          <Kicker>{copy.learns.kicker}</Kicker>
          <h2 className="display-2 mt-4 max-w-4xl" data-reveal>
            {copy.learns.title}
          </h2>
        </div>
        <div className="mx-auto max-w-6xl px-6 pb-20 pt-10 md:pb-28 md:pt-16">
          <Beat id="learn-1" register={register} beat={beatAt(0)} active={active}>
            <Dialogue
              you={copy.learns.you}
              lines={[
                { who: copy.learns.you, text: asked ? copy.learns.askExample.replace(/Freud/i, asked) : copy.learns.askExample },
                { who: 'Mino', text: copy.learns.probeReply },
                { who: 'Mino', text: copy.learns.probeQuestion },
                { who: copy.learns.you, text: copy.learns.probeAnswer },
                { who: 'Mino', text: copy.learns.probeVerdict },
              ]}
            />
          </Beat>

          <Beat id="learn-2" register={register} beat={beatAt(1)} active={active}>
            <ol className="max-w-md">
              {bank.path.map((module, index) => (
                <li key={module} className={`rule flex items-baseline gap-4 border-t py-3 ${index === 0 ? '' : 'fg-muted'}`}>
                  <span className="w-6 shrink-0 font-mono text-xs fg-faint">{String(index + 1).padStart(2, '0')}</span>
                  <span className="flex-1 text-base">{module}</span>
                  <span className={`font-mono text-xs ${index === 0 ? 'accent-on' : 'fg-faint'}`}>
                    {index === 0 ? copy.learns.pathNow : copy.learns.pathLater}
                  </span>
                </li>
              ))}
            </ol>
          </Beat>

          <Beat id="learn-3" register={register} beat={beatAt(2)} active={active}>
            <div className="max-w-md">
              <p className="font-display text-lg">{bank.question}</p>
              <ul className="mt-4" role="group" aria-label={bank.question}>
                {bank.options.map((option, index) => {
                  const chosen = answer === index;
                  const tone = answered
                    ? index === bank.correct
                      ? 'accent-on'
                      : chosen
                        ? 'line-through fg-faint'
                        : 'fg-faint'
                    : chosen
                      ? 'accent-on'
                      : '';
                  return (
                    <li key={option} className="rule border-t">
                      <button
                        type="button"
                        onClick={() => pick(index)}
                        aria-pressed={chosen}
                        disabled={answered}
                        className={`flex w-full items-baseline gap-4 py-3 text-left text-base transition-colors duration-fast disabled:cursor-default ${tone}`}
                      >
                        <span
                          aria-hidden="true"
                          className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full border border-current ${chosen ? 'bg-current' : ''}`}
                        />
                        {option}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {answer !== null && !answered && (
                <div className="rule mt-4 flex flex-wrap items-center gap-3 border-t pt-4">
                  <span className="fg-muted text-sm">{copy.learns.confident}</span>
                  <FieldButton onClick={() => confirm(true)}>{copy.learns.sure}</FieldButton>
                  <FieldButton onClick={() => confirm(false)}>{copy.learns.unsure}</FieldButton>
                </div>
              )}
              {answered && (
                <p className="rule mt-4 border-t pt-4 text-sm font-medium" role="status">
                  {correct ? copy.learns.right : copy.learns.wrong}
                </p>
              )}
              {answered && !correct && <p className="fg-muted mt-2 text-sm">{bank.correction}</p>}
            </div>
          </Beat>

          <Beat id="learn-4" register={register} beat={beatAt(3)} active={active}>
            {(() => {
              const moved = answered && !correct;
              const rows = [...bank.concepts]
                .map((c) => ({ name: c.name, value: moved ? c.after : c.before }))
                .sort((a, z) => a.value - z.value);
              return (
                <div className="max-w-md">
                  <p className="font-mono text-xs fg-faint">
                    {copy.learns.masteryTitle}
                    {moved && <span className="accent-on"> · {copy.learns.masteryMoved}</span>}
                  </p>
                  <ul className="mt-3">
                    {rows.map((row) => (
                      <li key={row.name} className="rule border-t py-3">
                        <div className="flex items-baseline justify-between gap-4 text-sm">
                          <span>{row.name}</span>
                          <span className="font-mono fg-muted">{row.value}</span>
                        </div>
                        <div className="rule mt-2 h-0.5 w-full bg-[color:var(--rule)]">
                          <div
                            className="h-0.5 bg-current transition-[width] duration-slow ease-noema"
                            style={{ width: `${row.value}%`, opacity: row.value < 40 ? 0.55 : 1 }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p className="fg-faint mt-3 text-xs">{copy.learns.masteryHint}</p>
                </div>
              );
            })()}
          </Beat>
        </div>
      </section>

      {/* ── explain differently ─────────────────────────────────────────── */}
      <section ref={register('explain')} className="atmo atmo-cream">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:py-28">
          <div className="max-w-reading">
            <Kicker>{copy.explain.kicker}</Kicker>
            <h2 className="display-2 mt-4 text-ink-900" data-reveal>
              {copy.explain.title}
            </h2>
            <p className="mt-6 text-md text-ink-600" data-reveal>
              {copy.explain.body}
            </p>
          </div>
          <div className="max-w-xl md:justify-self-end" data-reveal>
            <p className="font-mono text-xs text-ink-500">{copy.explain.example}</p>
            <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={copy.explain.kicker}>
              {EXPLAIN_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={explainMode === mode}
                  onClick={() => {
                    setExplainMode(mode);
                    mino.setState('teaching');
                  }}
                  className={`rounded-md border px-3 py-1.5 text-sm transition-colors duration-fast ${
                    explainMode === mode
                      ? 'border-ink-900 bg-ink-900 text-ink-50'
                      : 'border-line text-ink-800 hover:border-ink-400'
                  }`}
                >
                  {copy.explain.modes[mode]}
                </button>
              ))}
            </div>
            <div className="mt-6 border-t border-line pt-6">
              <Speaker>Mino</Speaker>
              <Markdown key={explainMode} text={explainText} className="mt-2 animate-fade-up font-serif text-md" />
            </div>
          </div>
        </div>
      </section>

      {/* ── the knowledge map ───────────────────────────────────────────── */}
      <section ref={register('map')} className="atmo atmo-black grain">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:items-center md:py-28">
          <div className="max-w-reading">
            <Kicker>{copy.map.kicker}</Kicker>
            <h2 className="display-2 mt-4" data-reveal>
              {copy.map.title}
            </h2>
            <p className="fg-muted mt-6 text-md" data-reveal>
              {copy.map.body}
            </p>
            <p className="fg-faint mt-6 text-xs">{copy.map.note}</p>
          </div>
          <div data-reveal>
            <KnowledgeMap locale={locale} labels={copy.map.states} now={copy.learns.pathNow} />
          </div>
        </div>
      </section>

      {/* ── modes ───────────────────────────────────────────────────────── */}
      <section id="modes" ref={register('modes')} className="atmo atmo-cream">
        <div className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <Kicker>{copy.modes.kicker}</Kicker>
          <h2 className="display-2 mt-4 max-w-3xl text-ink-900" data-reveal>
            {copy.modes.title}
          </h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3 md:gap-12">
            {[copy.modes.focus, copy.modes.socratic, copy.modes.normal].map((mode) => (
              <div key={mode.name} className="border-t border-line pt-5" data-reveal>
                <h3 className="font-display text-2xl text-ink-900">{mode.name}</h3>
                <p className="mt-3 text-base text-ink-600">{mode.body}</p>
              </div>
            ))}
          </div>

          {/* The same lesson, in two rhythms: what Focus changes is the delivery. */}
          <div className="mt-16 max-w-xl" data-landing-mode={demoMode} data-reveal>
            <div className="flex gap-6 border-b border-line" role="group" aria-label={copy.modes.title}>
              {(['normal', 'focus'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={demoMode === m}
                  onClick={() => setDemoMode(m)}
                  className={`-mb-px border-b-2 py-2 text-sm transition-colors duration-fast ${
                    demoMode === m ? 'border-signal text-ink-900' : 'border-transparent text-ink-600 hover:text-ink-900'
                  }`}
                >
                  {m === 'normal' ? copy.modes.demoNormal : copy.modes.demoFocus}
                </button>
              ))}
            </div>
            {demoMode === 'normal' ? (
              <div className="mt-6">
                <Speaker>Mino</Speaker>
                <Markdown text={lessonText} className="mt-2 font-serif text-md" />
              </div>
            ) : (
              <FocusRhythm
                text={lessonText}
                question={bank.question}
                options={bank.options}
                card={bank.card.front}
                labels={copy.modes}
              />
            )}
          </div>
        </div>
      </section>

      {/* ── mastery, not completion ─────────────────────────────────────── */}
      <section ref={register('mastery')} className="atmo atmo-cream border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:py-28">
          <div className="max-w-reading">
            <Kicker>{copy.mastery.kicker}</Kicker>
            <h2 className="display-2 mt-4 text-ink-900" data-reveal>
              {copy.mastery.title}
            </h2>
            <p className="mt-6 text-md text-ink-600" data-reveal>
              {copy.mastery.body}
            </p>
          </div>
          <div className="grid gap-12 md:justify-self-end md:grid-cols-2 md:gap-10">
            <div className="max-w-xs" data-reveal>
              <p className="font-mono text-xs text-ink-500">{copy.mastery.example}</p>
              <ul className="mt-3">
                {copy.mastery.rows.map(([name, state]) => (
                  <li key={name} className="flex items-center justify-between gap-4 border-t border-line py-3 text-sm">
                    <span className="text-ink-900">{name}</span>
                    <span className="inline-flex items-center gap-2 font-mono text-xs text-ink-600">
                      <StateDot state={state} />
                      {copy.map.states[state]}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="max-w-xs" data-reveal>
              <Speaker>Mino</Speaker>
              <p className="mt-2 font-serif text-md text-ink-900">{copy.mastery.returnWhen(REMEMBERED_DAYS)}</p>
              <button
                type="button"
                onClick={() => setFlipped((f) => !f)}
                className="mt-5 w-full rounded-lg text-left [perspective:1400px] focus-visible:ring-2 focus-visible:ring-signal focus-visible:ring-offset-2"
                aria-pressed={flipped}
              >
                <div
                  className={`grid transition-transform duration-slow ease-noema [transform-style:preserve-3d] ${
                    flipped ? '[transform:rotateY(180deg)]' : ''
                  }`}
                >
                  <div className="col-start-1 row-start-1 rounded-lg border border-line bg-raised p-6 [backface-visibility:hidden] [-webkit-backface-visibility:hidden]">
                    <p className="font-serif text-lg text-ink-900">{bank.card.front}</p>
                    <p className="mt-6 text-xs text-ink-500">{copy.mastery.returnTap}</p>
                  </div>
                  <div className="col-start-1 row-start-1 rounded-lg border border-signal bg-raised p-6 [backface-visibility:hidden] [-webkit-backface-visibility:hidden] [transform:rotateY(180deg)]">
                    <p className="text-sm text-ink-500">{bank.card.front}</p>
                    <p className="mt-3 font-serif text-lg text-ink-900">{bank.card.back}</p>
                    <p className="mt-5 text-xs text-ink-500">{copy.mastery.returnNext(NEXT_REVIEW_DAYS)}</p>
                  </div>
                </div>
              </button>
              <p className="mt-3 text-xs text-ink-500">{copy.mastery.note}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── sources ─────────────────────────────────────────────────────── */}
      <section ref={register('sources')} className="atmo atmo-mineral grain">
        <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
          <Kicker>{copy.sources.kicker}</Kicker>
          <h2 className="display-3 mt-4 max-w-3xl" data-reveal>
            {copy.sources.title}
          </h2>
          <p className="fg-muted mt-5 max-w-reading text-md" data-reveal>
            {copy.sources.body}
          </p>
        </div>
      </section>

      {/* ── pricing ─────────────────────────────────────────────────────── */}
      {plans && plans.length > 0 && (
        <section id="pricing" ref={register('pricing')} className="atmo atmo-cream">
          <div className="mx-auto max-w-6xl px-6 py-20 md:py-28">
            <Kicker>{copy.pricing.kicker}</Kicker>
            <h2 className="display-2 mt-4 max-w-3xl text-ink-900" data-reveal>
              {copy.pricing.title}
            </h2>
            <dl className="mt-12 grid gap-8 md:grid-cols-4 md:gap-6">
              {plans.map((plan) => (
                <div key={plan.plan} className="border-t border-line pt-5" data-reveal>
                  <dt className="font-display text-2xl text-ink-900">{copy.pricing.names[plan.plan] ?? plan.plan}</dt>
                  <dd className="mt-2">
                    <span className="font-display text-3xl text-ink-900">
                      {plan.monthly_price_cents === 0 ? copy.pricing.free : money.format(plan.monthly_price_cents / 100)}
                    </span>
                    {plan.monthly_price_cents > 0 && <span className="text-sm text-ink-500">{copy.pricing.perMonth}</span>}
                  </dd>
                  <dd className="mt-3 text-sm text-ink-600">{copy.pricing.units(plan.monthly_ai_units)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-6 text-xs text-ink-500">{copy.pricing.unitsHint}</p>
            <ButtonLink href={primaryHref} variant="primary" className="mt-8" onClick={() => start('pricing')}>
              {copy.pricing.cta}
            </ButtonLink>
          </div>
        </section>
      )}

      {/* ── questions ───────────────────────────────────────────────────── */}
      <section ref={register('faq')} className="atmo atmo-cream border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:py-28">
          <Kicker>{copy.faq.kicker}</Kicker>
          <dl className="max-w-3xl">
            {copy.faq.items.map(([q, a]) => (
              <details key={q} className="group border-t border-line py-4" data-reveal>
                <summary className="flex cursor-pointer list-none items-baseline justify-between gap-6 font-display text-xl text-ink-900 [&::-webkit-details-marker]:hidden">
                  <span>{q}</span>
                  <span aria-hidden="true" className="font-mono text-sm text-ink-400 transition-transform duration-fast group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 max-w-reading text-base text-ink-600">{a}</p>
              </details>
            ))}
          </dl>
        </div>
      </section>

      {/* ── close ───────────────────────────────────────────────────────── */}
      <section ref={register('close')} className="atmo atmo-black grain">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-24 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:items-center md:py-32">
          <div className="mx-auto w-full max-w-[14rem] md:max-w-xs">
            <MinoLive size="xl" className="w-full" />
          </div>
          <div>
            <h2 className="display-1">{copy.close.title}</h2>
            <p className="fg-muted mt-6 max-w-reading text-md">{copy.close.body}</p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <ButtonLink href={primaryHref} variant="primary" size="lg" onClick={() => start('landing_close')}>
                {signedIn ? copy.nav.continueLearning : copy.close.start}
              </ButtonLink>
              {asked && <span className="fg-muted text-sm">{asked}</span>}
            </div>
          </div>
        </div>
        <footer className="rule border-t">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm fg-muted">
            <span>{copy.footer.license}</span>
            <nav className="flex items-center gap-5" aria-label={copy.footer.code}>
              <a href="https://github.com/aislamsilvalol-ctrl/noema" className="transition-colors duration-fast hover:text-[color:var(--fg)]">
                {copy.footer.code}
              </a>
              <Link href="/privacy" className="transition-colors duration-fast hover:text-[color:var(--fg)]">
                {copy.footer.privacy}
              </Link>
              <Link href="/terms" className="transition-colors duration-fast hover:text-[color:var(--fg)]">
                {copy.footer.terms}
              </Link>
            </nav>
          </div>
        </footer>
      </section>

      {/* The companion: the same character, small, once the hero has scrolled
          away and until the close brings the large figure back. Mounted only
          then, so it costs nothing on the first screen. */}
      {scrolled && active !== 'ask' && active !== 'close' && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed bottom-5 right-5 z-20 h-20 w-20 animate-fade-up md:h-24 md:w-24"
        >
          <MinoLive size="fill" />
        </div>
      )}
    </main>
  );
}

/** A small serif line above a title: the page's only label style. */
function Kicker({ children }: { children: ReactNode }) {
  return <p className="accent-on font-display text-lg italic">{children}</p>;
}

/** Who is speaking, above a line of dialogue. */
function Speaker({ children }: { children: ReactNode }) {
  return <p className="font-mono text-xs accent-on">{children}</p>;
}

/** A neutral action that inherits the field's foreground. */
function FieldButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rule rounded-md border px-3 py-1.5 text-sm transition-colors duration-fast hover:border-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current"
    >
      {children}
    </button>
  );
}

/** The rendered still, compressed and sized — for the places that do not need the live stage. */
function Poster({ pose, sizes }: { pose: MinoRenderPose; sizes: string }) {
  return (
    <picture>
      <source type="image/avif" srcSet={minoPosterSet(pose, 'avif')} sizes={sizes} />
      <source type="image/webp" srcSet={minoPosterSet(pose, 'webp')} sizes={sizes} />
      {/* eslint-disable-next-line @next/next/no-img-element -- art-directed sources */}
      <img
        src={MINO_RENDERS[pose]}
        alt=""
        width={MINO_RENDER_SIZE.width}
        height={MINO_RENDER_SIZE.height}
        loading="lazy"
        decoding="async"
        draggable={false}
        className="mino-float block h-auto w-full select-none"
      />
    </picture>
  );
}

function StateDot({ state }: { state: MapState }) {
  const base = 'inline-block h-2.5 w-2.5 rounded-full';
  switch (state) {
    case 'mastered':
      return <span className={`${base} bg-ink-900`} />;
    case 'understood':
      return <span className={`${base} bg-ink-700`} />;
    case 'learning':
      return <span className={`${base} border border-ink-700 bg-[repeating-linear-gradient(45deg,transparent_0_1.5px,currentColor_1.5px_2.5px)] text-ink-700`} />;
    case 'review':
      return <span className={`${base} bg-ink-700 ring-1 ring-ink-400 ring-offset-2 ring-offset-surface`} />;
    default:
      return <span className={`${base} border border-dashed border-ink-400`} />;
  }
}

function Dialogue({ lines, you }: { lines: { who: string; text: string }[]; you: string }) {
  return (
    <ol className="max-w-md">
      {lines.map((line, index) => (
        <li key={`${index}-${line.text}`} className="rule border-t py-3">
          <Speaker>{line.who}</Speaker>
          <p className={`mt-1 text-md ${line.who === you ? 'fg-muted font-serif italic' : ''}`}>{line.text}</p>
        </li>
      ))}
    </ol>
  );
}

function FocusRhythm({
  text,
  question,
  options,
  card,
  labels,
}: {
  text: string;
  question: string;
  options: string[];
  card: string;
  labels: { hook: string; concept: string; interaction: string; recall: string };
}) {
  const sentences = text
    .replace(/\*\*/g, '')
    .split(/(?<=[.!?])\s+/)
    .filter(Boolean);
  const hook = sentences[0] ?? '';
  const concept = sentences.slice(1, 4);
  return (
    <ol className="mt-6 space-y-5">
      <li>
        <p className="font-mono text-xs text-accent">{labels.hook}</p>
        <p className="mt-1 font-display text-lg text-ink-900">{hook}</p>
      </li>
      <li>
        <p className="font-mono text-xs text-accent">{labels.concept}</p>
        <ul className="mt-1 space-y-1.5">
          {concept.map((line) => (
            <li key={line} className="text-sm text-ink-800">
              {line}
            </li>
          ))}
        </ul>
      </li>
      <li>
        <p className="font-mono text-xs text-accent">{labels.interaction}</p>
        <p className="mt-1 text-sm text-ink-900">{question}</p>
        <ul className="mt-2 space-y-1">
          {options.map((o) => (
            <li key={o} className="text-sm text-ink-600">
              — {o}
            </li>
          ))}
        </ul>
      </li>
      <li>
        <p className="font-mono text-xs text-accent">{labels.recall}</p>
        <p className="mt-1 font-serif text-sm text-ink-900">{card}</p>
      </li>
    </ol>
  );
}

function Beat({
  id,
  register,
  beat,
  active,
  children,
}: {
  id: Section;
  register: (id: string) => (element: Element | null) => void;
  beat: { n: string; title: string; body: string };
  active: string;
  children: ReactNode;
}) {
  const here = active === id;
  return (
    <section
      ref={register(id)}
      data-here={here || undefined}
      className="rule grid gap-6 border-t py-12 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-12 md:py-16"
    >
      <div className="max-w-reading">
        <span
          aria-hidden="true"
          className={`font-display text-3xl transition-colors duration-slow ease-noema ${here ? 'accent-on' : 'fg-faint'}`}
        >
          {beat.n}
        </span>
        <h3 className="mt-2 font-display text-2xl">{beat.title}</h3>
        <p className="fg-muted mt-3 text-md">{beat.body}</p>
      </div>
      <div className="md:pt-3">{children}</div>
    </section>
  );
}
