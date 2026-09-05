'use client';

/**
 * The Professor inside a notebook: the same lesson as `/chat`, grounded.
 *
 * With a notebook the engine retrieves the learner's own material into the
 * prompt and cites it; everything else — the journey, the moves, the blocks,
 * the cards, the checkpoints — is the shared `useLesson`. This page adds what
 * only makes sense here: the notebook's title, a way back to it, and "save
 * to notes" on a reply.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { ApiError, api, type Notebook } from '@/lib/api';
import { useT } from '@/lib/i18n';

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

/** A short, single-line note title from the question that prompted the answer. */
function titleFrom(question: string): string {
  const oneLine = question.trim().replace(/\s+/g, ' ');
  return oneLine.length > 80 ? `${oneLine.slice(0, 79)}…` : oneLine;
}

export default function ProfessorPage() {
  return (
    <MinoProvider>
      <ProfessorPageInner />
    </MinoProvider>
  );
}

function ProfessorPageInner() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const notebookId = params.id;
  const lesson = useLesson({ notebookId, sessionKey: `noema.session.${notebookId}` });

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [saveState, setSaveState] = useState<Record<number, SaveState>>({});
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (lesson.turns.length > 0 && typeof end.current?.scrollIntoView === 'function') {
      end.current.scrollIntoView({ block: 'end' });
    }
  }, [lesson.turns.length]);

  const load = useCallback(async () => {
    try {
      setNotebook(await api.notebook(notebookId));
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      // Not fatal on its own — the title just stays blank; the chat below
      // still works, and a real send() failure surfaces its own error.
    }
  }, [notebookId, router]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Saves one of Mino's replies as a real note, linked to this notebook, with
   * the question that produced it folded in as a quoted lede.
   */
  async function saveTurn(index: number) {
    const turn = lesson.turns[index];
    const question = lesson.turns[index - 1];
    if (!turn || turn.role !== 'assistant' || !turn.content) return;

    setSaveState((current) => ({ ...current, [index]: 'saving' }));
    try {
      const title = question ? titleFrom(question.content) : t.professor.title;
      const body = question ? `> ${question.content}\n\n${turn.content}` : turn.content;
      await api.createNote(notebookId, title, body);
      setSaveState((current) => ({ ...current, [index]: 'saved' }));
    } catch {
      setSaveState((current) => ({ ...current, [index]: 'error' }));
    }
  }

  const actions = lesson.streaming
    ? null
    : actionsFor(lesson.turns.length ? lesson.lastMove ?? 'teach' : null, lesson.awaitingCheck, t);

  return (
    <Shell>
      <MinoPresence />
      <div className="mx-auto flex max-w-reading flex-col">
        <LessonHeader
          title={t.professor.title}
          subtitle={notebook?.title}
          journey={lesson.journey}
          mino={minoStateFor({
            streaming: lesson.streaming,
            status: lesson.status,
            error: lesson.error,
            turns: lesson.turns.length,
          })}
          aside={
            <Link
              href={`/notebooks/${notebookId}`}
              className="text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
            >
              {t.common.backToNotebook}
            </Link>
          }
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
            <Notice
              kind="empty"
              title={t.professor.emptyTitle}
              body={t.professor.emptyLede}
              mino={<Mino state="curious" size="md" className="md:hidden" />}
              className="mt-4"
            />
          )}

          {lesson.turns.map((turn, index) => {
            if (turn.role === 'user') return <LearnerTurn key={index} content={turn.content} />;
            const isLive = lesson.streaming && index === lesson.turns.length - 1;
            const save = saveState[index] ?? 'idle';
            return (
              <LessonBlock
                key={index}
                turn={turn}
                streaming={isLive}
                status={lesson.status}
                onQuizAnswered={lesson.answerQuiz}
                onRecall={(id, rating) => void lesson.recallCard(id, rating)}
                onSubmitAssessment={lesson.submitAssessment}
              >
                {turn.content && !isLive && (
                  <div className="mt-2">
                    {save === 'idle' && (
                      <button
                        type="button"
                        onClick={() => void saveTurn(index)}
                        className="text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
                      >
                        {t.professor.saveToNotes}
                      </button>
                    )}
                    {save === 'saving' && (
                      <span className="text-xs text-ink-400">{t.professor.savingNote}</span>
                    )}
                    {save === 'saved' && (
                      <span className="text-xs text-ink-500">
                        {t.professor.savedNote}{' '}
                        <Link href={`/notebooks/${notebookId}`} className="text-accent">
                          {t.professor.openNotebook}
                        </Link>
                      </span>
                    )}
                    {save === 'error' && (
                      <button
                        type="button"
                        onClick={() => void saveTurn(index)}
                        role="alert"
                        className="text-xs text-critical"
                      >
                        {t.professor.couldNotSaveNote}
                      </button>
                    )}
                  </div>
                )}
              </LessonBlock>
            );
          })}

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
          placeholder={t.professor.placeholder}
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
