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
 * The content security policy, in two halves.
 *
 * Enforced now: the directives that cannot break a page, because nothing here
 * frames NOEMA, uses <base>, plugins, or posts a form to another origin. They
 * stop clickjacking and base-tag hijacking outright.
 *
 * Report-only for now: the script, style and connection allowlist. Next injects
 * inline bootstrap scripts, the theme script runs before paint, Plausible loads
 * from its own origin, and the 3D stage may use blob workers. Nobody has looked
 * at a real browser console against this policy yet; enforcing it blind could
 * blank the app. Violations show in the console, and once a release shows none,
 * this half moves into `CSP_ENFORCED`.
 */
const CSP_ENFORCED = [
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "object-src 'none'",
  "form-action 'self'",
].join('; ');

const CSP_REPORT_ONLY = [
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

const PERMISSIONS = 'camera=(), microphone=(), geolocation=(), payment=(), usb=()';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
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
          { key: 'Content-Security-Policy', value: CSP_ENFORCED },
          { key: 'Content-Security-Policy-Report-Only', value: CSP_REPORT_ONLY },
        ],
      },
    ];
  },
};

export default nextConfig;
