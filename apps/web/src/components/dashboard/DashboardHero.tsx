'use client';

/**
 * The first thing on Home, and the only large one: a window onto the
 * territory, with the answer to "where am I, what am I learning, what now"
 * set in its sky. A journey shows its subject, the lesson being taught, the
 * next concept, a ring of what is mastered and Continue. A loose lesson shows
 * what it has. A first day asks one question with a field to answer it in.
 *
 * Until the data is in, the frame is the sky alone — no skeleton boxes, no
 * photograph popping in half-drawn. The plate fades in once it has loaded.
 */

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { ButtonLink } from '@/components/ui/Button';
import { track } from '@/lib/analytics';
import { useT } from '@/lib/i18n';
import { rememberPrefill } from '@/lib/prefill';
import { Landscape } from './Landscape';
import type { DayPart, Place, Plate } from './homeState';

/** Pointer depth on devices with a fine pointer; still elsewhere. */
function useDepth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof window.matchMedia !== 'function') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!window.matchMedia('(pointer: fine)').matches) return;
    let raf = 0;
    let x = 0;
    let y = 0;
    const apply = () => {
      raf = 0;
      el.style.setProperty('--mx', x.toFixed(3));
      el.style.setProperty('--my', y.toFixed(3));
    };
    const move = (event: PointerEvent) => {
      const box = el.getBoundingClientRect();
      x = ((event.clientX - box.left) / box.width) * 2 - 1;
      y = ((event.clientY - box.top) / box.height) * 2 - 1;
      if (!raf) raf = window.requestAnimationFrame(apply);
    };
    el.addEventListener('pointermove', move, { passive: true });
    return () => {
      el.removeEventListener('pointermove', move);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, []);
  return ref;
}

function Frame({
  plate,
  part,
  children,
}: {
  plate: Plate | null;
  part: DayPart;
  children: ReactNode;
}) {
  const depth = useDepth<HTMLElement>();
  const [loaded, setLoaded] = useState(false);
  const [ready, setReady] = useState(false);
  // The push-in starts once the photograph is there, so it is seen.
  useEffect(() => {
    if (!loaded) return;
    const raf = window.requestAnimationFrame(() => setReady(true));
    return () => window.cancelAnimationFrame(raf);
  }, [loaded]);
  useEffect(() => {
    setLoaded(false);
    setReady(false);
  }, [plate]);

  return (
    <section
      ref={depth}
      data-dash-hero
      data-plate={plate ?? undefined}
      className="dash-frame relative -mx-6 overflow-hidden text-dash-bone md:mx-0 md:rounded-lg"
    >
      {plate && (
        <div
          className="dash-plate dash-plate-box absolute"
          aria-hidden="true"
          data-loaded={loaded}
          data-ready={ready}
        >
          <Landscape plate={plate} priority sizes="(min-width: 768px) 80vw, 100vw" className="block h-full w-full" onLoad={() => setLoaded(true)} />
        </div>
      )}
      <div className="dash-veil dash-plate-box absolute" data-part={part} aria-hidden="true" />
      <div className="dash-type relative flex min-h-[86svh] flex-col justify-end px-6 pb-8 pt-24 md:min-h-[540px] md:justify-center md:px-12 md:py-14 lg:px-14">
        {children}
      </div>
    </section>
  );
}

/** Concepts mastered, as a ring drawn in the alpenglow of the snowcaps. */
function Ring({ mastered, total, label }: { mastered: number; total: number; label: string }) {
  const r = 30;
  const length = 2 * Math.PI * r;
  const share = total > 0 ? mastered / total : 0;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 72 72" className="h-16 w-16 shrink-0 -rotate-90 md:h-[72px] md:w-[72px]" role="img" aria-label={label}>
        <circle cx="36" cy="36" r={r} fill="none" stroke="currentColor" strokeOpacity="0.18" strokeWidth="5" />
        {share > 0 && (
          <circle
            cx="36"
            cy="36"
            r={r}
            fill="none"
            stroke="rgb(var(--dash-alpenglow))"
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={length}
            strokeDashoffset={length * (1 - share)}
            className="dash-arc"
            style={{ '--dash-length': `${length}` } as React.CSSProperties}
          />
        )}
      </svg>
      <p className="text-sm leading-snug text-dash-bone/80" aria-hidden="true">
        <span className="block font-display text-xl tabular-nums text-dash-bone">
          {mastered}
          <span className="text-base text-dash-bone/60">/{total}</span>
        </span>
        {label}
      </p>
    </div>
  );
}

export interface HeroLesson {
  subject: string;
  /** The display line: the lesson being taught, or the subject. */
  headline: string;
  next: string | null;
  place: Place | null;
  href: string;
}

export function DashboardHero({
  loading,
  plate,
  part,
  greeting,
  ask,
  lesson,
  review,
}: {
  loading: boolean;
  plate: Plate | null;
  part: DayPart;
  greeting: string;
  ask: string;
  /** What to continue; null on a first day. */
  lesson: HeroLesson | null;
  /** Reviews due, offered quietly beside Continue. */
  review: { due: number; minutes: number } | null;
}) {
  const t = useT();
  const copy = t.home;

  if (loading) {
    return (
      <Frame plate={null} part={part}>
        <p className="dash-rise text-lg text-dash-bone/80">{copy.preparing}</p>
      </Frame>
    );
  }

  if (!lesson) {
    return (
      <Frame plate={plate} part={part}>
        <FirstDay greeting={greeting} />
      </Frame>
    );
  }

  const { place } = lesson;
  const lessonNumber = place && place.total > 0 ? Math.min(place.done + 1, place.total) : null;

  return (
    <Frame plate={plate} part={part}>
      <div className="max-w-[36rem]">
        <p className="dash-rise text-sm text-dash-bone/80 md:text-lg">
          {greeting} <span className="hidden sm:inline">{ask}</span>
        </p>
        <p
          className="dash-rise mt-5 inline-flex items-center gap-2 rounded-full bg-dash-bone/12 px-3 py-1 font-mono text-xs uppercase tracking-[0.12em] backdrop-blur-sm md:mt-10"
          style={{ '--dash-delay': '60ms' } as React.CSSProperties}
        >
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-dash-ember" />
          {lesson.subject}
        </p>
        <h1
          className="dash-rise mt-4 font-display text-[2.5rem] leading-[1.02] tracking-[-0.03em] text-dash-bone md:text-4xl"
          style={{ '--dash-delay': '100ms' } as React.CSSProperties}
        >
          {lesson.headline}
        </h1>
        {(lesson.next || lessonNumber) && (
          <p className="dash-rise mt-3 text-md text-dash-bone/80" style={{ '--dash-delay': '140ms' } as React.CSSProperties}>
            {[lesson.next ? copy.next(lesson.next) : null, lessonNumber && place ? copy.lessonOf(lessonNumber, place.total) : null]
              .filter(Boolean)
              .join(' · ')}
          </p>
        )}

        <div
          className="dash-rise mt-8 flex flex-col gap-6 md:mt-10 md:flex-row md:items-center md:gap-10"
          style={{ '--dash-delay': '200ms' } as React.CSSProperties}
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-5">
            <ButtonLink
              href={lesson.href}
              size="lg"
              aria-label={copy.continueAria(lesson.subject)}
              className="dash-ember w-full px-7 sm:w-auto"
              onClick={() => track('continue_learning_clicked', { from: 'hero' })}
              data-continue
            >
              {copy.continue}
              <span aria-hidden="true">→</span>
            </ButtonLink>
            {review && (
              <Link
                href="/review"
                onClick={() => track('review_started', { from: 'hero' })}
                className="min-h-11 py-3 text-center text-sm text-dash-bone/85 underline-offset-4 hover:text-dash-bone hover:underline sm:text-left"
              >
                {copy.quickReview(review.due, review.minutes)}
              </Link>
            )}
          </div>
          {place && place.concepts > 0 && (
            <Ring mastered={place.mastered} total={place.concepts} label={copy.ringLabel(place.mastered, place.concepts)} />
          )}
        </div>
      </div>
    </Frame>
  );
}

function FirstDay({ greeting }: { greeting: string }) {
  const t = useT();
  const copy = t.home.firstDay;
  const router = useRouter();
  const [subject, setSubject] = useState('');

  function start(text: string, from: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    track('continue_learning_clicked', { from });
    // /learn/new picks the subject up, so nobody types it twice.
    rememberPrefill(trimmed);
    router.push('/learn/new');
  }

  return (
    <div className="max-w-[40rem]">
      <p className="dash-rise text-base text-dash-bone/80 md:text-lg">{greeting}</p>
      <h1
        className="dash-rise mt-4 font-display text-[2.5rem] leading-[1.02] tracking-[-0.03em] text-dash-bone md:text-4xl"
        style={{ '--dash-delay': '80ms' } as React.CSSProperties}
      >
        {copy.title}
      </h1>
      <p className="dash-rise mt-4 max-w-[32rem] text-md text-dash-bone/80" style={{ '--dash-delay': '120ms' } as React.CSSProperties}>
        {copy.body}
      </p>
      <form
        className="dash-rise mt-8 flex flex-col gap-3 sm:flex-row"
        style={{ '--dash-delay': '180ms' } as React.CSSProperties}
        onSubmit={(event) => {
          event.preventDefault();
          start(subject, 'first_day');
        }}
      >
        <label htmlFor="home-subject" className="sr-only">
          {copy.label}
        </label>
        <input
          id="home-subject"
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
          placeholder={copy.placeholder}
          autoComplete="off"
          className="min-h-12 flex-1 rounded-md border border-dash-bone/25 bg-dash-night/35 px-4 text-base text-dash-bone placeholder:text-dash-bone/55 backdrop-blur-sm focus:border-dash-bone/70 focus:outline-none"
        />
        <button type="submit" className="dash-ember inline-flex min-h-12 items-center justify-center gap-2 rounded-md px-6 text-base font-medium transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2">
          {copy.submit}
          <span aria-hidden="true">→</span>
        </button>
      </form>
      <div className="dash-rise mt-6" style={{ '--dash-delay': '240ms' } as React.CSSProperties}>
        <p className="text-sm text-dash-bone/70">{copy.ideas}</p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {t.home.explore.ideas.map((idea) => (
            <li key={idea.title}>
              <button
                type="button"
                onClick={() => start(idea.title, 'first_day_idea')}
                className="min-h-11 rounded-full border border-dash-bone/25 px-4 text-sm text-dash-bone/90 transition-colors duration-fast hover:border-dash-bone/60 hover:bg-dash-bone/10 active:scale-[0.98]"
              >
                {idea.title}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
