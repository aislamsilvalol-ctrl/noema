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
import { MinoPresence } from '@/components/mino/MinoPresence';
import {
  Composer,
  LearnerTurn,
  LessonBlock,
  LessonHeader,
  actionsFor,
  minoStateFor,
} from '@/components/professor/Lesson';
import { useLesson } from '@/components/professor/useLesson';
import { Notice } from '@/components/ui/Notice';
import { useT } from '@/lib/i18n';
import { useEffect, useRef } from 'react';

export default function ChatPage() {
  return (
    <MinoProvider>
      <ChatPageInner />
    </MinoProvider>
  );
}

function ChatPageInner() {
  const t = useT();
  const lesson = useLesson({ sessionKey: 'noema.session.chat' });
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
    : actionsFor(lesson.turns.length ? lesson.lastMove ?? 'teach' : null, lesson.awaitingCheck, t);

  return (
    <Shell>
      <MinoPresence />
      <div className="mx-auto flex max-w-reading flex-col">
        <LessonHeader
          title={t.chat.title}
          journey={lesson.journey}
          mino={minoStateFor({
            streaming: lesson.streaming,
            status: lesson.status,
            error: lesson.error,
            turns: lesson.turns.length,
          })}
        />

        {lesson.blocked && (
          <Notice
            kind="info"
            title={t.professor.limitBlockedTitle}
            body={t.professor.limitBlockedBody}
          />
        )}

        <div className="mt-8 min-h-[40vh] space-y-8">
          {lesson.turns.length === 0 && (
            // The first-run moment: Mino, one question, and the composer right
            // below it. No button — the answer is typed, not clicked.
            <Notice
              kind="empty"
              title={t.chat.emptyTitle}
              body={t.chat.emptyLede}
              mino={<Mino state="curious" size="lg" className="md:hidden" />}
              className="mt-4"
            />
          )}

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

        <Composer
          value={lesson.input}
          onChange={lesson.setInput}
          onSubmit={(event) => {
            event.preventDefault();
            void lesson.ask(lesson.input);
          }}
          onStop={lesson.stop}
          streaming={lesson.streaming}
          placeholder={t.chat.placeholder}
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
              <p className="mb-2 text-xs text-ink-500">
                {t.professor.limitWarning(lesson.limitWarning)}
              </p>
            ) : null
          }
        />
      </div>
    </Shell>
  );
}
