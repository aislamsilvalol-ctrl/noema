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
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Shell } from '@/components/Shell';
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

    try {
      await professorChat(
        {
          notebook_id: notebookId,
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

  return (
    <Shell>
      <div className="mx-auto flex max-w-reading flex-col">
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl text-ink-900">{t.professor.title}</h1>
            {notebook && <p className="mt-1 text-sm text-ink-500">{notebook.title}</p>}
          </div>
          <Link
            href={`/notebooks/${notebookId}`}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {t.common.backToNotebook}
          </Link>
        </header>

        {blocked && (
          <div className="mt-6 rounded-md border border-line p-3">
            <p className="text-sm text-ink-800">{t.professor.limitBlockedTitle}</p>
            <p className="mt-1 text-xs text-ink-500">{t.professor.limitBlockedBody}</p>
          </div>
        )}

        <div className="mt-8 min-h-[40vh] space-y-6">
          {turns.length === 0 && <p className="text-sm text-ink-500">{t.professor.emptyLede}</p>}

          {turns.map((turn, index) => (
            <div key={index}>
              <span className="text-xs uppercase tracking-wide text-ink-400">
                {turn.role === 'user' ? t.professor.you : 'NOEMA'}
              </span>

              {turn.content && (
                <p className="mt-1 whitespace-pre-wrap text-base text-ink-800">
                  {turn.content}
                  {streaming && index === turns.length - 1 && (
                    <span className="ml-0.5 inline-block h-4 w-px animate-pulse bg-accent align-middle" />
                  )}
                </p>
              )}

              {streaming &&
                index === turns.length - 1 &&
                turn.role === 'assistant' &&
                !turn.content &&
                status && <p className="mt-1 text-sm text-ink-400">{status}</p>}

              {turn.role === 'assistant' &&
                turn.content &&
                !(streaming && index === turns.length - 1) && (
                  <div className="mt-1.5">
                    {(saveState[index] ?? 'idle') === 'idle' && (
                      <button
                        type="button"
                        onClick={() => void saveTurn(index)}
                        className="text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
                      >
                        {t.professor.saveToNotes}
                      </button>
                    )}
                    {saveState[index] === 'saving' && (
                      <span className="text-xs text-ink-400">{t.professor.savingNote}</span>
                    )}
                    {saveState[index] === 'saved' && (
                      <span className="text-xs text-ink-500">
                        {t.professor.savedNote}{' '}
                        <Link href={`/notebooks/${notebookId}`} className="text-accent">
                          {t.professor.openNotebook}
                        </Link>
                      </span>
                    )}
                    {saveState[index] === 'error' && (
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
                <div className="mt-2 rounded-md border border-line px-3 py-2 text-sm text-ink-700">
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
                <div className="mt-2 rounded-md border border-line px-3 py-2 text-sm text-ink-700">
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
            </div>
          ))}

          {error && (
            <p role="alert" className="text-sm text-critical">
              {error}
            </p>
          )}
        </div>

        {/* `sticky` rather than a page-wide `fixed`, so the composer respects
            this column's own width instead of needing to coordinate with
            Shell's fixed mobile tab bar. `bottom-24` clears that bar on
            mobile — the same offset `main`'s own `pb-24` already reserves for
            it; `md:bottom-0` sits flush once the bar is gone. */}
        <div className="sticky bottom-24 mt-6 border-t border-line bg-surface pt-4 md:bottom-0">
          {canQuickAct && (
            <div className="mb-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void ask(t.professor.quickActions.testMe)}
                className="rounded-md border border-line px-2.5 py-1 text-xs text-ink-600 transition-colors duration-state hover:border-ink-400"
              >
                {t.professor.quickActions.testMe}
              </button>
              <button
                type="button"
                onClick={() => void ask(t.professor.quickActions.deepen)}
                className="rounded-md border border-line px-2.5 py-1 text-xs text-ink-600 transition-colors duration-state hover:border-ink-400"
              >
                {t.professor.quickActions.deepen}
              </button>
              <button
                type="button"
                onClick={() => void ask(t.professor.quickActions.summarize)}
                className="rounded-md border border-line px-2.5 py-1 text-xs text-ink-600 transition-colors duration-state hover:border-ink-400"
              >
                {t.professor.quickActions.summarize}
              </button>
            </div>
          )}

          {limitWarning !== null && (
            <p className="mb-2 text-xs text-ink-500">{t.professor.limitWarning(limitWarning)}</p>
          )}

          <form onSubmit={send}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void ask(input);
                }
              }}
              rows={2}
              placeholder={t.professor.placeholder}
              className="w-full resize-none rounded-md border border-line bg-raised px-3 py-2 text-base text-ink-900 outline-none transition-colors duration-state focus:border-accent placeholder:text-ink-400"
            />
            <div className="mt-2 flex items-center justify-between pb-2">
              <span className="text-xs text-ink-400">{t.common.enterToSend}</span>
              {streaming ? (
                <button
                  type="button"
                  onClick={() => abort.current?.abort()}
                  className="text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
                >
                  {t.common.stop}
                </button>
              ) : (
                <button
                  type="submit"
                  className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
                >
                  {t.common.send}
                </button>
              )}
            </div>
          </form>
        </div>
      </div>
    </Shell>
  );
}
