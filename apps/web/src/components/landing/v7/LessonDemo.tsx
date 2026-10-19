'use client';

/**
 * A lesson, played: the product shown working instead of described.
 *
 * The window is drawn from the lesson's own pieces (Mino's mark and name, the
 * learner's ruled line, the quiz card, the mastery note) so what the visitor
 * sees is what they get. A short script plays once the window is on screen —
 * Mino asks, the learner gets it wrong, Mino changes approach, the learner
 * gets it, a concept firms up — and then the composer is theirs: a question
 * typed there goes to the real tutor (`demoTeach`) and streams into the same
 * window. If the tutor cannot answer, a sample is shown and says so.
 *
 * Reduced motion, or no IntersectionObserver: the finished lesson, still.
 */

import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Mino } from '@/components/mino/Mino';
import type { MinoState } from '@/components/mino/machine';
import { track } from '@/lib/analytics';
import { ApiError, demoTeach } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { Markdown } from '@/lib/markdown';
import { rememberPrefill } from '@/lib/prefill';
import { bankFor } from '../v5/subjects';
import { prefersReducedMotion } from '../v6/useSceneProgress';
import { useInView } from './useInView';

type Item =
  | { kind: 'you'; beat: number; text: string }
  | { kind: 'mino'; beat: number; text: string }
  | { kind: 'strategy'; beat: number; text: string }
  | { kind: 'quiz'; beat: number; question: string; options: string[]; answer: number; pick: number; verdict: string }
  | { kind: 'mastery'; beat: number; items: string[][] };

type Live = { question: string; reply: string; status: 'streaming' | 'live' | 'sample' };

const TYPE_MS = 22;

function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('cancelled', 'AbortError'));
    });
  });
}

export function LessonDemo() {
  const { t, locale } = useI18n();
  const copy = t.landing7.demo;
  const script = copy.script as unknown as Item[];
  const box = useRef<HTMLDivElement>(null);
  const inView = useInView(box);

  // Items before `cursor` are complete; the one at `cursor` is playing.
  const [cursor, setCursor] = useState(0);
  const [typed, setTyped] = useState(0);
  const [phase, setPhase] = useState(0);
  const [run, setRun] = useState(0);
  const [question, setQuestion] = useState('');
  const [live, setLive] = useState<Live | null>(null);
  const ask = useRef<AbortController | null>(null);
  const body = useRef<HTMLDivElement>(null);

  // Read after mount, so the server's markup and the first client render agree.
  const [reduced, setReduced] = useState(false);
  useEffect(() => setReduced(prefersReducedMotion()), []);
  const still = inView === null || reduced;
  const done = still || cursor >= script.length;

  useEffect(() => {
    if (still || !inView || live) return;
    const controller = new AbortController();
    const { signal } = controller;
    async function play() {
      for (let i = 0; i < script.length; i += 1) {
        const item = script[i]!;
        setCursor(i);
        setTyped(0);
        setPhase(0);
        if (item.kind === 'mino') {
          await wait(500, signal);
          for (let n = 1; n <= item.text.length; n += 2) {
            setTyped(n);
            await wait(TYPE_MS, signal);
          }
          setTyped(item.text.length);
          await wait(900, signal);
        } else if (item.kind === 'quiz') {
          await wait(1300, signal);
          setPhase(1);
          await wait(650, signal);
          setPhase(2);
          await wait(item.pick === item.answer ? 1500 : 2100, signal);
        } else {
          await wait(item.kind === 'you' ? 900 : 1100, signal);
        }
      }
      setCursor(script.length);
    }
    play().catch(() => undefined);
    return () => controller.abort();
  }, [still, inView, live, run, script]);

  const at = done ? script.length : cursor;
  const current = script[Math.min(Math.max(at, 0), script.length - 1)];
  const beat = done ? copy.steps.length - 1 : (current?.beat ?? 0);

  const mino = useMemo<MinoState>(() => {
    if (live) return live.status === 'streaming' ? 'teaching' : 'happy';
    if (done) return 'happy';
    if (!current) return 'idle';
    if (current.kind === 'you') return 'listening';
    if (current.kind === 'mino') return 'teaching';
    if (current.kind === 'strategy') return 'thinking';
    if (current.kind === 'mastery') return 'celebrating';
    if (phase < 2) return 'questioning';
    return current.pick === current.answer ? 'happy' : 'correcting';
  }, [live, done, current, phase]);

  // The window keeps its size; what is newest stays in view, as in a lesson.
  useEffect(() => {
    const el = body.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [cursor, typed, phase, live]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || live?.status === 'streaming') return;
    track('cta_clicked', { location: 'teach_ask' });
    rememberPrefill(trimmed);
    setLive({ question: trimmed, reply: '', status: 'streaming' });
    setQuestion('');
    ask.current?.abort();
    ask.current = new AbortController();
    let sawToken = false;
    let failed = false;
    try {
      await demoTeach(
        trimmed,
        {
          onToken: (text) => {
            sawToken = true;
            setLive((current) => (current ? { ...current, reply: current.reply + text } : current));
          },
          onError: () => {
            failed = true;
          },
        },
        ask.current.signal,
      );
    } catch (err) {
      failed = !(err instanceof DOMException && err.name === 'AbortError');
      if (err instanceof ApiError) failed = true;
    }
    setLive((current) =>
      current
        ? failed || !sawToken
          ? { ...current, reply: bankFor(trimmed, locale).sample, status: 'sample' }
          : { ...current, status: 'live' }
        : current,
    );
  }

  function replay() {
    ask.current?.abort();
    setLive(null);
    setCursor(0);
    setRun((n) => n + 1);
  }

  return (
    <div ref={box} className="l7-demo">
      <ol className="l7-rail" aria-hidden="true">
        {copy.steps.map((step, index) => (
          <li key={step} className={index === beat && !live ? 'is-now' : index < beat || live ? 'is-past' : ''}>
            <span className="l7-rail-n">{String(index + 1).padStart(2, '0')}</span>
            {step}
          </li>
        ))}
      </ol>

      <div className="l7-window" data-demo-state={live ? 'live' : done ? 'done' : 'playing'}>
        <header className="l7-window-head">
          <Mino state={mino} size="sm" />
          <div className="min-w-0">
            <p className="font-display text-xl text-ink-900">{live ? live.question : copy.lesson}</p>
            <p className="font-mono text-xs text-ink-500">{live ? 'Mino' : copy.lessonMeta}</p>
          </div>
        </header>

        <div ref={body} className="l7-window-body">
          {live ? (
            <div className="l7-turns" aria-live="polite" aria-busy={live.status === 'streaming' || undefined}>
              <YouLine text={live.question} />
              <MinoTurn>
                {live.reply ? (
                  <Markdown text={live.reply} className="l7-reading" />
                ) : (
                  <p className="text-sm text-ink-500">{t.landing5.hero.thinking}</p>
                )}
                {live.status !== 'streaming' && (
                  <p className="mt-4 text-sm text-ink-500">
                    {live.status === 'live' ? t.landing5.hero.liveNote : t.landing5.hero.sampleNote}
                  </p>
                )}
              </MinoTurn>
            </div>
          ) : (
            <>
              {/* The whole exchange for assistive tech, at once; the played
                  version below is for the eye. */}
              <ol className="sr-only">
                {script.map((item, index) => (
                  <li key={index}>{plain(item, t.professor.mastery)}</li>
                ))}
              </ol>
              <div className="l7-turns" aria-hidden="true">
                {script.map((item, index) =>
                  index > at ? null : (
                    <ScriptItem
                      key={`${run}-${index}`}
                      item={item}
                      playing={index === at && !done}
                      typed={typed}
                      phase={index === at && !done ? phase : 2}
                      mastery={t.professor.mastery}
                    />
                  ),
                )}
              </div>
            </>
          )}
        </div>

        <form className="l7-composer" onSubmit={submit} data-ready={done || live ? 'true' : 'false'}>
          <label htmlFor="l7-ask" className="sr-only">
            {copy.label}
          </label>
          <input
            id="l7-ask"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={copy.placeholder}
            autoComplete="off"
            enterKeyHint="send"
            className="l7-composer-input"
          />
          <button type="submit" className="l7-composer-send" disabled={!question.trim() || live?.status === 'streaming'}>
            {copy.submit}
          </button>
        </form>
      </div>

      <div className="l7-demo-foot">
        <p className="font-mono text-xs text-ink-500">{copy.staged}</p>
        {(done || live) && !still && (
          <button type="button" onClick={replay} className="l7-text-button">
            {copy.replay}
          </button>
        )}
      </div>
    </div>
  );
}

type MasteryCopy = { mastered: (concept: string) => string; learning: (concept: string) => string };

function plain(item: Item, mastery: MasteryCopy): string {
  if (item.kind === 'quiz') return `${item.question} ${item.options[item.pick]} — ${item.verdict}`;
  if (item.kind === 'mastery')
    return item.items.map(([step, concept]) => (step === 'mastered' ? mastery.mastered(concept!) : mastery.learning(concept!))).join('. ');
  return item.text;
}

function YouLine({ text }: { text: string }) {
  const { t } = useI18n();
  return (
    <div className="l7-in border-l-2 border-line pl-4">
      <span className="font-mono text-xs text-ink-400">{t.professor.you}</span>
      <p className="mt-1 text-base text-ink-700">{text}</p>
    </div>
  );
}

function MinoTurn({ children }: { children: React.ReactNode }) {
  return (
    <div className="l7-in">
      <div className="flex items-center gap-2">
        <Mino state="teaching" size="xs" />
        <span className="font-mono text-xs text-signal">Mino</span>
      </div>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function ScriptItem({
  item,
  playing,
  typed,
  phase,
  mastery,
}: {
  item: Item;
  playing: boolean;
  typed: number;
  phase: number;
  mastery: MasteryCopy;
}) {
  if (item.kind === 'you') return <YouLine text={item.text} />;
  if (item.kind === 'mino') {
    const text = playing ? item.text.slice(0, typed) : item.text;
    return (
      <MinoTurn>
        <p className="l7-reading">
          {text}
          {playing && typed < item.text.length && <span className="l7-caret" />}
        </p>
      </MinoTurn>
    );
  }
  if (item.kind === 'strategy') {
    return (
      <p className="l7-in l7-strategy">
        <span aria-hidden="true">↻</span> {item.text}
      </p>
    );
  }
  if (item.kind === 'mastery') {
    return (
      <div className="l7-in space-y-1">
        {item.items.map(([step, concept]) => (
          <p key={concept} className="flex items-baseline gap-2 text-sm text-ink-700">
            <span className={step === 'mastered' ? 'text-positive' : 'text-signal'}>{step === 'mastered' ? '●' : '◐'}</span>
            {step === 'mastered' ? mastery.mastered(concept!) : mastery.learning(concept!)}
          </p>
        ))}
      </div>
    );
  }
  const right = item.pick === item.answer;
  return (
    <div className="l7-in l7-quiz">
      <p className="font-display text-lg text-ink-900">{item.question}</p>
      <ul className="mt-4 space-y-2">
        {item.options.map((option, index) => {
          const chosen = phase >= 1 && index === item.pick;
          const graded = phase >= 2;
          const tone =
            graded && index === item.answer && right
              ? 'is-right'
              : graded && chosen && !right
                ? 'is-wrong'
                : chosen
                  ? 'is-chosen'
                  : graded
                    ? 'is-other'
                    : '';
          return (
            <li key={option} className={`l7-option ${tone}`}>
              <span>{option}</span>
              {graded && index === item.answer && right && (
                <svg viewBox="0 0 16 16" className="l7-check h-4 w-4 text-positive">
                  <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" pathLength={1} />
                </svg>
              )}
            </li>
          );
        })}
      </ul>
      {phase >= 2 && (
        <p className={`l7-in mt-4 border-l-2 pl-4 text-sm ${right ? 'border-positive text-positive' : 'border-critical text-critical'}`}>
          {item.verdict}
        </p>
      )}
    </div>
  );
}
