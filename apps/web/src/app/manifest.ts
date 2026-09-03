import type { MetadataRoute } from 'next';
import { siteConfig } from '@/lib/site-config';

/**
 * Not a PWA -- the product doesn't need one. This exists so a phone's "add
 * to home screen" produces a real name/icon/theme colour instead of the
 * browser's own guess, which is the actual, bounded thing the brief asked
 * for (item 18: "não transformar em PWA completa se produto não exige").
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: siteConfig.name,
    short_name: siteConfig.name,
    description: siteConfig.description,
    start_url: '/',
    display: 'browser',
    background_color: '#fbfaf9',
    theme_color: siteConfig.themeColor,
    icons: [
      { src: '/icon', sizes: '32x32', type: 'image/png' },
      { src: '/apple-icon', sizes: '180x180', type: 'image/png' },
    ],
  };
}
