import type { MetadataRoute } from 'next';
import { siteConfig } from '@/lib/site-config';

/**
 * Not a security boundary -- every route listed here as disallowed still
 * requires real authentication regardless of what a crawler respects. This
 * exists only to give well-behaved crawlers an honest signal about which
 * surface is public (the marketing site, legal pages) versus the
 * authenticated app, so a search result never points at a login-walled page.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: ['/', '/privacy', '/terms'],
      disallow: [
        '/admin',
        '/login',
        '/chat',
        '/learn',
        '/library',
        '/goals',
        '/review',
        '/explain',
        '/socratic',
        '/mistakes',
        '/graph',
        '/progress',
        '/settings',
        '/today',
        '/notebooks',
        '/api',
      ],
    },
    sitemap: `${siteConfig.baseUrl}/sitemap.xml`,
  };
}
