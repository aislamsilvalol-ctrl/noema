/**
 * The one place the site's own identity (not the product's learning content)
 * is defined -- base URL, name, tagline. Every SEO/metadata surface
 * (`layout.tsx`, `robots.ts`, `sitemap.ts`, `opengraph-image.tsx`) reads from
 * here instead of hardcoding a URL or a title string of its own, so there is
 * exactly one place to update when a real custom domain replaces Railway's.
 *
 * No custom domain exists yet -- `RAILWAY_PUBLIC_DOMAIN` is the real,
 * currently-live one, and Railway sets it automatically on every deploy, so
 * this needs no new environment variable of its own.
 */

const domain = process.env.RAILWAY_PUBLIC_DOMAIN;

export const siteConfig = {
  name: 'NOEMA',
  tagline: 'Learn anything. Remember everything.',
  description:
    'An open-source adaptive learning platform that turns your documents, notes and questions into a system that knows what you understand.',
  baseUrl: domain ? `https://${domain}` : 'http://localhost:3000',
  // Plausible's script wants the bare host, not a full URL.
  domain: domain ?? 'localhost',
  themeColor: '#b5450c',
  // Only the real Railway production environment counts -- local dev and any
  // preview/staging deploy must not pollute production analytics (brief
  // item 59).
  isProduction: process.env.RAILWAY_ENVIRONMENT_NAME === 'production',
} as const;
