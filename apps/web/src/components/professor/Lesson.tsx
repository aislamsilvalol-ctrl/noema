'use client';

/**
 * The Professor as a learning session, not a chat log.
 *
 * Shared by both Professor screens (`/chat` and the notebook one):
 *
 * - `LessonHeader`  — where the lesson is (subject, current concept) and the
 *   journey's course strip when there is one.
 * - `LearnerTurn`   — the learner's line, small and quiet: the prompt for the
 *   block below it, not a speech bubble with equal billing.
 * - `LessonBlock`   — one of Mino's replies as *segments*: prose rendered as
 *   elements (never HTML), and beside it the structured pieces the server
 *   sent as events — a quiz, a check, an iceberg, the cards it wrote, a
 *   checkpoint paper, a note that older context was folded into memory.
 * - `Composer`      — the field, one primary Send, Stop while streaming, and
 *   contextual actions above it that depend on the last move, not the same
 *   four buttons after every reply.
 *
 * Nothing here decides what to send or how; `useLesson` and the pages do.
 */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Mino, type MinoState } from '@/components/mino/Mino';
import { CurriculumStrip } from '@/components/professor/CurriculumStrip';
import { ExamView } from '@/components/professor/ExamView';
import { FlashcardDeck } from '@/components/professor/FlashcardDeck';
import { LearningBlock } from '@/components/professor/LearningBlocks';
import type { Segment, Turn } from '@/components/professor/useLesson';
import { Button } from '@/components/ui/Button';
import type { AssessmentView, Journey } from '@/lib/api';
import { Markdown } from '@/lib/markdown';
import { useI18n, useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

export interface LessonPlace {
  subject?: string | null;
  topic?: string | null;
  concept?: string | null;
}

export function minoStateFor({
  streaming,
  status,
  error,
  turns,
}: {
  streaming: boolean;
  status: string | null;
  error: string | null;
  turns: number;
}): MinoState {
  if (error) return 'confused';
  if (streaming && status) return 'thinking';
  if (streaming) return 'teaching';
  if (turns === 0) return 'curious';
  return 'idle';
}

export function LessonHeader({
  title,
  subtitle,
  place,
  journey,
  mino,
  aside,
}: {
  title: string;
  subtitle?: string | null;
  place?: LessonPlace | null;
  journey?: Journey | null;
  mino: MinoState;
  aside?: ReactNode;
}) {
  const t = useT();
  const subject = journey?.subject || place?.subject || place?.topic || '';
  const concept = journey?.current.concept || place?.concept || '';
  return (
    <header className="flex items-start gap-4" data-mino-state={mino}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h1 className="font-display text-2xl text-ink-900">
            {subject ? t.professor.learning(subject) : title}
          </h1>
          {aside}
        </div>
        {journey ? (
          <CurriculumStrip journey={journey} />
        ) : (
          (concept || subtitle) && (
            <p className="mt-1 text-sm text-ink-500">
              {concept && concept !== subject ? t.today.onConcept(concept) : subtitle}
            </p>
          )
        )}
      </div>
    </header>
  );
}

export function LearnerTurn({ content }: { content: string }) {
  const t = useT();
  return (
    <div className="border-l-2 border-line pl-4">
      <span className="text-xs uppercase tracking-wide text-ink-400">{t.professor.you}</span>
      <p className="mt-1 whitespace-pre-wrap text-base text-ink-700">{content}</p>
    </div>
  );
}

export function LessonBlock({
  turn,
  streaming,
  status,
  children,
  onQuizAnswered,
  onRecall,
  onSubmitAssessment,
}: {
  turn: Turn;
  /** This block is the one being written right now. */
  streaming: boolean;
  status: string | null;
  /** Per-block actions (save to notes, created-items cards). */
  children?: ReactNode;
  onQuizAnswered?: (detail: {
    question: string;
    chosen: string;
    concept: string;
    correct: boolean;
  }) => void;
  onRecall?: (cardId: string, rating: 1 | 2 | 3 | 4) => void;
  onSubmitAssessment?: (id: string, responses: unknown[]) => Promise<unknown>;
}) {
  const t = useT();
  const hasContent = turn.segments.length > 0;
  return (
    <div className="max-w-reading" data-move={turn.move}>
      {/* The same character as the live figure: one Mino, two sizes. */}
      <div className="flex items-center gap-2">
        <Mino state={streaming ? 'teaching' : 'idle'} size="xs" />
        <span className="text-xs uppercase tracking-wide text-signal">Mino</span>
      </div>
      {hasContent ? (
        <div className="relative mt-2 space-y-3">
          {turn.segments.map((segment, index) => (
            <SegmentView
              key={index}
              segment={segment}
              streaming={streaming && index === turn.segments.length - 1}
              onQuizAnswered={onQuizAnswered}
              onRecall={onRecall}
              onSubmitAssessment={onSubmitAssessment}
            />
          ))}
        </div>
      ) : (
        streaming &&
        status && (
          <p className="mt-2 text-sm text-ink-400" aria-live="polite">
            {status}
          </p>
        )
      )}
      {children}
      {!hasContent && !streaming && !status && (
        <p className="mt-2 text-sm text-ink-400">{t.professor.nothingCameBack}</p>
      )}
    </div>
  );
}

function SegmentView({
  segment,
  streaming,
  onQuizAnswered,
  onRecall,
  onSubmitAssessment,
}: {
  segment: Segment;
  streaming: boolean;
  onQuizAnswered?: (detail: {
    question: string;
    chosen: string;
    concept: string;
    correct: boolean;
  }) => void;
  onRecall?: (cardId: string, rating: 1 | 2 | 3 | 4) => void;
  onSubmitAssessment?: (id: string, responses: unknown[]) => Promise<unknown>;
}) {
  const t = useT();
  switch (segment.kind) {
    case 'text':
      return (
        <div className="relative">
          <Markdown
            text={segment.text}
            renderTool={(tool, data, key) => (
              // A fence in stored prose (pre-V3 turns) still draws as a block.
              <LearningBlock key={key} tool={tool} data={data} />
            )}
          />
          {streaming && (
            <span
              aria-hidden="true"
              className="ml-0.5 inline-block h-4 w-px animate-pulse bg-signal align-middle"
            />
          )}
        </div>
      );
    case 'block':
      return (
        <LearningBlock
          tool={segment.tool}
          data={segment.data}
          onEvent={(event, detail) => {
            if ((event === 'correct' || event === 'wrong') && detail && onQuizAnswered) {
              onQuizAnswered({
                question: String(detail.question ?? ''),
                chosen: String(detail.chosen ?? ''),
                concept: String(detail.concept ?? ''),
                correct: event === 'correct',
              });
            }
          }}
        />
      );
    case 'cards':
      return <FlashcardDeck cards={segment.cards} onRecall={(id, rating) => onRecall?.(id, rating)} />;
    case 'checkpoint':
      return (
        <ExamView
          assessment={segment.assessment as AssessmentView}
          onSubmit={(responses) =>
            onSubmitAssessment
              ? onSubmitAssessment(segment.assessment.id, responses)
              : Promise.resolve()
          }
        />
      );
    case 'memory':
      return (
        <p className="text-xs text-ink-400" data-lesson-memory>
          {t.professor.memoryFolded(segment.compacted)}
        </p>
      );
    default:
      return null;
  }
}

/**
 * The actions that make sense after the last move — not the same four after
 * every reply. None while a question waits for its answer: the answer is the
 * action.
 */
export function actionsFor(
  lastMove: string | null,
  awaitingCheck: boolean,
  t: Dict,
): { label: string; text: string }[] | null {
  const a = t.professor.actions;
  if (awaitingCheck) return null;
  switch (lastMove) {
    case null:
      return null;
    case 'question':
    case 'quiz':
    case 'practice':
    case 'exam':
      return null;
    case 'correct':
      return [
        { label: a.gotIt, text: a.gotIt },
        { label: a.stillNot, text: a.stillNot },
        { label: a.example, text: a.example },
      ];
    case 'motivate':
    case 'flashcard':
      return [{ label: a.continueOn, text: a.continueOn }];
    case 'summarize':
      return [
        { label: a.testMe, text: a.testMe },
        { label: a.continueOn, text: a.continueOn },
      ];
    default:
      return [
        { label: a.testMe, text: a.testMe },
        { label: a.dontGet, text: a.dontGet },
        { label: a.knowThis, text: a.knowThis },
        { label: a.deeper, text: a.deeper },
      ];
  }
}

/** The largest text attachment folded into a message, in characters. */
const ATTACHMENT_MAX = 6000;
const ATTACHMENT_TYPES =
  '.txt,.md,.markdown,.csv,.json,text/plain,text/markdown,text/csv,application/json';

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function recognitionFactory(): (() => Recognition) | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => Recognition;
    webkitSpeechRecognition?: new () => Recognition;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? () => new Ctor() : null;
}

/**
 * On a phone the software keyboard takes the lower half of the viewport. While
 * the composer has focus and the visual viewport has shrunk, the root carries
 * `data-keyboard="open"`: the tab bar hides and the composer sits flush at the
 * bottom (globals.css), so the field is never behind the keyboard.
 */
function useKeyboardChoreography(active: boolean) {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const viewport = window.visualViewport;
    const root = document.documentElement;
    if (!viewport || !active) {
      delete root.dataset.keyboard;
      return;
    }
    const update = () => {
      const shrunk = window.innerHeight - viewport.height > 150;
      if (shrunk) root.dataset.keyboard = 'open';
      else delete root.dataset.keyboard;
    };
    update();
    viewport.addEventListener('resize', update);
    return () => {
      viewport.removeEventListener('resize', update);
      delete root.dataset.keyboard;
    };
  }, [active]);
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  streaming,
  placeholder,
  quickActions,
  notice,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onStop: () => void;
  streaming: boolean;
  placeholder: string;
  /** Rendered above the field; `null` hides the row. */
  quickActions?: { label: string; onClick: () => void }[] | null;
  notice?: ReactNode;
}) {
  const t = useT();
  const { locale } = useI18n();
  const [focused, setFocused] = useState(false);
  const [listening, setListening] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [canListen, setCanListen] = useState(false);
  useEffect(() => setCanListen(recognitionFactory() !== null), []);
  useKeyboardChoreography(focused);

  function toggleListening() {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const make = recognitionFactory();
    if (!make) return;
    const rec = make();
    rec.lang = ({ pt: 'pt-BR', en: 'en-US', es: 'es-ES' } as Record<string, string>)[locale] ?? 'pt-BR';
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (event) => {
      const heard = Array.from(event.results, (r) => r[0]?.transcript ?? '')
        .join(' ')
        .trim();
      if (heard) onChange(value ? value + ' ' + heard : heard);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognition.current = rec;
    setListening(true);
    rec.start();
  }

  async function attach(file: File | undefined) {
    if (!file) return;
    setAttachError(null);
    const text = await file.text();
    if (!text.trim()) return;
    if (text.length > ATTACHMENT_MAX) {
      setAttachError(t.professor.composer.attachTooLarge(Math.round(ATTACHMENT_MAX / 1000)));
      return;
    }
    // Folded into the message as quoted material, labelled, so Mino reads it
    // as something the learner brought — never as instructions.
    const block = '\n\n<ANEXO nome="' + file.name + '">\n' + text.trim() + '\n</ANEXO>';
    onChange((value.trimEnd() + block).trim());
  }

  return (
    // Sits on the mobile tab bar (43 px, see Shell) rather than floating above
    // a strip of lesson text; flush with the bottom once the bar is gone, and
    // while the keyboard is open (see useKeyboardChoreography).
    <div className="noema-composer sticky bottom-11 mt-8 border-t border-line bg-surface pt-4 md:bottom-0">
      {quickActions && quickActions.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {quickActions.map((action) => (
            <Button key={action.label} size="sm" variant="secondary" onClick={action.onClick}>
              {action.label}
            </Button>
          ))}
        </div>
      )}

      {notice}

      {attachError && (
        <p role="alert" className="mb-2 text-xs text-critical">
          {attachError}
        </p>
      )}

      <form onSubmit={onSubmit}>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              onSubmit(event);
            }
          }}
          rows={2}
          placeholder={placeholder}
          className="w-full resize-none rounded-md border border-line bg-raised px-3 py-2 text-base text-ink-900 outline-none transition-colors duration-fast focus:border-signal placeholder:text-ink-400"
        />
        <div className="mt-2 flex items-center justify-between gap-3 pb-2">
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-ink-400 sm:inline">{t.common.enterToSend}</span>
            {canListen && (
              <button
                type="button"
                onClick={toggleListening}
                aria-pressed={listening}
                aria-label={listening ? t.professor.composer.stopListening : t.professor.composer.speak}
                className={
                  'text-xs transition-colors duration-fast ' +
                  (listening ? 'text-signal' : 'text-ink-500 hover:text-ink-900')
                }
              >
                {listening ? t.professor.composer.listening : t.professor.composer.speak}
              </button>
            )}
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
            >
              {t.professor.composer.attach}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept={ATTACHMENT_TYPES}
              className="hidden"
              aria-label={t.professor.composer.attach}
              onChange={(event) => {
                void attach(event.target.files?.[0]);
                event.target.value = '';
              }}
            />
          </div>
          {streaming ? (
            <Button variant="ghost" size="sm" onClick={onStop}>
              {t.common.stop}
            </Button>
          ) : (
            <Button type="submit" variant="primary">
              {t.common.send}
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
