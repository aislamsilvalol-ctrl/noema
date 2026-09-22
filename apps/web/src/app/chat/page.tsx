'use client';

/**
 * The notebook-independent entry point to Noema: a lesson with Mino.
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
import { Notice } from '@/components/ui/Notice';
import { useT } from '@/lib/i18n';
import { useLearningMode } from '@/lib/useLearningMode';
import { useEffect, useRef, useState } from 'react';

export default function ChatPage() {
  return (
    <MinoProvider>
      <ChatPageInner />
    </MinoProvider>
  );
}

function ChatPageInner() {
  const t = useT();
  // `/chat?new=1` starts a lesson instead of resuming the newest one — the
  // way in from "start something new". Read once, on the client; the server
  // render has no query string and no turns either way.
  const [fresh] = useState(
    () => typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('new'),
  );
  useEffect(() => {
    if (!fresh) return;
    try {
      window.sessionStorage.removeItem('noema.session.chat');
    } catch {
      // nothing stored, nothing to forget
    }
  }, [fresh]);
  const lesson = useLesson({ sessionKey: 'noema.session.chat', resumeLatest: !fresh });
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
