'use client';

/**
 * Modo TDAH, the pieces every screen of it shares.
 *
 * - `FocoGuide`  — Mino as a focus guide: small, still, four states. No
 *   bubbles, no idle animation beyond a rare blink (none under reduced
 *   motion, which the figure already honours).
 * - `FocoTopLine` — the only chrome a session has: the step, a thin progress
 *   line, the time left, and "Pausar" / "Sair", always reachable.
 * - `taskLabel` / `reasonLabel` — the next activity said in the reader's
 *   language, from the server's numbers (never its English sentence).
 */

import { Mino, type MinoState } from '@/components/mino/Mino';
import type { FocusSession, NextActivity } from '@/lib/api';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

export type GuideState = 'idle' | 'focused' | 'thinking' | 'happy';

const POSE: Record<GuideState, MinoState> = {
  idle: 'idle',
  focused: 'focused',
  thinking: 'thinking',
  happy: 'happy',
};

export function FocoGuide({
  state,
  size = 'sm',
  className = '',
}: {
  state: GuideState;
  size?: 'xs' | 'sm' | 'md';
  className?: string;
}) {
  return (
    <span aria-hidden="true" data-foco-guide={state} className={className}>
      <Mino state={POSE[state]} size={size} />
    </span>
  );
}

export function taskLabel(activity: NextActivity, t: Dict): string {
  if (activity.kind === 'review') return t.foco.reviewTask(activity.due_count);
  if (activity.kind === 'learn') return activity.concept || activity.title;
  return t.foco.startTask;
}

export function sessionTaskLabel(session: FocusSession, t: Dict): string {
  if (session.kind === 'review') return t.foco.reviewTask(session.steps_total);
  return session.concept || session.title;
}

export function reasonLabel(activity: NextActivity, t: Dict): string {
  switch (activity.reason_code) {
    case 'overdue':
      return t.foco.reason.overdue(activity.overdue_count);
    case 'due':
      return t.foco.reason.due(activity.due_count);
    case 'continue':
      return t.foco.reason.continue(activity.title || activity.concept);
    default:
      return t.foco.reason.start;
  }
}

/** Whole minutes left, rounded up: "~3 min", never a ticking clock. */
export function minutesLeft(secondsLeft: number): number {
  return Math.ceil(secondsLeft / 60);
}

export function FocoTopLine({
  step,
  done,
  total,
  minutes,
  onPause,
  onExit,
  busy = false,
}: {
  /** The step on screen ("Passo 2/4"). */
  step: number;
  /** Steps finished — what the progress line shows. */
  done: number;
  total: number;
  minutes: number;
  onPause?: () => void;
  onExit: () => void;
  busy?: boolean;
}) {
  const t = useT();
  const progress = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <header
      className="sticky top-0 z-20 border-b border-line bg-surface pt-[env(safe-area-inset-top)]"
      data-foco-topline
    >
      <div className="mx-auto flex max-w-reading items-center gap-3 px-5 py-2.5">
        <span className="font-mono text-xs text-ink-700" data-foco-step>
          {t.foco.stepOf(step, total)}
        </span>
        <span className="text-xs text-ink-500" data-foco-time>
          {t.foco.minutesLeft(minutes)}
        </span>
        <span className="ml-auto flex items-center">
          {onPause && (
            <button
              type="button"
              onClick={onPause}
              disabled={busy}
              className="min-h-11 px-3 text-sm text-ink-600 transition-colors duration-fast hover:text-ink-900 disabled:opacity-50"
              data-foco-pause
            >
              {t.foco.pause}
            </button>
          )}
          <button
            type="button"
            onClick={onExit}
            disabled={busy}
            className="min-h-11 pl-3 text-sm text-ink-600 transition-colors duration-fast hover:text-ink-900 disabled:opacity-50"
            data-foco-exit
          >
            {t.foco.exit}
          </button>
        </span>
      </div>
      <div
        className="h-0.5 bg-line"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-label={t.foco.stepOf(step, total)}
      >
        <div
          className="h-full bg-primary motion-safe:transition-[width] motion-safe:duration-state"
          style={{ width: `${progress}%` }}
        />
      </div>
    </header>
  );
}
