/**
 * What Home decides, as pure functions: which place the hero stands in, how
 * Mino feels, where the learner is on the path, and the one thing worth doing
 * now. The page composes endpoints; these read them. Nothing here invents a
 * number — a decision with no evidence behind it returns null and the page
 * draws less.
 */

import type { Journey, JourneyConcept, Mastery, NextActivity } from '@/lib/api';

export type Plate = 'horizon' | 'trail' | 'valley' | 'mino' | 'terraces' | 'routes' | 'bleach';
export type DayPart = 'morning' | 'afternoon' | 'evening' | 'night';

export function dayPart(hour: number): DayPart {
  if (hour >= 5 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 18) return 'afternoon';
  if (hour >= 18 && hour < 23) return 'evening';
  return 'night';
}

/**
 * The hero's place follows the learner's state, not chance: an open field
 * on the first day, the path ahead while a journey runs, the valley already
 * walked when reviewing comes first, Mino close when something was mastered
 * today. See docs/dashboard-redesign.md, "Landscape strategy".
 */
export function heroPlate({
  firstDay,
  journey,
  next,
}: {
  firstDay: boolean;
  journey: Journey | null;
  next: NextActivity | null;
}): Plate {
  if (firstDay) return 'horizon';
  if ((journey?.momentum?.mastered_today ?? 0) > 0) return 'mino';
  if (next?.kind === 'review' && next.reason_code === 'overdue') return 'valley';
  if (journey) return 'trail';
  return 'terraces';
}

/**
 * Tiles: the same subject always lands in the same place. Mino close up is
 * kept for the hero's celebration, so tiles walk the other plates.
 */
const TILE_PLATES: Plate[] = ['routes', 'terraces', 'valley', 'trail', 'horizon'];
export function plateFor(key: string): Plate {
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) | 0;
  return TILE_PLATES[Math.abs(hash) % TILE_PLATES.length] ?? 'routes';
}

export interface Place {
  /** Module title, when it says more than the subject. */
  module: string | null;
  /** The lesson being taught now. */
  lesson: string | null;
  /** The concept the lesson is on. */
  concept: string | null;
  /** Lessons behind (done or skipped) and in all. */
  done: number;
  total: number;
  /** Concepts of the journey and how many are mastered. */
  mastered: number;
  concepts: number;
}

/** Where the learner stands on a journey, said once (no title repeated). */
export function placeIn(journey: Journey): Place {
  const plan = journey.plan ?? [];
  const unit = plan[journey.current?.module ?? 0];
  const lesson = unit?.lessons[journey.current?.lesson ?? 0];
  const seen = new Set([journey.subject.trim().toLowerCase()]);
  const fresh = (value: string | undefined | null): string | null => {
    const key = (value ?? '').trim().toLowerCase();
    if (!key || seen.has(key)) return null;
    seen.add(key);
    return (value ?? '').trim();
  };
  const unitTitle = fresh(unit?.title);
  const lessonTitle = fresh(lesson?.title);
  const concept = fresh(journey.current?.concept);
  const total = plan.reduce((sum, m) => sum + m.lessons.length, 0);
  const done = plan.reduce(
    (sum, m) => sum + m.lessons.filter((l) => l.status === 'done' || l.status === 'skipped').length,
    0,
  );
  const concepts = journey.concepts ?? [];
  return {
    module: unitTitle,
    lesson: lessonTitle,
    concept,
    done,
    total,
    mastered: concepts.filter((c) => c.state === 'mastered').length,
    concepts: concepts.length,
  };
}

// A weak concept is named only when the number can be trusted: enough
// observations, and low enough to be worth a lesson.
export const WEAK_MIN_EVIDENCE = 4;
export const WEAK_BELOW = 60;
const SHAKY_STAGES = new Set(['uncertain', 'needs_review']);

export interface Weak {
  name: string;
  /** The graph's mastery %, when it has enough evidence behind it. */
  score: number | null;
}

/**
 * The concept worth a second look: the graph's weakest when its number can
 * be trusted, otherwise the stage the lesson itself found shaky (a learner
 * who only studies with Mino has no cards behind a mastery number, but the
 * lesson knows which idea went wrong twice).
 */
export function weakConcept(mastery: Mastery[], journey: Journey | null): Weak | null {
  const weakest = [...mastery]
    .filter((m) => m.components.effective_observations >= WEAK_MIN_EVIDENCE && m.mastery < WEAK_BELOW)
    .sort((a, b) => a.mastery - b.mastery)[0];
  if (weakest) return { name: weakest.concept_name, score: Math.round(weakest.mastery) };
  const shaky: JourneyConcept | undefined = (journey?.concepts ?? [])
    .filter((c) => SHAKY_STAGES.has(c.state))
    .sort((a, b) => b.evidence - a.evidence)[0];
  return shaky ? { name: shaky.name, score: null } : null;
}

export type Recommendation =
  | { kind: 'review'; due: number; overdue: number; minutes: number }
  | { kind: 'weak'; name: string; score: number | null }
  | { kind: 'continue'; concept: string; minutes: number }
  | { kind: 'start' };

/**
 * The one thing worth doing now, beside Continue. The engine's answer
 * (`/me/next-activity`) leads; when it only says "continue" — which the hero
 * already offers — the next most useful thing is a concept that went wrong,
 * then reviews due, then the engine's continue (a focused 10 minutes on it).
 */
export function recommend({
  next,
  weak,
  due,
  hasLesson,
}: {
  next: NextActivity | null;
  weak: Weak | null;
  due: number;
  hasLesson: boolean;
}): Recommendation | null {
  if (next?.kind === 'review' && next.due_count > 0) {
    return { kind: 'review', due: next.due_count, overdue: next.overdue_count, minutes: next.minutes_estimate };
  }
  if (weak) return { kind: 'weak', name: weak.name, score: weak.score };
  if (due > 0) return { kind: 'review', due, overdue: 0, minutes: Math.max(1, Math.round(due * 0.5)) };
  if (next?.kind === 'learn') return { kind: 'continue', concept: next.concept || next.title, minutes: next.minutes_estimate };
  if (!hasLesson) return { kind: 'start' };
  return null;
}

/** A first name for the greeting; nothing when the account has none. */
export function firstName(displayName: string | null | undefined): string {
  const name = (displayName ?? '').trim().split(/\s+/)[0] ?? '';
  // An e-mail-like display name is not a name to greet.
  return name.includes('@') ? '' : name;
}

/**
 * The one sentence Mino remembers about where the journey stopped, from the
 * newest fold of its memory: the step agreed next, else what was last taught.
 */
export function remembered(journey: Journey | null): { next: string } | { last: string } | null {
  const latest = journey?.memory?.[journey.memory.length - 1];
  const summary = (latest?.summary ?? {}) as Record<string, unknown>;
  const next = typeof summary.next_step === 'string' ? summary.next_step.trim() : '';
  if (next) return { next };
  const last = typeof summary.last_taught === 'string' ? summary.last_taught.trim() : '';
  return last ? { last } : null;
}
