'use client';

/**
 * The Professor as a learning session, not a chat log.
 *
 * Four pieces, used by both Professor screens (`/chat` and the notebook one)
 * so they look and behave the same while keeping their own request logic:
 *
 * - `LessonHeader`  — Mino, and where the lesson is: subject, current concept.
 *   Mino's state follows the stream: thinking before the first token,
 *   teaching while tokens arrive, confused on an error, idle between turns.
 * - `LearnerTurn`   — the learner's line, small and quiet. It is the prompt
 *   for the block below it, not a speech bubble with equal billing.
 * - `LessonBlock`   — one of Noema's replies as lesson prose (markdown
 *   rendered as elements, never HTML), with the streaming caret and the
 *   "thinking…" status while nothing has arrived yet.
 * - `Composer`      — the field, one primary Send, Stop while streaming, and
 *   the quick actions above it: Test me · Go deeper · Summarize · Explain
 *   differently. The actions send text, exactly as typing it would.
 *
 * Nothing here decides what to send or how; the pages keep that.
 */

import type { FormEvent, ReactNode } from 'react';
import { Mino, type MinoState } from '@/components/mino/Mino';
import { useMinoOptional } from '@/components/mino/MinoController';
import { LearningBlock, type LearningEvent } from '@/components/professor/LearningBlocks';
import { Button } from '@/components/ui/Button';
import { Markdown } from '@/lib/markdown';
import { useT } from '@/lib/i18n';

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
  mino,
  aside,
}: {
  title: string;
  subtitle?: string | null;
  place?: LessonPlace | null;
  mino: MinoState;
  aside?: ReactNode;
}) {
  const t = useT();
  const subject = place?.subject || place?.topic || '';
  const concept = place?.concept && place.concept !== subject ? place.concept : '';
  return (
    <header className="flex items-start gap-4" data-mino-state={mino}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h1 className="font-display text-2xl text-ink-900">
            {subject ? t.professor.learning(subject) : title}
          </h1>
          {aside}
        </div>
        {(concept || subtitle) && (
          <p className="mt-1 text-sm text-ink-500">
            {concept ? t.today.onConcept(concept) : subtitle}
          </p>
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
  content,
  streaming,
  status,
  children,
  onLearningEvent,
}: {
  content: string;
  /** This block is the one being written right now. */
  streaming: boolean;
  status: string | null;
  /** Per-block actions (save to notes, created-items cards). */
  children?: ReactNode;
  /** A learning block inside the reply was answered or revealed. */
  onLearningEvent?: (event: LearningEvent, detail?: Record<string, unknown>) => void;
}) {
  const shared = useMinoOptional();
  return (
    <div className="max-w-reading">
      {/* The same character as the live figure: one Mino, two sizes. */}
      <div className="flex items-center gap-2">
        <Mino state={streaming ? 'teaching' : 'idle'} size="xs" />
        <span className="text-xs uppercase tracking-wide text-signal">Mino</span>
      </div>
      {content ? (
        <div className="relative mt-2">
          <Markdown
            text={content}
            renderTool={(tool, data, key) => (
              <LearningBlock
                key={key}
                tool={tool}
                data={data}
                onEvent={(event, detail) => {
                  if (event === 'correct' || event === 'wrong') shared?.react(event);
                  onLearningEvent?.(event, detail);
                }}
              />
            )}
          />
          {streaming && (
            <span
              aria-hidden="true"
              className="ml-0.5 inline-block h-4 w-px animate-pulse bg-signal align-middle"
            />
          )}
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
    </div>
  );
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
  return (
    // Sits on the mobile tab bar (43 px, see Shell) rather than floating above
    // a strip of lesson text; flush with the bottom once the bar is gone.
    <div className="sticky bottom-11 mt-8 border-t border-line bg-surface pt-4 md:bottom-0">
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

      <form onSubmit={onSubmit}>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
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
        <div className="mt-2 flex items-center justify-between pb-2">
          <span className="text-xs text-ink-400">{t.common.enterToSend}</span>
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
