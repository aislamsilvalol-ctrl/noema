/**
 * Who may open which route, decided before anything paints.
 *
 * The middleware (`src/middleware.ts`) runs this on the edge; it is a pure
 * function so the decision can be tested without Next's request objects.
 * The session cookie's name comes from the API (`noema/api/v1/deps.py`,
 * `SESSION_COOKIE`); the web proxies `/api/v1/*` to the API, so the cookie
 * is first-party and the edge can see it. Its presence is all that is
 * checked here — validity is the API's call, and a stale cookie still ends
 * in the pages' own 401 handling.
 */

export const SESSION_COOKIE = 'noema_session';

/**
 * Every route that needs an account. `/notebooks` and `/learn` cover their
 * subtrees. Mirrored, as literals, in `middleware.ts`'s `config.matcher`,
 * which Next requires to be static — the test keeps the two lists equal.
 */
export const GUARDED_PREFIXES = [
  '/today',
  '/chat',
  '/review',
  '/library',
  '/progress',
  '/graph',
  '/mistakes',
  '/goals',
  '/explain',
  '/socratic',
  '/notebooks',
  '/learn',
  '/settings',
  '/admin',
] as const;

export function isGuardedPath(pathname: string): boolean {
  return GUARDED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Where to send this request instead, or `null` to let it through. Demo
 * mode has no session cookie at all — the demo route handler answers every
 * request as a signed-in user — so the guard stands aside there.
 */
export function guardRedirect({
  pathname,
  search = '',
  hasSession,
  demo = false,
}: {
  pathname: string;
  search?: string;
  hasSession: boolean;
  demo?: boolean;
}): string | null {
  if (demo || hasSession || !isGuardedPath(pathname)) return null;
  return `/login?next=${encodeURIComponent(pathname + search)}`;
}

/**
 * The `?next=` a login may honour: a path on this origin, nothing else.
 * `//host` and `/\host` are how a browser spells "another site" in a
 * relative URL, so both are refused along with anything that is not a path.
 */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null;
  if (raw === '/login' || raw.startsWith('/login?')) return null;
  return raw;
}
