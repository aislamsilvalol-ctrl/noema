'use client';

/**
 * One lesson with Mino, as state: the turns (prose and the structured pieces
 * the server sent with them), the session and journey pointers, what the
 * learner is typing, and the one function that sends.
 *
 * Both Professor screens (`/chat` and the notebook one) use this; they only
 * differ in what they wrap around it. The server decides everything
 * pedagogical — the move, the blocks, the cards, the checkpoint, the
 * character's state — and this hook draws what arrives. It never parses the
 * prose for UI; blocks come as their own events, in arrival order, and are
 * kept as segments beside the text so a reply reads in the order it was
 * written.
 *
 * Learning events go back the same way they came: a quiz option chosen sends
 * the option as the learner's line with the verdict attached; an open check
 * is answered in the composer and tagged as such; a handed-in assessment asks
 * Mino for the correction.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { SERVER_STATES } from '@/components/mino/machine';
import { useMino } from '@/components/mino/MinoController';
import {
  api,
  professorChat,
  type AssessmentView,
  type Journey,
  type LearningEventIn,
  type LessonCard,
} from '@/lib/api';
import { humanError, humanStreamError } from '@/lib/errors';
import { useT } from '@/lib/i18n';
import { takePrefill } from '@/lib/prefill';

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'block'; tool: string; data: Record<string, unknown> }
  | { kind: 'cards'; cards: LessonCard[] }
  | { kind: 'checkpoint'; assessment: AssessmentView }
  | { kind: 'memory'; compacted: number; tokensSaved: number };

export interface ActionResult {
  intent: string;
  count: number;
  examId?: string;
  minutes?: number;
}

export interface Turn {
  role: 'user' | 'assistant';
  /** The prose, joined — for saving to notes and for the empty check. */
  content: string;
  segments: Segment[];
  move?: string;
  action?: ActionResult;
}

export interface LessonState {
  turns: Turn[];
  journey: Journey | null;
  sessionId: string | null;
  input: string;
  setInput: (value: string) => void;
  streaming: boolean;
  status: string | null;
  error: string | null;
  blocked: { usedUnits: number; limitUnits: number } | null;
  limitWarning: number | null;
  lastMove: string | null;
  /** The last reply ended with a question the learner should answer in prose. */
  awaitingCheck: boolean;
  ask: (text: string, event?: LearningEventIn) => Promise<void>;
  stop: () => void;
  answerQuiz: (detail: { question: string; chosen: string; concept: string; correct: boolean }) => void;
  recallCard: (cardId: string, rating: 1 | 2 | 3 | 4) => Promise<void>;
  submitAssessment: (id: string, responses: unknown[]) => Promise<AssessmentView>;
  refreshJourney: () => void;
}

function appendText(turn: Turn, text: string): Turn {
  const segments = [...turn.segments];
  const last = segments[segments.length - 1];
  if (last && last.kind === 'text') {
    segments[segments.length - 1] = { kind: 'text', text: last.text + text };
  } else {
    segments.push({ kind: 'text', text });
  }
  return { ...turn, content: turn.content + text, segments };
}

function appendSegment(turn: Turn, segment: Segment): Turn {
  return { ...turn, segments: [...turn.segments, segment] };
}

/** Segments for a stored reply: its prose, then the blocks it carried. */
function fromStored(content: string, blocks: Record<string, unknown>[] | null | undefined): Segment[] {
  const segments: Segment[] = content ? [{ kind: 'text', text: content }] : [];
  for (const block of blocks ?? []) {
    const { tool, ...data } = block as { tool: string } & Record<string, unknown>;
    if (typeof tool === 'string') segments.push({ kind: 'block', tool, data });
  }
  return segments;
}

export function useLesson({
  notebookId,
  sessionKey,
}: {
  notebookId?: string;
  sessionKey: string;
}): LessonState {
  const t = useT();
  const mino = useMino();

  const [turns, setTurns] = useState<Turn[]>([]);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<{ usedUnits: number; limitUnits: number } | null>(
    null,
  );
  const [limitWarning, setLimitWarning] = useState<number | null>(null);
  const [lastMove, setLastMove] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const sessionRef = useRef<string | null>(null);
  const streamingRef = useRef(false);

  const thinkingLabel = useCallback(
    (intent: string): string => {
      const table = t.professor.thinking as Record<string, string>;
      return table[intent] ?? t.professor.thinking.default;
    },
    [t],
  );

  const updateLast = useCallback((update: (turn: Turn) => Turn) => {
    setTurns((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last && last.role === 'assistant') next[next.length - 1] = update(last);
      return next;
    });
  }, []);

  const refreshJourney = useCallback(() => {
    const id = journey?.id;
    if (!id) return;
    api
      .journey(id)
      .then(setJourney)
      .catch(() => undefined);
  }, [journey?.id]);

  const ask = useCallback(
    async (text: string, event?: LearningEventIn) => {
      const trimmed = text.trim();
      if (!trimmed || streamingRef.current) return;

      setTurns((current) => [
        ...current,
        { role: 'user', content: trimmed, segments: [{ kind: 'text', text: trimmed }] },
        { role: 'assistant', content: '', segments: [] },
      ]);
      setInput('');
      streamingRef.current = true;
      setStreaming(true);
      setError(null);
      setBlocked(null);
      setLimitWarning(null);
      setStatus(t.professor.thinking.default);
      mino.on('request_started');

      abort.current = new AbortController();
      let failed = false;
      let announced = false;
      const finish = () => {
        // `done` may arrive before the stream closes (cards and compaction
        // follow it); the composer is free from the moment the reply is.
        if (!streamingRef.current) return;
        streamingRef.current = false;
        setStreaming(false);
        setStatus(null);
      };

      try {
        await professorChat(
          {
            ...(notebookId ? { notebook_id: notebookId } : {}),
            ...(sessionRef.current ? { session_id: sessionRef.current } : {}),
            messages: [{ role: 'user', content: trimmed }],
            ...(event ? { learning_event: event } : {}),
          },
          {
            onBlocked: (usage) => {
              setStatus(null);
              setTurns((current) => current.slice(0, -1));
              setBlocked({ usedUnits: usage.used_units, limitUnits: usage.limit_units });
            },
            onWarning: (usage) =>
              setLimitWarning(Math.max(usage.limit_units - usage.used_units, 0)),
            onSession: (session) => {
              sessionRef.current = session.id;
              setSessionId(session.id);
              try {
                window.sessionStorage.setItem(sessionKey, session.id);
              } catch {
                // Storage blocked: the id still lives in state for this visit.
              }
            },
            onJourney: (payload) => setJourney((current) => ({ ...(current ?? {}), ...payload }) as Journey),
            onMove: (move) => {
              setLastMove(move.move);
              updateLast((turn) => ({ ...turn, move: move.move }));
            },
            onIntent: (intent) => setStatus(thinkingLabel(intent)),
            onMino: (state) => {
              const named = SERVER_STATES[state];
              if (named) mino.setState(named);
            },
            onToken: (chunk) => {
              setStatus(null);
              if (!announced) {
                announced = true;
                mino.on('response_streaming');
              }
              updateLast((turn) => appendText(turn, chunk));
            },
            onBlock: (block) =>
              updateLast((turn) =>
                appendSegment(turn, { kind: 'block', tool: block.tool, data: block.data }),
              ),
            onFlashcards: (payload) =>
              updateLast((turn) => appendSegment(turn, { kind: 'cards', cards: payload.cards })),
            onCheckpoint: (assessment) =>
              updateLast((turn) => appendSegment(turn, { kind: 'checkpoint', assessment })),
            onMemory: (memory) =>
              updateLast((turn) =>
                appendSegment(turn, {
                  kind: 'memory',
                  compacted: memory.compacted_turns,
                  tokensSaved: memory.tokens_saved,
                }),
              ),
            onAction: (action) => {
              setStatus(null);
              updateLast((turn) => ({
                ...turn,
                action: {
                  intent: action.intent,
                  count: action.count,
                  examId: action.exam_id,
                  minutes: action.minutes,
                },
              }));
            },
            onDone: () => {
              finish();
              mino.on('response_done');
            },
            onError: (message, streamEvent) => {
              setError(humanStreamError(streamEvent ?? { message }, t));
              failed = true;
              mino.on('lost');
            },
          },
          abort.current.signal,
        );
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          setError(humanError(err, t, 'ai'));
          failed = true;
          mino.on('lost');
        }
      } finally {
        finish();
        if (failed) setStatus(null);
      }
    },
    [mino, notebookId, sessionKey, t, thinkingLabel, updateLast],
  );

  // Resume: a lesson this tab was in comes back from the server — its turns,
  // their blocks, and the journey — rather than starting the learner over.
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
        sessionRef.current = session.id;
        setSessionId(session.id);
        setTurns(
          session.turns.map((turn) => ({
            role: turn.role === 'learner' ? 'user' : 'assistant',
            content: turn.content,
            segments: fromStored(turn.content, turn.blocks as Record<string, unknown>[] | null),
          })),
        );
        if (session.journey_id) {
          api
            .journey(session.journey_id)
            .then((loaded) => {
              if (!cancelled) setJourney(loaded);
            })
            .catch(() => undefined);
        }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount; the key is stable per page
  }, []);

  // A sentence carried from another screen arrives once, so nobody types it twice.
  useEffect(() => {
    const carried = takePrefill();
    if (!carried) return;
    if (carried.autosend) void ask(carried.text);
    else setInput(carried.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount
  }, []);

  const answerQuiz = useCallback(
    (detail: { question: string; chosen: string; concept: string; correct: boolean }) => {
      // The option is the learner's line; the verdict rides with it. A short
      // pause lets the reveal be read before Mino answers.
      window.setTimeout(() => {
        void ask(detail.chosen, {
          kind: 'quiz',
          concept: detail.concept,
          correct: detail.correct,
          question: detail.question.slice(0, 600),
          chosen: detail.chosen.slice(0, 300),
        });
      }, 900);
    },
    [ask],
  );

  const recallCard = useCallback(
    async (cardId: string, rating: 1 | 2 | 3 | 4) => {
      if (!journey?.id) return;
      try {
        await api.recallCard(journey.id, cardId, rating);
        mino.react(rating >= 3 ? 'correct' : 'wrong');
      } catch {
        // The card can be graded again from /review; nothing to show here.
      }
    },
    [journey?.id, mino],
  );

  const submitAssessment = useCallback(
    async (id: string, responses: unknown[]) => {
      const graded = await api.submitAssessment(id, responses);
      updateLast((turn) => ({
        ...turn,
        segments: turn.segments.map((segment) =>
          segment.kind === 'checkpoint' && segment.assessment.id === id
            ? { kind: 'checkpoint', assessment: graded }
            : segment,
        ),
      }));
      const score = graded.score ?? 0;
      mino.react(score >= 0.7 ? 'correct' : 'wrong');
      // Mino comments on the paper: the correction is the next turn.
      window.setTimeout(() => {
        void ask(t.professor.exam.handedIn, { kind: 'assessment', assessment_id: id });
      }, 1200);
      return graded;
    },
    [ask, mino, t, updateLast],
  );

  const stop = useCallback(() => abort.current?.abort(), []);

  const last = turns[turns.length - 1];
  const lastBlock =
    last?.role === 'assistant'
      ? [...last.segments].reverse().find((s) => s.kind === 'block')
      : undefined;
  const awaitingCheck =
    !streaming && lastBlock?.kind === 'block' && lastBlock.tool === 'check';

  const askWithCheck = useCallback(
    (text: string, event?: LearningEventIn) => {
      if (!event && awaitingCheck && lastBlock?.kind === 'block') {
        const concept = typeof lastBlock.data.concept === 'string' ? lastBlock.data.concept : '';
        return ask(text, { kind: 'check', concept });
      }
      return ask(text, event);
    },
    [ask, awaitingCheck, lastBlock],
  );

  return {
    turns,
    journey,
    sessionId,
    input,
    setInput,
    streaming,
    status,
    error,
    blocked,
    limitWarning,
    lastMove,
    awaitingCheck,
    ask: askWithCheck,
    stop,
    answerQuiz,
    recallCard,
    submitAssessment,
    refreshJourney,
  };
}
