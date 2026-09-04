'use client';

/**
 * Noema: one composer, no mode picker.
 *
 * `TutorPanel` (the notebook page's rail) still exists and still lets someone
 * pick Explain/Socratic/Examiner/Partner/Feynman by hand — that manual path is
 * untouched. This page is the other one: you just ask, and `POST /ai/professor`
 * decides whether that means explaining, going deeper, summarizing, quizzing,
 * making a flashcard, or sitting an exam, then does it. The `intent` event
 * names the choice so the "thinking…" line says something truer than a
 * generic spinner would.
 *
 * Presentation is the shared learning-session pieces in
 * `components/professor/Lesson.tsx`; the request, session, save-to-notes and
 * created-items logic is here, unchanged.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Shell } from '@/components/Shell';
import { Mino } from '@/components/mino/Mino';
import {
  Composer,
  LearnerTurn,
  LessonBlock,
  LessonHeader,
  minoStateFor,
  type LessonPlace,
} from '@/components/professor/Lesson';
import { Notice } from '@/components/ui/Notice';
import { ApiError, api, professorChat, type Notebook } from '@/lib/api';
import { humanError, humanStreamError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

interface ActionResult {
  intent: string;
  count: number;
  examId?: string;
  minutes?: number;
}

interface Turn {
  role: 'user' | 'assistant';
  content: string;
  action?: ActionResult;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

/**
 * A short, single-line note title from the question that prompted the
 * answer -- `ask()` only ever stores a trimmed, non-empty question, so this
 * never actually sees an empty string in practice.
 */
function titleFrom(question: string): string {
  const oneLine = question.trim().replace(/\s+/g, ' ');
  return oneLine.length > 80 ? `${oneLine.slice(0, 79)}…` : oneLine;
}

export default function ProfessorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const notebookId = params.id;

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  // The teaching session this conversation belongs to. Kept per tab so a
  // reload continues the same lesson instead of starting a new one — the
  // backend keeps the transcript; this is only the pointer to it.
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessionKey = `noema.session.${notebookId}`;
  const [place, setPlace] = useState<LessonPlace | null>(null);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<Record<number, SaveState>>({});
  const [blocked, setBlocked] = useState<{ usedUnits: number; limitUnits: number } | null>(
    null,
  );
  const [limitWarning, setLimitWarning] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);

  // A new turn brings the page to it; the sticky composer would otherwise
  // hide the reply being written right behind it.
  useEffect(() => {
    if (turns.length > 0 && typeof end.current?.scrollIntoView === 'function') {
      end.current.scrollIntoView({ block: 'end' });
    }
  }, [turns.length]);

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

  // Resume: if this tab was in a lesson, reload it from the server rather
  // than starting the learner over. A missing or ended session simply starts
  // fresh — the honest fallback, not an error worth showing.
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.sessionStorage.getItem(sessionKey);
    } catch {
      return;
    }
    if (!stored) return;
    let cancelled = false;
    api
      .session(stored)
      .then((session) => {
        if (cancelled || session.ended_at) return;
        setSessionId(session.id);
        setPlace({
          subject: session.subject,
          topic: session.current_topic,
          concept: session.current_concept,
        });
        setTurns(
          session.turns.map((turn) => ({
            role: turn.role === 'learner' ? 'user' : 'assistant',
            content: turn.content,
          })),
        );
      })
      .catch(() => {
        try {
          window.sessionStorage.removeItem(sessionKey);
        } catch {
          // nothing to clear
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per mount; the key is stable per page
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshPlace = useCallback((id: string) => {
    api
      .session(id)
      .then((session) =>
        setPlace({
          subject: session.subject,
          topic: session.current_topic,
          concept: session.current_concept,
        }),
      )
      .catch(() => undefined);
  }, []);

  const thinkingLabel = (intent: string): string => {
    const table = t.professor.thinking as Record<string, string>;
    return table[intent] ?? t.professor.thinking.default;
  };

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;

    const history: Turn[] = [...turns, { role: 'user', content: trimmed }];
    setTurns([...history, { role: 'assistant', content: '' }]);
    setInput('');
    setStreaming(true);
    setError(null);
    setBlocked(null);
    setLimitWarning(null);
    setStatus(t.professor.thinking.default);

    abort.current = new AbortController();
    let activeSession = sessionId;

    try {
      await professorChat(
        {
          notebook_id: notebookId,
          session_id: sessionId ?? undefined,
          messages: history.map((turn) => ({ role: turn.role, content: turn.content })),
        },
        {
          onBlocked: (usage) => {
            setStatus(null);
            // The turn never ran -- no assistant reply is coming for the
            // placeholder pushed above, so drop it rather than leave an
            // empty bubble nothing will ever fill.
            setTurns((current) => current.slice(0, -1));
            setBlocked({ usedUnits: usage.used_units, limitUnits: usage.limit_units });
          },
          onWarning: (usage) =>
            setLimitWarning(Math.max(usage.limit_units - usage.used_units, 0)),
          onIntent: (intent) => setStatus(thinkingLabel(intent)),
          onSession: (session) => {
            activeSession = session.id;
            setSessionId(session.id);
            try {
              window.sessionStorage.setItem(sessionKey, session.id);
            } catch {
              // Storage blocked: the id still lives in state for this visit.
            }
          },
          onToken: (chunk) => {
            setStatus(null);
            setTurns((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              if (last) next[next.length - 1] = { ...last, content: last.content + chunk };
              return next;
            });
          },
          onAction: (action) => {
            setStatus(null);
            setTurns((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              if (last) {
                next[next.length - 1] = {
                  ...last,
                  action: {
                    intent: action.intent,
                    count: action.count,
                    examId: action.exam_id,
                    minutes: action.minutes,
                  },
                };
              }
              return next;
            });
          },
          onError: (message, event) => setError(humanStreamError(event ?? { message }, t)),
        },
        abort.current.signal,
      );
    } catch (err) {
      setError(humanError(err, t, 'ai'));
    } finally {
      setStreaming(false);
      setStatus(null);
      if (activeSession) refreshPlace(activeSession);
    }
  }

  function send(event: React.FormEvent) {
    event.preventDefault();
    void ask(input);
  }

  /**
   * Saves one assistant turn as a real note, linked to this notebook.
   *
   * There is no persisted conversation to link back to -- `POST /ai/professor`
   * is stateless per call -- so the honest version of "keep the link to the
   * conversation" is folding the question that produced the answer into the
   * note itself, as a quoted lede, rather than a foreign key this backend
   * does not have.
   */
  async function saveTurn(index: number) {
    const turn = turns[index];
    const question = turns[index - 1];
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

  const lastTurn = turns[turns.length - 1];
  const canQuickAct = !streaming && lastTurn?.role === 'assistant' && Boolean(lastTurn.content);
  const quick = t.professor.quickActions;

  return (
    <Shell>
      <div className="mx-auto flex max-w-reading flex-col">
        <LessonHeader
          title={t.professor.title}
          subtitle={notebook?.title}
          place={place}
          mino={minoStateFor({ streaming, status, error, turns: turns.length })}
          aside={
            <Link
              href={`/notebooks/${notebookId}`}
              className="text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
            >
              {t.common.backToNotebook}
            </Link>
          }
        />

        {blocked && (
          <Notice
            kind="info"
            title={t.professor.limitBlockedTitle}
            body={t.professor.limitBlockedBody}
          />
        )}

        <div className="mt-8 min-h-[40vh] space-y-8">
          {turns.length === 0 && (
            <Notice
              kind="empty"
              title={t.professor.emptyTitle}
              body={t.professor.emptyLede}
              mino={<Mino state="curious" size="md" />}
              className="mt-4"
            />
          )}

          {turns.map((turn, index) => {
            if (turn.role === 'user') return <LearnerTurn key={index} content={turn.content} />;
            const isLive = streaming && index === turns.length - 1;
            const save = saveState[index] ?? 'idle';
            return (
              <LessonBlock key={index} content={turn.content} streaming={isLive} status={status}>
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

                {turn.action && turn.action.intent === 'create_exam' && turn.action.examId && (
                  <div className="mt-3 rounded-md border border-line px-3 py-2 text-sm text-ink-700">
                    <p>{t.professor.examCreated(turn.action.minutes ?? 0)}</p>
                    <Link
                      href={`/notebooks/${notebookId}/exam?examId=${turn.action.examId}`}
                      className="mt-1 inline-block text-sm text-accent"
                    >
                      {t.professor.startExam}
                    </Link>
                  </div>
                )}

                {turn.action && turn.action.intent !== 'create_exam' && (
                  <div className="mt-3 rounded-md border border-line px-3 py-2 text-sm text-ink-700">
                    <p>
                      {turn.action.intent === 'create_flashcard'
                        ? t.professor.flashcardsCreated(turn.action.count)
                        : t.professor.questionsCreated(turn.action.count)}
                    </p>
                    <Link
                      href={`/notebooks/${notebookId}/${
                        turn.action.intent === 'create_flashcard' ? 'cards' : 'quiz'
                      }`}
                      className="mt-1 inline-block text-sm text-accent"
                    >
                      {turn.action.intent === 'create_flashcard'
                        ? t.professor.openCards
                        : t.professor.openQuiz}
                    </Link>
                  </div>
                )}
              </LessonBlock>
            );
          })}

          {error && (
            <p role="alert" className="text-sm text-critical">
              {error}
            </p>
          )}
          <div ref={end} aria-hidden="true" />
        </div>

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={send}
          onStop={() => abort.current?.abort()}
          streaming={streaming}
          placeholder={t.professor.placeholder}
          quickActions={
            canQuickAct
              ? [
                  { label: quick.testMe, onClick: () => void ask(quick.testMe) },
                  { label: quick.deepen, onClick: () => void ask(quick.deepen) },
                  { label: quick.differently, onClick: () => void ask(quick.differently) },
                  { label: quick.summarize, onClick: () => void ask(quick.summarize) },
                ]
              : null
          }
          notice={
            limitWarning !== null ? (
              <p className="mb-2 text-xs text-ink-500">{t.professor.limitWarning(limitWarning)}</p>
            ) : null
          }
        />
      </div>
    </Shell>
  );
}
