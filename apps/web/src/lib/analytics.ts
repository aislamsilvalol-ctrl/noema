/**
 * A deliberately small event set, not "track everything": the launch funnel
 * from the landing to the first review. Each marks a step where a learner
 * got value (a lesson started, a review session), never page views, and
 * carries no personal data and no lesson content.
 *
 * A no-op everywhere Plausible isn't loaded (local dev, preview/staging,
 * or a browser blocking the script) -- `window.plausible` is only ever
 * defined by the script tag in `layout.tsx`, itself production-only.
 */

type AnalyticsEvent =
  | 'cta_clicked'
  | 'signup_started'
  | 'signup_completed'
  | 'onboarding_completed'
  | 'lesson_started'
  | 'review_session';

declare global {
  interface Window {
    plausible?: (event: string, options?: { props?: Record<string, string> }) => void;
  }
}

export function track(event: AnalyticsEvent, props?: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  window.plausible?.(event, props ? { props } : undefined);
}
