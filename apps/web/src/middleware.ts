/**
 * The route guard.
 *
 * A signed-out visit to an authenticated page used to paint the shell, call
 * the API, and only then bounce on 401. Now the redirect happens before the
 * first byte: no session cookie, no page. The decision itself lives in
 * `lib/route-guard.ts` so it can be tested as a plain function.
 */

import { NextResponse, type NextRequest } from 'next/server';
import { SESSION_COOKIE, guardRedirect } from '@/lib/route-guard';

// Inlined at build time, like everywhere else the flag is read.
const DEMO = process.env.NEXT_PUBLIC_DEMO === '1';

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const target = guardRedirect({
    pathname,
    search,
    hasSession: request.cookies.has(SESSION_COOKIE),
    demo: DEMO,
  });
  if (!target) return NextResponse.next();
  return NextResponse.redirect(new URL(target, request.url));
}

export const config = {
  // Literals, because Next reads this list at build time. Must match
  // `GUARDED_PREFIXES` in lib/route-guard.ts — a test checks that it does.
  // Nothing public, nothing under /api, no static files: those paths are
  // simply not listed.
  matcher: [
    '/today/:path*',
    '/chat/:path*',
    '/review/:path*',
    '/library/:path*',
    '/progress/:path*',
    '/graph/:path*',
    '/mistakes/:path*',
    '/goals/:path*',
    '/explain/:path*',
    '/socratic/:path*',
    '/notebooks/:path*',
    '/learn/:path*',
    '/settings/:path*',
    '/admin/:path*',
  ],
};
