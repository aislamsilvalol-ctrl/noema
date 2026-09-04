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
 *
 * Presentation is the shared learning-session pieces in
 * `components/professor/Lesson.tsx`; the request and session logic is here.
 */

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
import { api, professorChat } from '@/lib/api';
import { humanError, humanStreamError } from '@/lib/errors';
import { useT } from '@/lib/i18n';
import { takePrefill } from '@/lib/prefill';

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
  // Where the lesson is, for the header. Read from the session, never guessed.
  const [place, setPlace] = useState<LessonPlace | null>(null);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  const thinkingLabel = useCallback(
    (intent: string): string => {
      const table = t.professor.thinking as Record<string, string>;
      return table[intent] ?? t.professor.thinking.default;
    },
    [t],
  );

  // A sentence carried from another screen arrives here, once, so nobody
  // types it twice; the create-learning flow asks for it to be sent.
  useEffect(() => {
    const carried = takePrefill();
    if (!carried) return;
    if (carried.autosend) void ask(carried.text);
    else setInput(carried.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount; `ask` is stable for an empty lesson
  }, []);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per mount; the key is a constant
  }, []);

  // After a turn, the session may have moved on (new concept, new topic).
  // Best effort: the header is a courtesy, not a dependency.
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
      if (activeSession) refreshPlace(activeSession);
    }
  }

  function send(event: React.FormEvent) {
    event.preventDefault();
    void ask(input);
  }

  const lastTurn = turns[turns.length - 1];
  const canQuickAct = !streaming && lastTurn?.role === 'assistant' && Boolean(lastTurn.content);
  const quick = t.professor.quickActions;

  return (
    <Shell>
      <div className="mx-auto flex max-w-reading flex-col">
        <LessonHeader
          title={t.chat.title}
          place={place}
          mino={minoStateFor({ streaming, status, error, turns: turns.length })}
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

          {turns.map((turn, index) =>
            turn.role === 'user' ? (
              <LearnerTurn key={index} content={turn.content} />
            ) : (
              <LessonBlock
                key={index}
                content={turn.content}
                streaming={streaming && index === turns.length - 1}
                status={status}
              />
            ),
          )}

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
          placeholder={t.chat.placeholder}
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
