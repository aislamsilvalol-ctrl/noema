/**
 * A deliberately small event set, not "track everything" (brief item 57).
 * Scoped to the public conversion funnel this task actually covers --
 * landing → signup. Deeper in-app events (learning_path_created,
 * subscription_started) would mean instrumenting the teaching/billing code
 * this task's own scope explicitly excludes ("PRESERVE NOEMA... salvo se
 * algo público depender diretamente deles"); left as a real follow-up, not
 * done here.
 *
 * A no-op everywhere Plausible isn't loaded (local dev, preview/staging,
 * or a browser blocking the script) -- `window.plausible` is only ever
 * defined by the script tag in `layout.tsx`, itself production-only.
 */

type AnalyticsEvent = 'cta_clicked' | 'signup_started' | 'signup_completed';

declare global {
  interface Window {
    plausible?: (event: string, options?: { props?: Record<string, string> }) => void;
  }
}

export function track(event: AnalyticsEvent, props?: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  window.plausible?.(event, props ? { props } : undefined);
}
