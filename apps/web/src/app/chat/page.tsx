'use client';

/**
 * The notebook-independent entry point to Noema: a lesson with Mino.
 *
 * Which lesson is in the URL: `/chat?session=<id>` opens exactly that one, so
 * a refresh keeps it and two tabs hold two lessons. Plain `/chat` never guesses
 * — it lists the open lessons by subject and offers something new; a lesson
 * started there takes its id into the address as soon as the server makes it.
 *
 * No notebook, no material, no mode picker. The learner writes what they
 * want to learn; the Professor Engine turns it into a journey (goal →
 * curriculum), teaches one idea at a time, checks, writes cards, runs a
 * checkpoint when it is due, and remembers — all server-side. This page
 * draws what arrives: prose, blocks, decks, papers, the course strip, and
 * the character's state. `useLesson` holds the state; `Lesson.tsx` the
 * pieces. Once someone wants a persistent, material-backed notebook,
 * `/library` is still exactly where that happens.
 */

import { Shell } from '@/components/Shell';
import { Mino, MinoProvider } from '@/components/mino/Mino';
import {
  Composer,
  LearnerTurn,
  LessonBlock,
  LessonHeader,
  actionsFor,
  minoStateFor,
} from '@/components/professor/Lesson';
import { FocusStage } from '@/components/professor/FocusStage';
import { StudyRail } from '@/components/professor/StudyRail';
import { useLesson } from '@/components/professor/useLesson';
import { Loading } from '@/components/ui/Loading';
import { Notice } from '@/components/ui/Notice';
import { api, type LessonSummary } from '@/lib/api';
import { useI18n, useT } from '@/lib/i18n';
import { titleFrom } from '@/lib/text';
import { useLearningMode } from '@/lib/useLearningMode';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <MinoProvider>
        <ChatRoute />
      </MinoProvider>
    </Suspense>
  );
}

/**
 * Decides which lesson the page holds. A different `?session=`, `?new=1` or
 * the bare entry remounts the lesson, so nothing of the last one carries over.
 * The one exception is the id this page wrote itself when the server created
 * the lesson: that is the same lesson getting its address, not a new one.
 */
function ChatRoute() {
  const params = useSearchParams();
  const requested = params.get('session');
  const target = requested ?? (params.has('new') ? 'new' : 'entry');
  const born = useRef<string | null>(null);
  const [mount, setMount] = useState({ target, key: 0, session: requested });

  if (target !== mount.target) {
    if (requested !== null && requested === born.current) {
      setMount({ ...mount, target });
    } else {
      born.current = null;
      setMount({ target, key: mount.key + 1, session: requested });
    }
  }

  const adopt = useCallback((id: string) => {
    born.current = id;
    window.history.replaceState(null, '', `/chat?session=${encodeURIComponent(id)}`);
  }, []);

  return <ChatLesson key={mount.key} session={mount.session} onStarted={adopt} />;
}

function ChatLesson({
  session,
  onStarted,
}: {
  session: string | null;
  onStarted: (id: string) => void;
}) {
  const t = useT();
  const lesson = useLesson({ session, onSessionStarted: onStarted });
  const { mode, minutes } = useLearningMode();
  const focus = mode === 'focus';
  const end = useRef<HTMLDivElement>(null);

  // A new turn brings the page to it; the sticky composer would otherwise
  // hide the reply being written right behind it.
  useEffect(() => {
    if (lesson.turns.length > 0 && typeof end.current?.scrollIntoView === 'function') {
      end.current.scrollIntoView({ block: 'end' });
    }
  }, [lesson.turns.length]);

  const actions = lesson.streaming
    ? null
    : actionsFor(lesson.turns.length ? (lesson.lastMove ?? 'teach') : null, lesson.awaitingCheck, t);

  const firstRun = lesson.turns.length === 0 && !lesson.streaming;
  const missing = session !== null && !lesson.resuming && lesson.sessionId === null && firstRun;
  const composer = (
    <Composer
      value={lesson.input}
      onChange={lesson.setInput}
      onSubmit={(event) => {
        event.preventDefault();
        void lesson.ask(lesson.input);
      }}
      onStop={lesson.stop}
      onAsk={firstRun ? undefined : (text) => void lesson.ask(text)}
      streaming={lesson.streaming}
      placeholder={firstRun ? t.chat.firstPlaceholder : t.chat.placeholder}
      inline={firstRun}
      autoFocus={firstRun}
      quickActions={
        actions
          ? actions.map((action) => ({
              label: action.label,
              onClick: () => void lesson.ask(action.text),
            }))
          : null
      }
      notice={
        lesson.limitWarning !== null ? (
          <p className="mb-2 text-xs text-ink-500">{t.professor.limitWarning(lesson.limitWarning)}</p>
        ) : null
      }
    />
  );

  if (lesson.resuming) {
    return (
      <Shell>
        <Loading mino />
      </Shell>
    );
  }

  if (firstRun && !focus) {
    // The first-run stage: one question, the field under it, three ways to
    // start. Mino is here — curious, beside the question — and nowhere else.
    return (
      <Shell>
        <section
          className="mx-auto grid max-w-3xl gap-8 pt-4 md:grid-cols-[9rem_1fr] md:gap-12 md:pt-12"
          data-learning-mode={mode}
          data-first-run
        >
          <Mino state="curious" size="lg" className="hidden md:block" />
          <div className="min-w-0">
            <p className="font-mono text-xs uppercase tracking-[0.12em] text-ink-500">{t.nav.learn}</p>
            <h1 className="mt-3 font-display text-3xl text-ink-900 md:text-4xl">{t.chat.emptyTitle}</h1>
            <p className="mt-4 max-w-reading text-md text-ink-600">{t.chat.emptyLede}</p>
            {missing && <Notice kind="info" title={t.chat.lessonMissing} />}
            {lesson.blocked && (
              <Notice kind="info" title={t.professor.limitBlockedTitle} body={t.professor.limitBlockedBody} />
            )}
            {lesson.safetyMessage && (
              <Notice kind="info" title={t.professor.safetyBlockedTitle} body={lesson.safetyMessage} />
            )}
            {composer}
            {lesson.error && (
              <p role="alert" className="mt-3 text-sm text-critical">
                {lesson.error}
              </p>
            )}
            <ul className="mt-6 flex flex-wrap gap-2" aria-label={t.chat.examplesLabel}>
              {t.chat.examples.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => void lesson.ask(example)}
                    className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-600 transition-colors duration-fast hover:border-ink-400 hover:text-ink-900"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
            <OpenLessons />
          </div>
        </section>
      </Shell>
    );
  }

  return (
    <Shell focus={focus} rail={focus ? undefined : <StudyRail journey={lesson.journey} />}>
      <div className="mx-auto flex max-w-reading flex-col" data-learning-mode={mode}>
        <LessonHeader
          title={t.chat.title}
          journey={focus ? null : lesson.journey}
          aside={
            focus ? undefined : (
              <nav className="flex gap-4 text-sm text-ink-500" aria-label={t.chat.allLessons}>
                <Link href="/chat" className="hover:text-ink-900">
                  {t.chat.allLessons}
                </Link>
                <Link href="/chat?new=1" className="hover:text-ink-900">
                  {t.chat.newLesson}
                </Link>
              </nav>
            )
          }
          mino={minoStateFor({
            streaming: lesson.streaming,
            status: lesson.status,
            error: lesson.error,
            turns: lesson.turns.length,
          })}
        />
        {focus && (
          <FocusStage
            journey={lesson.journey}
            minutes={minutes}
            streaming={lesson.streaming}
            onLost={lesson.lostFocus}
            onStop={() => void lesson.ask(t.professor.focus.stopMessage)}
            onExtend={() => void lesson.ask(t.professor.focus.extendMessage)}
          />
        )}

        {lesson.blocked && (
          <Notice kind="info" title={t.professor.limitBlockedTitle} body={t.professor.limitBlockedBody} />
        )}

        {lesson.safetyMessage && (
          <Notice kind="info" title={t.professor.safetyBlockedTitle} body={lesson.safetyMessage} />
        )}

        <div className="mt-8 min-h-[40vh] space-y-8">
          {lesson.turns.map((turn, index) =>
            turn.role === 'user' ? (
              <LearnerTurn key={index} content={turn.content} />
            ) : (
              <LessonBlock
                key={index}
                turn={turn}
                streaming={lesson.streaming && index === lesson.turns.length - 1}
                status={lesson.status}
                onQuizAnswered={lesson.answerQuiz}
                onRecall={(id, rating) => void lesson.recallCard(id, rating)}
                onSubmitAssessment={lesson.submitAssessment}
                onRecallAnswer={lesson.answerRecall}
                onPark={lesson.parkDecision}
              />
            ),
          )}

          {lesson.error && (
            <p role="alert" className="text-sm text-critical">
              {lesson.error}
            </p>
          )}
          <div ref={end} aria-hidden="true" />
        </div>

        {composer}
      </div>
    </Shell>
  );
}

/**
 * The lessons already under way, each by what it teaches. A row opens that
 * lesson and no other; nothing here is picked for the learner.
 */
function OpenLessons() {
  const t = useT();
  const { locale } = useI18n();
  const [lessons, setLessons] = useState<LessonSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .openLessons()
      .then((items) => {
        if (!cancelled) setLessons(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (lessons.length === 0) return null;
  const date = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' });

  return (
    <section className="mt-12" aria-labelledby="open-lessons">
      <h2 id="open-lessons" className="text-sm text-ink-500">
        {t.chat.continueTitle}
      </h2>
      <ul className="mt-3 divide-y divide-line border-y border-line">
        {lessons.map((item) => {
          const when = item.last_turn_at ?? item.created_at;
          const concept =
            item.current_concept && item.current_concept !== item.subject ? item.current_concept : '';
          return (
            <li key={item.id}>
              <Link
                href={`/chat?session=${encodeURIComponent(item.id)}`}
                className="flex items-baseline justify-between gap-4 py-4 hover:text-ink-900"
              >
                <span className="min-w-0">
                  <span className="block truncate text-md text-ink-900">
                    {item.subject || titleFrom(item.learning_goal)}
                  </span>
                  {concept && <span className="block truncate text-sm text-ink-500">{concept}</span>}
                </span>
                <span className="shrink-0 text-sm text-ink-500">{date.format(new Date(when))}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
