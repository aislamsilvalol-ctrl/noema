'use client';

/**
 * Modo TDAH — a session. One block at a time, nothing else on screen.
 *
 * The only chrome is the top line (step, progress, time left, Pausar, Sair).
 * Under it, one thing: Mino's latest reply with its interaction and the
 * composer (a learn sitting), or one card (a review sitting). Each answered
 * interaction is a step; after it, the feedback stays on screen with
 * "Continuar" or "Pausa" under it — an offer, never a forced timer.
 *
 * Everything that matters lives on the server, so a refresh, a closed tab
 * or another device lands on the same step: the sitting is
 * `/focus/sessions/{id}` (its id is in the URL), the lesson is the teaching
 * session the sitting points at, and the cards are the due queue. The
 * learning goes through the ordinary endpoints — `/ai/professor` with
 * `focus: true`, `/reviews` — so mastery, the student model, schedules and
 * XP move exactly as they do in normal mode.
 */

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import {
  FocoGuide,
  FocoTopLine,
  minutesLeft,
  taskLabel,
  type GuideState,
} from '@/components/foco/Foco';
import { MinoProvider } from '@/components/mino/Mino';
import { Composer, LearnerTurn, LessonBlock } from '@/components/professor/Lesson';
import { useLesson } from '@/components/professor/useLesson';
import { Button } from '@/components/ui/Button';
import { Loading } from '@/components/ui/Loading';
import {
  ApiError,
  api,
  type DueCard,
  type FocusSession,
  type NextActivity,
} from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useI18n, useT } from '@/lib/i18n';
import { newClientEventId } from '@/lib/offlineQueue';
import { leaveFocusMode, useLearningMode } from '@/lib/useLearningMode';

type Phase = 'step' | 'stepDone' | 'break' | 'complete';

export default function FocoSessionPage() {
  return (
    <Suspense fallback={null}>
      <MinoProvider>
        <FocoSession />
      </MinoProvider>
    </Suspense>
  );
}

function initialPhase(session: FocusSession): Phase {
  if (session.status === 'completed') return 'complete';
  if (session.status === 'paused') return 'break';
  return 'step';
}

function FocoSession() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const id = params.get('id');
  const [focus, setFocus] = useState<FocusSession | null>(null);
  const focusRef = useRef<FocusSession | null>(null);
  const [phase, setPhase] = useState<Phase>('step');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Time left is the server's number at `receivedAt`, counted down here.
  const [receivedAt, setReceivedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  const apply = useCallback((next: FocusSession) => {
    focusRef.current = next;
    setFocus(next);
    setReceivedAt(Date.now());
    setNow(Date.now());
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = id ? api.focusSession(id) : api.focusCurrent();
    load
      .then((session) => {
        if (cancelled) return;
        if (!session || session.status === 'abandoned') {
          router.replace('/foco');
          return;
        }
        if (!id) {
          router.replace(`/foco/sessao?id=${encodeURIComponent(session.id)}`);
        }
        apply(session);
        setPhase(initialPhase(session));
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isUnauthorized) {
          router.push(`/login?next=${encodeURIComponent(`/foco/sessao?id=${id ?? ''}`)}`);
          return;
        }
        if (err instanceof ApiError && err.problem.status === 404) {
          router.replace('/foco');
          return;
        }
        setError(t.foco.loadFailed);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per sitting id
  }, [id]);

  const active = focus?.status === 'active';
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, [active]);

  const run = useCallback(
    async (action: () => Promise<FocusSession>, then?: (next: FocusSession) => void) => {
      setBusy(true);
      setError(null);
      try {
        const next = await action();
        apply(next);
        then?.(next);
      } catch (err) {
        setError(humanError(err, t, 'save'));
      } finally {
        setBusy(false);
      }
    },
    [apply, t],
  );

  // One answered interaction: counted once on the server (by its index),
  // then the feedback stays on screen with Continuar / Pausa under it.
  const stepDone = useCallback(() => {
    const current = focusRef.current;
    if (!current) return;
    void run(
      () => api.focusStep(current.id, current.steps_done),
      () => setPhase('stepDone'),
    );
  }, [run]);

  const finish = useCallback(() => {
    const current = focusRef.current;
    if (!current) return;
    void run(
      () => api.focusComplete(current.id),
      () => setPhase('complete'),
    );
  }, [run]);

  const pause = useCallback(() => {
    const current = focusRef.current;
    if (!current) return;
    void run(
      () => api.focusPause(current.id),
      () => setPhase('break'),
    );
  }, [run]);

  const resume = useCallback(() => {
    const current = focusRef.current;
    if (!current) return;
    void run(
      () => api.focusResume(current.id),
      (next) => setPhase(next.steps_done >= next.steps_total ? 'stepDone' : 'step'),
    );
  }, [run]);

  const exit = useCallback(async () => {
    const current = focusRef.current;
    if (current?.status === 'active') {
      // Leaving is a pause: "Continuar sessão" is waiting on the home.
      await api.focusPause(current.id).catch(() => undefined);
    }
    router.push('/foco');
  }, [router]);

  if (!focus) {
    return (
      <div className="mx-auto max-w-reading px-5 pt-16">
        {error ? (
          <p role="alert" className="text-sm text-critical">
            {error}
          </p>
        ) : (
          <Loading mino />
        )}
      </div>
    );
  }

  const seconds =
    focus.seconds_left - (focus.status === 'active' ? Math.floor((now - receivedAt) / 1000) : 0);
  const step = phase === 'step' ? Math.min(focus.steps_done + 1, focus.steps_total) : focus.steps_done;
  const lastStep = focus.steps_done >= focus.steps_total;

  if (phase === 'complete') {
    return <Complete focus={focus} />;
  }

  return (
    // No tab bar here: the composer sits flush on the bottom of the screen.
    <div
      className="flex min-h-screen flex-col bg-surface"
      style={{ ['--noema-tabbar-height' as string]: '0px' }}
      data-foco-session={focus.kind}
      data-foco-phase={phase}
    >
      <FocoTopLine
        step={step}
        done={focus.steps_done}
        total={focus.steps_total}
        minutes={minutesLeft(seconds)}
        onPause={phase === 'break' ? undefined : pause}
        onExit={() => void exit()}
        busy={busy}
      />

      <main className="mx-auto flex w-full max-w-reading flex-1 flex-col px-5 pt-6">
        {phase === 'break' && (
          <section className="flex flex-1 flex-col items-start justify-center pb-24" data-foco-break>
            <FocoGuide state="idle" />
            <h1 className="mt-4 font-display text-2xl text-ink-900">{t.foco.breakTitle}</h1>
            <p className="mt-2 max-w-sm text-base text-ink-600">{t.foco.breakBody}</p>
            <Button variant="primary" size="lg" className="mt-8" onClick={resume} busy={busy ? t.common.loading : undefined} data-foco-resume>
              {t.foco.back}
            </Button>
          </section>
        )}

        {/* Kept mounted through a break, so the lesson does not reload. */}
        <div className={phase === 'break' ? 'hidden' : 'flex flex-1 flex-col'}>
          {focus.kind === 'learn' ? (
            <LearnStep focus={focus} interactive={phase === 'step'} onAnswered={stepDone} />
          ) : (
            <ReviewStep interactive={phase === 'step'} onRated={stepDone} onEmpty={finish} />
          )}

          {phase === 'stepDone' && (
            <div
              className="sticky bottom-0 mt-8 border-t border-line bg-surface pb-[max(1rem,env(safe-area-inset-bottom))] pt-4"
              data-foco-step-done
            >
              <p className="text-sm text-ink-700">{t.foco.stepDone(focus.steps_done, focus.steps_total)}</p>
              <div className="mt-3 flex gap-3">
                {lastStep ? (
                  <Button variant="primary" size="lg" className="flex-1" onClick={finish} busy={busy ? t.common.loading : undefined} data-foco-finish>
                    {t.foco.finish}
                  </Button>
                ) : (
                  <Button variant="primary" size="lg" className="flex-1" onClick={() => setPhase('step')} data-foco-next-step>
                    {t.foco.continue}
                  </Button>
                )}
                <Button size="lg" variant="secondary" onClick={pause} disabled={busy} data-foco-take-break>
                  {t.foco.pause}
                </Button>
              </div>
            </div>
          )}
        </div>

        {error && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {error}
          </p>
        )}
      </main>
    </div>
  );
}

// ── learn: the lesson engine, one reply at a time ─────────────────────────

function LearnStep({
  focus,
  interactive,
  onAnswered,
}: {
  focus: FocusSession;
  interactive: boolean;
  onAnswered: () => void;
}) {
  const t = useT();
  const lesson = useLesson({ session: focus.teaching_session_id ?? null, focus: true });
  const answered = useRef(false);
  const opened = useRef(false);
  const wasStreaming = useRef(false);

  // The first reply of this sitting. Whether it was already asked for is
  // read from the server (a reply written since the sitting started), so a
  // refresh never asks twice.
  useEffect(() => {
    if (lesson.resuming || opened.current || !focus.teaching_session_id) return;
    opened.current = true;
    const started = new Date(focus.started_at).getTime();
    api
      .session(focus.teaching_session_id)
      .then((session) => {
        const replied = session.turns.some(
          (turn) => turn.role === 'noema' && new Date(turn.created_at).getTime() >= started - 1000,
        );
        if (replied) return;
        const opening =
          session.turns.length === 0 && session.learning_goal
            ? session.learning_goal
            : t.foco.opening(focus.concept || focus.title);
        void lesson.ask(opening);
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, after the lesson has loaded
  }, [lesson.resuming]);

  // A reply to something the learner answered has finished: that is a step.
  useEffect(() => {
    if (wasStreaming.current && !lesson.streaming && answered.current) {
      answered.current = false;
      if (!lesson.error) onAnswered();
    }
    wasStreaming.current = lesson.streaming;
  }, [lesson.streaming, lesson.error, onAnswered]);

  const send = (text: string) => {
    if (!text.trim() || lesson.streaming) return;
    answered.current = true;
    void lesson.ask(text);
  };

  const turns = lesson.turns;
  const lastReplyIndex = turns.map((turn) => turn.role).lastIndexOf('assistant');
  const reply = lastReplyIndex >= 0 ? turns[lastReplyIndex] : undefined;
  const prompt = lastReplyIndex > 0 ? turns[lastReplyIndex - 1] : undefined;
  const guide: GuideState = lesson.streaming ? 'thinking' : lesson.cheering ? 'happy' : 'focused';

  if (lesson.resuming || (!reply && !lesson.streaming)) {
    return <Loading mino className="mt-6" />;
  }

  return (
    <div className="flex flex-1 flex-col" data-foco-learn>
      <div className="flex-1 space-y-5 pb-6">
        {prompt && prompt.role === 'user' && turns.length > 2 && <LearnerTurn content={prompt.content} />}
        {reply && (
          <LessonBlock
            turn={reply}
            streaming={lesson.streaming}
            status={lesson.status}
            mino={guide === 'happy' ? 'happy' : guide === 'thinking' ? 'thinking' : 'focused'}
            sessionId={lesson.sessionId}
            onQuizAnswered={(detail) => {
              answered.current = true;
              lesson.answerQuiz(detail);
            }}
          />
        )}
        {lesson.error && (
          <p role="alert" className="text-sm text-critical">
            {lesson.error}
          </p>
        )}
      </div>

      {interactive && (
        <Composer
          value={lesson.input}
          onChange={lesson.setInput}
          onSubmit={(event) => {
            event.preventDefault();
            send(lesson.input);
          }}
          onStop={lesson.stop}
          streaming={lesson.streaming}
          placeholder={t.foco.answerPlaceholder}
          quickActions={
            lesson.streaming ? null : [{ label: t.foco.gotIt, onClick: () => send(t.foco.gotItMessage) }]
          }
        />
      )}
    </div>
  );
}

// ── review: the due queue, one card at a time ─────────────────────────────

const RATINGS = [
  { value: 1, id: 'again' },
  { value: 2, id: 'hard' },
  { value: 3, id: 'good' },
  { value: 4, id: 'easy' },
] as const;

function interval(days: number, locale: string): string {
  const unit = (value: number, kind: Intl.RelativeTimeFormatUnit) =>
    new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(value, kind);
  if (days < 1 / 24) return unit(Math.max(1, Math.round(days * 24 * 60)), 'minute');
  if (days < 1) return unit(Math.round(days * 24), 'hour');
  if (days < 30) return unit(Math.round(days), 'day');
  return unit(Math.round(days / 30), 'month');
}

function ReviewStep({
  interactive,
  onRated,
  onEmpty,
}: {
  interactive: boolean;
  onRated: () => void;
  onEmpty: () => void;
}) {
  const t = useT();
  const { locale } = useI18n();
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [result, setResult] = useState<{ rating: number; days: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownAt = useRef(Date.now());
  const wasInteractive = useRef(interactive);

  useEffect(() => {
    // The due queue as it is now: cards rated in this sitting are no longer
    // due, so after a refresh the first card is the next one.
    api
      .dueCards(undefined, 50)
      .then(setCards)
      .catch((err) => setError(humanError(err, t, 'load')));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once
  }, []);

  // "Continuar" after a rated card: the next card, face down.
  useEffect(() => {
    if (interactive && !wasInteractive.current && result) {
      setResult(null);
      setRevealed(false);
      setIndex((i) => i + 1);
      shownAt.current = Date.now();
    }
    wasInteractive.current = interactive;
  }, [interactive, result]);

  const card = cards?.[index];

  async function rate(rating: 1 | 2 | 3 | 4) {
    if (!card || saving) return;
    setSaving(true);
    setError(null);
    try {
      const outcome = await api.review({
        card_id: card.id,
        rating,
        elapsed_ms: Date.now() - shownAt.current,
        client_event_id: newClientEventId(),
      });
      setResult({ rating, days: outcome.scheduled_days });
      onRated();
    } catch (err) {
      setError(humanError(err, t, 'save'));
    } finally {
      setSaving(false);
    }
  }

  if (cards === null) return error ? <p role="alert" className="text-sm text-critical">{error}</p> : <Loading className="mt-6" />;

  if (!card) {
    return (
      <section className="flex flex-1 flex-col items-start justify-center pb-24" data-foco-review-empty>
        <FocoGuide state="happy" />
        <p className="mt-4 text-base text-ink-700">{t.foco.noMoreCards}</p>
        <Button variant="primary" size="lg" className="mt-6" onClick={onEmpty}>
          {t.foco.finish}
        </Button>
      </section>
    );
  }

  const happy = result !== null && result.rating >= 3;
  return (
    <section className="flex flex-1 flex-col" data-foco-review>
      <FocoGuide state={happy ? 'happy' : 'focused'} size="xs" />
      <div className="mt-4 rounded-lg border border-line bg-raised p-6 shadow-elevation-1">
        <p className="font-serif text-xl text-ink-900" data-foco-card-front>
          {card.front_md}
        </p>
        {revealed && (
          <p className="mt-5 border-t border-line pt-5 text-base text-ink-700" data-foco-card-back>
            {card.back_md}
          </p>
        )}
      </div>

      {result ? (
        <p className="mt-5 text-sm text-ink-700" role="status" data-foco-feedback>
          {t.review.ratings[RATINGS[result.rating - 1]!.id].label} ·{' '}
          {t.foco.nextIn(interval(result.days, locale))}
        </p>
      ) : !revealed ? (
        <Button size="lg" variant="secondary" className="mt-6 w-full" onClick={() => setRevealed(true)} disabled={!interactive}>
          {t.foco.showAnswer}
        </Button>
      ) : (
        <div className="mt-6">
          <p className="text-sm text-ink-600">{t.foco.howDidItGo}</p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {RATINGS.map((r) => (
              <Button
                key={r.value}
                variant={r.value === 3 ? 'primary' : 'secondary'}
                size="lg"
                onClick={() => void rate(r.value)}
                disabled={saving || !interactive}
                data-foco-rate={r.id}
              >
                {t.review.ratings[r.id].label}
              </Button>
            ))}
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-critical">
          {error}
        </p>
      )}
    </section>
  );
}

// ── the end ───────────────────────────────────────────────────────────────

function Complete({ focus }: { focus: FocusSession }) {
  const t = useT();
  const router = useRouter();
  const { mode } = useLearningMode();
  const [next, setNext] = useState<NextActivity | null>(null);

  useEffect(() => {
    api
      .nextActivity()
      .then(setNext)
      .catch(() => undefined);
  }, []);

  const { summary } = focus;
  return (
    <div className="flex min-h-screen flex-col bg-surface px-6 pb-10 pt-[max(1.5rem,env(safe-area-inset-top))]">
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-10" data-foco-complete>
        <FocoGuide state="happy" size="md" />
        <p className="mt-6 font-mono text-xs uppercase tracking-[0.12em] text-signal">{t.foco.name}</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">{t.foco.completeTitle}</h1>
        <ul className="mt-6 space-y-2 text-base text-ink-700" data-foco-summary>
          <li>{t.foco.summarySteps(focus.steps_done)}</li>
          {summary.cards_reviewed > 0 && <li>{t.foco.summaryCards(summary.cards_reviewed)}</li>}
          {summary.concepts_touched.length > 0 && (
            <li>{t.foco.summaryConcepts(summary.concepts_touched.join(', '))}</li>
          )}
        </ul>
        {next && next.kind !== 'start' && (
          <p className="mt-6 border-t border-line pt-4 text-sm text-ink-600" data-foco-up-next>
            {t.foco.next}: <span className="text-ink-900">{taskLabel(next, t)}</span>
          </p>
        )}
        <div className="mt-8 grid gap-3">
          <Button variant="primary" size="lg" onClick={() => router.push('/foco')} data-foco-one-more>
            {t.foco.oneMore}
          </Button>
          <Button
            size="lg"
            variant="secondary"
            onClick={async () => {
              if (mode === 'focus') await leaveFocusMode().catch(() => undefined);
              router.push('/today');
            }}
            data-foco-back-normal
          >
            {t.foco.backToNormal}
          </Button>
        </div>
      </main>
    </div>
  );
}
