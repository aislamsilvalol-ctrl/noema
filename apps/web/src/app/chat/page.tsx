'use client';

/**
 * The notebook-independent entry point to Noema.
 *
 * `POST /ai/professor` has always supported `notebook_id: null` end to end --
 * `_assemble()` returns the plain, ungrounded tutor prompt and answers from the
 * model's own general knowledge (`apps/api/noema/api/v1/ai.py`). What never
 * existed was a way to *reach* that call without first creating a notebook:
 * the only two components calling this endpoint both live under
 * `/notebooks/[id]/professor` and always pass a real id. A brand-new account
 * could not say "quero aprender psicologia" without material to attach it to
 * first -- see `NOEMA_TEACHING_BEHAVIOR_AUDIT.md` for the full trace.
 *
 * This page is `notebooks/[id]/professor/page.tsx` with the notebook stripped
 * out: no notebook fetch, no "save to notes" (nothing to save into), no
 * exam/flashcard/quiz action cards (those intents redirect to EXPLAIN when
 * there's no notebook, by design -- `needs_notebook_material()` -- so they
 * never fire here). Once someone wants a persistent, material-backed
 * notebook, `/library` is still exactly where that happens.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Shell } from '@/components/Shell';
import { Mino } from '@/components/mino/Mino';
import { Notice } from '@/components/ui/Notice';
import { api, professorChat } from '@/lib/api';
import { humanError, humanStreamError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

interface Turn {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatPage() {
  const t = useT();

  const [turns, setTurns] = useState<Turn[]>([]);
  // The teaching session this conversation belongs to. Kept per tab so a
  // reload continues the same lesson instead of starting a new one — the
  // backend keeps the transcript; this is only the pointer to it.
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessionKey = 'noema.session.chat';
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<{ usedUnits: number; limitUnits: number } | null>(
    null,
  );
  const [limitWarning, setLimitWarning] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);

  const thinkingLabel = useCallback(
    (intent: string): string => {
      const table = t.professor.thinking as Record<string, string>;
      return table[intent] ?? t.professor.thinking.default;
    },
    [t],
  );

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per mount; the key is a constant
  }, []);

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
          session_id: sessionId ?? undefined,
          messages: history.map((turn) => ({ role: turn.role, content: turn.content })),
        },
        {
          onBlocked: (usage) => {
            setStatus(null);
            setTurns((current) => current.slice(0, -1));
            setBlocked({ usedUnits: usage.used_units, limitUnits: usage.limit_units });
          },
          onWarning: (usage) =>
            setLimitWarning(Math.max(usage.limit_units - usage.used_units, 0)),
          onIntent: (intent) => setStatus(thinkingLabel(intent)),
          onSession: (session) => {
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
          onAction: () => setStatus(null),
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

  return (
    <Shell>
      <div className="mx-auto flex max-w-reading flex-col">
        <header>
          <h1 className="font-display text-2xl text-ink-900">{t.chat.title}</h1>
        </header>

        {blocked && (
          <div className="mt-6 rounded-md border border-line p-3">
            <p className="text-sm text-ink-800">{t.professor.limitBlockedTitle}</p>
            <p className="mt-1 text-xs text-ink-500">{t.professor.limitBlockedBody}</p>
          </div>
        )}

        <div className="mt-8 min-h-[40vh] space-y-6">
          {turns.length === 0 && (
            // The first-run moment: Mino, one question, and the composer right
            // below it. No button — the answer is typed, not clicked.
            <Notice
              kind="empty"
              title={t.chat.emptyTitle}
              body={t.chat.emptyLede}
              mino={<Mino state="curious" size="lg" />}
              className="mt-4"
            />
          )}

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
            </div>
          ))}

          {error && (
            <p role="alert" className="text-sm text-critical">
              {error}
            </p>
          )}
        </div>

        <div className="sticky bottom-24 mt-6 border-t border-line bg-surface pt-4 md:bottom-0">
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
              placeholder={t.chat.placeholder}
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
