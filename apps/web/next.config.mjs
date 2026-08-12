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
        ],
      },
    ];
  },
};

export default nextConfig;
