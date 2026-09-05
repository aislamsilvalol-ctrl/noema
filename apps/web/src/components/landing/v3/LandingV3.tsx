'use client';

/**
 * The landing page as meeting the tutor.
 *
 * One narrative in five beats — ASK, LEARN, PRACTICE, ADAPT, REMEMBER — and
 * a close that asks the question again. The visitor types a subject; the
 * real tutor answers (POST /ai/demo, restricted; a written sample when it
 * cannot); the beats after that adapt locally to the subject. Mino is one
 * character across the page: the hero figure and the companion that follows
 * the scroll share a controller, so product events move both.
 *
 * Nothing here fakes a delay, a brain or a dashboard. The visuals are the
 * product's own pieces: a lesson block, a question with confidence, mastery
 * bars that reorder, a card that turns.
 */

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { Wordmark } from '@/components/brand/Wordmark';
import { MinoLive, MinoProvider, useMino } from '@/components/mino/Mino';
import { Button, ButtonLink } from '@/components/ui/Button';
import { track } from '@/lib/analytics';
import { ApiError, api, demoTeach } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { Markdown } from '@/lib/markdown';
import { rememberPrefill } from '@/lib/prefill';
import { bankFor, type SubjectBank } from './subjects';
import { useActiveSection } from './useActiveSection';

const SECTIONS = ['ask', 'path', 'learn', 'practice', 'adapt', 'remember', 'close'] as const;
type Section = (typeof SECTIONS)[number];

// Where the character is, per beat, when nothing else is directing it.
const SECTION_STATE = {
  ask: 'idle',
  path: 'writing',
  learn: 'teaching',
  practice: 'curious',
  adapt: 'thinking',
  remember: 'reading',
  close: 'wave',
} as const;

type DemoStatus = 'idle' | 'streaming' | 'live' | 'sample';

export function LandingV3() {
  return (
    <MinoProvider>
      <Page />
    </MinoProvider>
  );
}

function Page() {
  const { t, locale } = useI18n();
  const copy = t.landing3;
  const mino = useMino();
  const { active, register } = useActiveSection(SECTIONS);

  const [signedIn, setSignedIn] = useState(false);
  const [subject, setSubject] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [status, setStatus] = useState<DemoStatus>('idle');
  const [example, setExample] = useState(0);
  const [answer, setAnswer] = useState<number | null>(null);
  const [sure, setSure] = useState<boolean | null>(null);
  const [flipped, setFlipped] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const bank: SubjectBank | null = asked ? bankFor(asked, locale) : null;
  const answered = answer !== null && sure !== null;
  const correct = bank !== null && answer === bank.correct;

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

  // The examples rotate in the placeholder until the visitor types.
  useEffect(() => {
    if (subject || asked) return;
    if (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = window.setInterval(() => setExample((i) => (i + 1) % copy.examples.length), 2800);
    return () => window.clearInterval(timer);
  }, [subject, asked, copy.examples.length]);

  // Scroll moves the character between beats — unless it is busy with the
  // demo (thinking/teaching follow the request, not the scroll position).
  useEffect(() => {
    if (status === 'streaming') return;
    if (active === 'practice' && answered) return;
    // While the visitor is in the field, the field directs the character.
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
      // 429 (allowance spent), 503 (no provider), network: the sample stands in.
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
    if (answer === null || !bank) return;
    setSure(wasSure);
    mino.react(answer === bank.correct ? 'correct' : 'wrong');
  }

  function start() {
    if (asked) rememberPrefill(asked);
    track('cta_clicked', { location: 'landing_close' });
  }

  const primaryHref = signedIn ? '/chat' : asked ? '/login' : '/login';
  const heroLabel = signedIn ? copy.continueLearning : copy.signIn;

  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Wordmark size="md" className="text-ink-900" />
        <nav className="flex items-center gap-5 text-sm text-ink-600">
          <a
            href="https://github.com/aislamsilvalol-ctrl/noema"
            className="transition-colors duration-fast hover:text-ink-900"
          >
            {copy.github}
          </a>
          <Link
            href={signedIn ? '/chat' : '/login'}
            onClick={() => track('cta_clicked', { location: 'header' })}
            className="transition-colors duration-fast hover:text-ink-900"
          >
            {heroLabel}
          </Link>
          <LanguageSwitcher />
        </nav>
      </header>

      {/* 01 ASK ─────────────────────────────────────────────────────────── */}
      <section
        ref={register('ask')}
        className="mx-auto grid max-w-6xl gap-10 px-6 pb-20 pt-10 md:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] md:items-center md:pt-20"
      >
        <div>
          <p className="text-sm text-ink-500">{copy.eyebrow}</p>
          <form onSubmit={ask} className="mt-6">
            <label htmlFor="ask" className="block font-display text-4xl leading-tight text-ink-900 md:text-5xl">
              {copy.title}
            </label>
            <div className="mt-8 flex max-w-xl gap-2">
              <input
                id="ask"
                ref={input}
                value={subject}
                onChange={(event) => onType(event.target.value)}
                onFocus={() => {
                  mino.on('input_focus');
                  mino.focus(input.current);
                }}
                onBlur={() => !subject && mino.on('input_blur')}
                placeholder={copy.examples[example] ?? copy.placeholder}
                autoComplete="off"
                enterKeyHint="go"
                className="min-w-0 flex-1 rounded-md border border-line bg-raised px-4 py-3.5 text-lg text-ink-900 outline-none transition-colors duration-fast focus:border-signal placeholder:text-ink-400"
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={!subject.trim()}
                busy={status === 'streaming' ? copy.thinking : undefined}
              >
                {copy.submit}
              </Button>
            </div>
          </form>

          {asked && (
            <div className="mt-8 max-w-xl animate-fade-up" aria-live="polite">
              <p className="text-xs uppercase tracking-wide text-signal">Mino</p>
              <div className="mt-2 min-h-[4rem]">
                {reply ? (
                  <Markdown text={reply} className="text-md" />
                ) : (
                  <p className="text-sm text-ink-400">{copy.thinking}</p>
                )}
                {status === 'streaming' && reply && (
                  <span aria-hidden="true" className="ml-0.5 inline-block h-4 w-px animate-pulse bg-signal align-middle" />
                )}
              </div>
              {status !== 'streaming' && (
                <div className="mt-4 flex flex-wrap items-center gap-4">
                  <p className="text-xs text-ink-400">
                    {status === 'live' ? copy.demoNote : copy.sampleNote}
                  </p>
                  <button
                    type="button"
                    onClick={changeSubject}
                    className="text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
                  >
                    {copy.change}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* On a phone the figure is small and comes first, at the right, so it
            shares the first screen with the question instead of sitting
            below it; from md up it takes the right column at full size. */}
        <div className="order-first -mb-4 ml-auto w-28 md:order-none md:mx-auto md:mb-0 md:w-full md:max-w-sm">
          <MinoLive size="xl" primary className="w-full" />
        </div>
      </section>

      {/* 02 PATH ────────────────────────────────────────────────────────── */}
      <Beat
        id="path"
        register={register}
        index="02"
        label={copy.steps.path}
        title={copy.pathTitle}
        body={copy.pathBody}
        flip
      >
        {(() => {
          const b = bank ?? bankFor(copy.examples[0] ?? '', locale);
          return (
            <ol className="rounded-lg border border-line bg-raised p-6 shadow-elevation-1" data-landing-path>
              <p className="text-xs uppercase tracking-wide text-signal">{asked ?? copy.examples[0]}</p>
              {b.path.map((step, index) => (
                <li key={step} className="mt-4 flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className={`mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full border ${
                      index === 0 ? 'border-signal bg-signal' : 'border-line bg-transparent'
                    }`}
                  />
                  <span className={index === 0 ? 'text-base text-ink-900' : 'text-base text-ink-600'}>{step}</span>
                </li>
              ))}
              <p className="mt-5 text-xs text-ink-400">{copy.pathNote}</p>
            </ol>
          );
        })()}
      </Beat>

      {/* 03 LEARN ───────────────────────────────────────────────────────── */}
      <Beat
        id="learn"
        register={register}
        index="03"
        label={copy.steps.learn}
        title={copy.learnTitle}
        body={copy.learnBody}
      >
        <div className="rounded-lg border border-line bg-raised p-6 shadow-elevation-1">
          <p className="border-l-2 border-line pl-3 text-sm text-ink-600">
            {asked ?? copy.examples[0]}
          </p>
          <p className="mt-5 text-xs uppercase tracking-wide text-signal">Mino</p>
          <Markdown text={reply || bankFor(asked ?? copy.examples[0] ?? '', locale).sample} className="mt-2 text-sm" />
        </div>
      </Beat>

      {/* 04 PRACTICE ────────────────────────────────────────────────────── */}
      <Beat
        id="practice"
        register={register}
        index="04"
        label={copy.steps.practice}
        title={copy.practiceTitle}
        body={copy.practiceBody}
        flip
      >
        {(() => {
          const b = bank ?? bankFor(copy.examples[0] ?? '', locale);
          return (
            <div className="rounded-lg border border-line bg-raised p-6 shadow-elevation-1">
              <p className="font-display text-lg text-ink-900">{b.question}</p>
              <ul className="mt-4 space-y-2" role="group" aria-label={b.question}>
                {b.options.map((option, index) => {
                  const chosen = answer === index;
                  const reveal = answered;
                  const tone = reveal
                    ? index === b.correct
                      ? 'border-positive text-ink-900'
                      : chosen
                        ? 'border-critical text-ink-900'
                        : 'border-line text-ink-500'
                    : chosen
                      ? 'border-signal text-ink-900'
                      : 'border-line text-ink-800 hover:border-ink-400';
                  return (
                    <li key={option}>
                      <button
                        type="button"
                        onClick={() => pick(index)}
                        aria-pressed={chosen}
                        disabled={answered}
                        className={`w-full rounded-md border bg-raised px-4 py-3 text-left text-base transition-colors duration-fast ${tone}`}
                      >
                        {option}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {answer !== null && !answered && (
                <div className="mt-4 flex items-center gap-2">
                  <span className="text-sm text-ink-600">{copy.practiceConfident}</span>
                  <Button size="sm" variant="secondary" onClick={() => confirm(true)}>
                    {t.review.confidence[4]}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => confirm(false)}>
                    {t.review.confidence[1]}
                  </Button>
                </div>
              )}
              {answered && (
                <div className={`mt-5 border-l-2 pl-4 ${correct ? 'border-positive' : 'border-critical'}`}>
                  <p className={`text-sm font-medium ${correct ? 'text-positive' : 'text-critical'}`}>
                    {correct ? copy.correct : copy.wrong}
                  </p>
                  {!correct && <p className="mt-2 text-sm text-ink-700">{b.correction}</p>}
                </div>
              )}
            </div>
          );
        })()}
      </Beat>

      {/* 05 ADAPT ───────────────────────────────────────────────────────── */}
      <Beat
        id="adapt"
        register={register}
        index="05"
        label={copy.steps.adapt}
        title={copy.adaptTitle}
        body={copy.adaptBody}
      >
        {(() => {
          const b = bank ?? bankFor(copy.examples[0] ?? '', locale);
          const moved = answered && !correct;
          const rows = [...b.concepts]
            .map((c) => ({ name: c.name, value: moved ? c.after : c.before }))
            .sort((a, z) => a.value - z.value);
          return (
            <div className="rounded-lg border border-line bg-raised px-6 py-3 shadow-elevation-1">
              {moved && <p className="pt-2 text-xs text-signal">{copy.adaptRecomputed}</p>}
              <ul className="divide-y divide-line">
                {rows.map((row) => (
                  <li key={row.name} className="py-3">
                    <div className="flex items-baseline justify-between gap-4 text-sm">
                      <span className="text-ink-800">{row.name}</span>
                      <span className={`font-mono ${row.value < 40 ? 'text-critical' : row.value < 60 ? 'text-ink-600' : 'text-positive'}`}>
                        {row.value}
                      </span>
                    </div>
                    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-sunken">
                      <div
                        className={`h-full rounded-full transition-[width] duration-slow ease-noema ${row.value < 40 ? 'bg-critical' : row.value < 60 ? 'bg-primary' : 'bg-positive'}`}
                        style={{ width: `${row.value}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}
      </Beat>

      {/* 06 REMEMBER ────────────────────────────────────────────────────── */}
      <Beat
        id="remember"
        register={register}
        index="06"
        label={copy.steps.remember}
        title={copy.rememberTitle}
        body={copy.rememberBody}
        flip
      >
        {(() => {
          const b = bank ?? bankFor(copy.examples[0] ?? '', locale);
          return (
            <button
              type="button"
              onClick={() => setFlipped((f) => !f)}
              className="w-full text-left [perspective:1400px] focus-visible:outline-none"
              aria-pressed={flipped}
            >
              <div
                className={`grid transition-transform duration-slow ease-noema [transform-style:preserve-3d] ${flipped ? '[transform:rotateY(180deg)]' : ''}`}
              >
                <div className="col-start-1 row-start-1 rounded-lg border border-line bg-raised p-6 shadow-elevation-1 [backface-visibility:hidden]">
                  <p className="font-serif text-lg text-ink-900">{b.card.front}</p>
                  <p className="mt-6 text-xs text-ink-400">{t.review.showAnswer}</p>
                </div>
                <div className="col-start-1 row-start-1 rounded-lg border border-signal bg-raised p-6 shadow-elevation-2 [backface-visibility:hidden] [transform:rotateY(180deg)]">
                  <p className="text-sm text-ink-500">{b.card.front}</p>
                  <p className="mt-3 font-serif text-lg text-ink-900">{b.card.back}</p>
                  <p className="mt-5 text-xs text-ink-500">{copy.rememberNext(11)}</p>
                </div>
              </div>
            </button>
          );
        })()}
      </Beat>

      {/* CLOSE ──────────────────────────────────────────────────────────── */}
      <section ref={register('close')} className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-24 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:items-center">
          <div className="mx-auto w-full max-w-[14rem] md:max-w-xs">
            <MinoLive size="xl" className="w-full" />
          </div>
          <div>
            <h2 className="font-display text-4xl text-ink-900 md:text-5xl">{copy.closeTitle}</h2>
            <p className="mt-4 text-md text-ink-600">{copy.closeBody}</p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <ButtonLink href={primaryHref} variant="primary" size="lg" onClick={start}>
                {signedIn ? copy.continueLearning : copy.start}
              </ButtonLink>
              {asked && <span className="text-sm text-ink-500">{asked}</span>}
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-ink-500">
          <span>{copy.license}</span>
          <nav className="flex items-center gap-4">
            <Link href="/privacy" className="transition-colors duration-fast hover:text-ink-900">
              {copy.privacy}
            </Link>
            <Link href="/terms" className="transition-colors duration-fast hover:text-ink-900">
              {copy.terms}
            </Link>
          </nav>
        </div>
      </footer>

      {/* The companion: the same character, small, once the hero has scrolled
          away and until the close brings the large figure back. */}
      <div
        aria-hidden="true"
        className={`pointer-events-none fixed bottom-6 right-6 z-40 h-16 w-16 transition-[opacity,transform] duration-normal ease-noema md:h-20 md:w-20 ${
          active === 'ask' || active === 'close' ? 'translate-y-4 opacity-0' : 'translate-y-0 opacity-100'
        }`}
      >
        <MinoLive size="xl" className="h-full w-full" />
      </div>
    </main>
  );
}

function Beat({
  id,
  register,
  index,
  label,
  title,
  body,
  flip = false,
  children,
}: {
  id: Section;
  register: (id: string) => (element: Element | null) => void;
  index: string;
  label: string;
  title: string;
  body: string;
  flip?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section ref={register(id)} className="border-t border-line">
      <div
        className={`mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-2 md:items-center md:py-28 ${
          flip ? 'md:[&>*:first-child]:order-2' : ''
        }`}
      >
        <div className="max-w-reading">
          <p className="font-mono text-xs text-signal">
            {index} · {label}
          </p>
          <h2 className="mt-3 font-display text-3xl leading-tight text-ink-900">{title}</h2>
          <p className="mt-4 text-md text-ink-600">{body}</p>
        </div>
        <div className="w-full max-w-md md:justify-self-center">{children}</div>
      </div>
    </section>
  );
}
