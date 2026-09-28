/**
 * The API runs somewhere else — a container host, because it needs Postgres,
 * Redis and a worker. The browser still talks only to this origin: `/api/v1/*`
 * is proxied through here.
 *
 * That is not for tidiness. Session cookies are `SameSite=Lax`, so a browser
 * would refuse to send them from this domain to the API's domain — login would
 * appear to succeed and every request after it would come back 401. Proxying
 * makes the cookies first-party and removes the CORS question entirely, without
 * relaxing `SameSite` and the CSRF protection that rests on it.
 */
const API_ORIGIN = process.env.NOEMA_API_ORIGIN;

/**
 * The content security policy, enforced.
 *
 * It shipped report-only first (2026-09-25) because nobody had looked at a
 * browser against it. On 2026-09-26 a headless Chrome walked the landing,
 * login, pricing, Today, a lesson, progress, settings, review and library,
 * signed in, with a listener for violations: none. The same listener did
 * catch a deliberately injected off-policy script and image, so the silence
 * was real. `'unsafe-inline'` stays for scripts and styles: Next's bootstrap
 * and the theme script are inline, and nonces are a separate change.
 */
const CSP_ENFORCED = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://plausible.io",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self' https://plausible.io",
  "media-src 'self'",
  "worker-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "object-src 'none'",
  "form-action 'self'",
].join('; ');


// Development builds evaluate code for fast refresh, which the script policy
// forbids; there, only the framing and base rules apply.
const CSP =
  process.env.NODE_ENV === 'production'
    ? CSP_ENFORCED
    : "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"

const PERMISSIONS = 'camera=(), microphone=(), geolocation=(), payment=(), usb=()';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Account creation lives on /login; the obvious addresses lead there too.
  async redirects() {
    return ['/signup', '/register'].map((source) => ({
      source,
      destination: '/login?mode=register',
      permanent: false,
    }));
  },
  async rewrites() {
    // `beforeFiles`, because the demo route handler lives at the same path and
    // filesystem routes would otherwise win. In demo mode there is no upstream,
    // and that handler is the point.
    if (!API_ORIGIN) return [];
    return {
      beforeFiles: [{ source: '/api/v1/:path*', destination: `${API_ORIGIN}/api/v1/:path*` }],
    };
  },

  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          // One year, this host and anything under it. No `preload`: that is a
          // commitment to the browsers' list, made on purpose, not by default.
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Permissions-Policy', value: PERMISSIONS },
          { key: 'Content-Security-Policy', value: CSP },
        ],
      },
    ];
  },
};

export default nextConfig;
