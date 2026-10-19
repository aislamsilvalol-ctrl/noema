'use client';

/**
 * "Agora": the one band in deep ultramarine. Mino says, in one sentence, the
 * most useful thing beside Continue — and offers at most two ways to do it:
 * the recommendation itself, and a short Modo TDAH session on the engine's
 * next task. Rows, not cards; each row is one link.
 */

import Link from 'next/link';
import type { ReactNode } from 'react';
import { Mino } from '@/components/mino/Mino';
import type { MinoState } from '@/components/mino/machine';
import { track } from '@/lib/analytics';
import { useT } from '@/lib/i18n';
import { NEW_LESSON } from '@/lib/lessonLinks';
import { rememberPrefill } from '@/lib/prefill';
import { useReveal } from './Landscape';
import type { DayPart, Recommendation } from './homeState';

/** Mino beside a sentence — never one without the other. */
export function CharacterMoment({ mood, children }: { mood: MinoState; children: ReactNode }) {
  return (
    <div className="flex items-start gap-4">
      <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-dash-bone/10" data-mino-mood={mood}>
        <Mino state={mood} size="sm" />
      </span>
      <div className="min-w-0 pt-1">{children}</div>
    </div>
  );
}

function Row({
  href,
  onClick,
  kicker,
  title,
  meta,
  cta,
  dot,
  data,
}: {
  href: string;
  onClick: () => void;
  kicker: string;
  title: string;
  meta: string;
  cta: string;
  dot?: boolean;
  data: string;
}) {
  return (
    <li>
      <Link
        href={href}
        onClick={onClick}
        className="group flex min-h-[72px] items-center gap-4 py-4 transition-colors duration-fast active:bg-dash-bone/5"
        {...{ [data]: '' }}
      >
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.12em] text-dash-bone/60">
            {dot && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-dash-ember" />}
            {kicker}
          </p>
          <p className="mt-1 text-md text-dash-bone">{title}</p>
          <p className="text-sm text-dash-bone/60">{meta}</p>
        </div>
        <span className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-md border border-dash-bone/25 px-3 text-sm text-dash-bone transition-colors duration-fast group-hover:border-dash-bone/70 group-hover:bg-dash-bone/10 sm:px-4">
          <span className="sr-only sm:not-sr-only">{cta}</span>
          <span aria-hidden="true" className="transition-transform duration-normal group-hover:translate-x-0.5">
            →
          </span>
        </span>
      </Link>
    </li>
  );
}

export function NextAction({
  recommendation,
  focusTask,
  focusMinutes,
  mood,
  part,
  memory = null,
}: {
  recommendation: Recommendation | null;
  /** What Mino remembers of the last lesson, said when nothing is more urgent. */
  memory?: string | null;
  /** The engine's next task for Modo TDAH; null when it has none. */
  focusTask: string | null;
  focusMinutes: number;
  mood: MinoState;
  part: DayPart;
}) {
  const t = useT();
  const copy = t.home.now;
  const [ref, shown] = useReveal<HTMLElement>();
  if (!recommendation && !focusTask) return null;

  let sentence = '';
  let primary: ReactNode = null;
  if (recommendation?.kind === 'review') {
    sentence =
      part === 'night'
        ? copy.reviewNight(recommendation.due)
        : recommendation.overdue > 0
          ? copy.reviewOverdue(recommendation.overdue)
          : copy.reviewDue(recommendation.due);
    primary = (
      <Row
        href="/review"
        onClick={() => {
          track('next_action_clicked', { kind: 'review' });
          track('review_started', { from: 'now' });
        }}
        kicker={t.today.reviewsTitle}
        title={t.today.reviewsDue(recommendation.due)}
        meta={copy.minutes(recommendation.minutes)}
        cta={copy.reviewCta}
        data="data-now-review"
      />
    );
  } else if (recommendation?.kind === 'weak') {
    const name = recommendation.name;
    sentence = copy.weak(name);
    primary = (
      <Row
        href={NEW_LESSON}
        onClick={() => {
          track('next_action_clicked', { kind: 'weak' });
          rememberPrefill(t.today.weakMessage(name), true);
        }}
        kicker={t.home.trail.groups.shaky}
        title={copy.weakCta(name)}
        meta={copy.weakMeta(recommendation.score)}
        cta={t.today.weakCta}
        data="data-now-weak"
      />
    );
  } else if (recommendation?.kind === 'continue') {
    sentence = memory ?? copy.continue(recommendation.concept);
  } else if (recommendation?.kind === 'start') {
    sentence = copy.start;
    primary = (
      <Row
        href="/learn/new"
        onClick={() => track('next_action_clicked', { kind: 'start' })}
        kicker={t.today.startLearningTitle}
        title={copy.startCta}
        meta={t.home.firstDay.steps[1] ?? ''}
        cta={t.home.firstDay.submit}
        data="data-now-start"
      />
    );
  } else if (focusTask) {
    sentence = memory ?? copy.continue(focusTask);
  }

  return (
    <section
      ref={ref}
      data-shown={shown}
      aria-labelledby="home-now"
      className="dash-reveal rounded-lg bg-dash-deep px-6 py-8 text-dash-bone md:px-10 md:py-10"
      data-next-action
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14">
        <CharacterMoment mood={mood}>
          <h2 id="home-now" className="font-mono text-xs uppercase tracking-[0.14em] text-dash-alpenglow">
            {copy.title}
          </h2>
          <p className="mt-3 font-display text-xl leading-snug text-dash-bone md:text-2xl md:leading-tight">{sentence}</p>
        </CharacterMoment>
        <ul className="divide-y divide-dash-bone/15 border-y border-dash-bone/15 self-center">
          {primary}
          {focusTask && (
            <FocusSession task={focusTask} minutes={focusMinutes} />
          )}
        </ul>
      </div>
    </section>
  );
}

/** Modo TDAH, offered as what it is: a short session, one goal, the time. */
export function FocusSession({ task, minutes }: { task: string; minutes: number }) {
  const t = useT();
  return (
    <Row
      href="/foco"
      onClick={() => {
        track('next_action_clicked', { kind: 'focus' });
        track('quick_session_started', { from: 'home' });
      }}
      kicker={t.foco.name}
      title={t.home.focus.title(task)}
      meta={t.home.focus.meta(minutes)}
      cta={t.home.focus.cta}
      dot
      data="data-foco-card"
    />
  );
}
