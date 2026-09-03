import type { MetadataRoute } from 'next';
import { siteConfig } from '@/lib/site-config';

/**
 * Public/indexable URLs only -- the authenticated app (chat, notebooks,
 * admin, settings, ...) and auth pages are deliberately absent, matching
 * `robots.ts`'s disallow list.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: siteConfig.baseUrl, lastModified: now, changeFrequency: 'weekly', priority: 1 },
    {
      url: `${siteConfig.baseUrl}/privacy`,
      lastModified: now,
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${siteConfig.baseUrl}/terms`,
      lastModified: now,
      changeFrequency: 'yearly',
      priority: 0.3,
    },
  ];
}
