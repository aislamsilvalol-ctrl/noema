/**
 * A deliberately small event set, not "track everything": the launch funnel
 * from the landing to a successful learning session. Each marks a step where
 * a learner moved forward, never page views, and carries no personal data and
 * no lesson content -- props are short enums ('quiz', 'true'), never a
 * concept, a question or an answer. The full table is in `docs/analytics.md`.
 *
 * These are the top of the funnel and attribution. Activation, sessions and
 * revenue are counted from the database (`GET /admin/launch`), so a browser
 * that blocks this script changes nothing that matters.
 *
 * A no-op everywhere Plausible isn't loaded (local dev, preview/staging,
 * or a browser blocking the script) -- `window.plausible` is only ever
 * defined by the script tag in `layout.tsx`, itself production-only.
 */

export type AnalyticsEvent =
  | 'cta_clicked'
  | 'signup_started'
  | 'signup_completed'
  | 'onboarding_completed'
  | 'learning_goal_created'
  | 'lesson_started'
  | 'learning_session_completed'
  | 'exercise_answered'
  | 'mastery_updated'
  | 'review_session'
  | 'adhd_mode_enabled'
  | 'pricing_viewed'
  | 'checkout_started'
  | 'subscription_started';

declare global {
  interface Window {
    plausible?: (event: string, options?: { props?: Record<string, string> }) => void;
  }
}

export function track(event: AnalyticsEvent, props?: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  window.plausible?.(event, props ? { props } : undefined);
}

/**
 * Once per browser tab session, for events a page would otherwise send on
 * every visit or refresh (entering Modo TDAH, coming back from checkout).
 */
export function trackOnce(event: AnalyticsEvent, props?: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  const key = `noema.tracked.${event}`;
  try {
    if (window.sessionStorage.getItem(key)) return;
    window.sessionStorage.setItem(key, '1');
  } catch {
    // Storage blocked: send it; a duplicate is better than nothing.
  }
  track(event, props);
}

// ── Signup attribution ───────────────────────────────────────────────────────

export const ATTRIBUTION_KEY = 'noema.attribution';
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'] as const;
export type Attribution = Partial<Record<(typeof UTM_KEYS)[number], string>>;

/**
 * Keep the UTM tags of the first visit that carried any. First touch wins: a
 * later visit with other tags does not overwrite it. Only those four keys,
 * each cut to 100 characters; they are campaign names, not identities.
 */
export function captureAttribution(search: string = typeof window === 'undefined' ? '' : window.location.search): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(search);
  const found: Attribution = {};
  for (const key of UTM_KEYS) {
    const value = params.get(key)?.trim();
    if (value) found[key] = value.slice(0, 100);
  }
  if (Object.keys(found).length === 0) return;
  try {
    if (window.localStorage.getItem(ATTRIBUTION_KEY)) return;
    window.localStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(found));
  } catch {
    // Storage blocked: this signup arrives unattributed.
  }
}

/** What `captureAttribution` kept, or null. Sent once, with the signup. */
export function readAttribution(): Attribution | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(ATTRIBUTION_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    const kept: Attribution = {};
    for (const key of UTM_KEYS) {
      const value = (parsed as Record<string, unknown>)[key];
      if (typeof value === 'string' && value) kept[key] = value.slice(0, 100);
    }
    return Object.keys(kept).length > 0 ? kept : null;
  } catch {
    return null;
  }
}
