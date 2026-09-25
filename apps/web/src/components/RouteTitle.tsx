'use client';

/**
 * The document title for every client-rendered route, in the reader's
 * language.
 *
 * Most screens are client components and cannot export `metadata`, and the
 * server renders English before the locale is known, so a static title would
 * be wrong in PT and ES anyway. This sets it once, from the pathname, after
 * the locale is applied. Routes that own server metadata (the landing,
 * privacy, terms) are absent from the table and keep it.
 */

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { siteConfig } from '@/lib/site-config';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

const ROUTES: ReadonlyArray<[RegExp, (t: Dict) => string]> = [
  [/^\/today/, (t) => t.nav.today],
  [/^\/chat/, (t) => t.nav.chat],
  [/^\/learn\/new/, (t) => t.titles.learnNew],
  [/^\/goals/, (t) => t.nav.goals],
  [/^\/graph/, (t) => t.titles.graph],
  [/^\/library/, (t) => t.nav.library],
  [/^\/mistakes/, (t) => t.titles.mistakes],
  [/^\/notebooks\/[^/]+\/cards/, (t) => t.titles.cards],
  [/^\/notebooks\/[^/]+\/exam/, (t) => t.titles.exam],
  [/^\/notebooks\/[^/]+\/professor/, (t) => t.titles.lesson],
  [/^\/notebooks\/[^/]+\/quiz/, (t) => t.titles.quiz],
  [/^\/notebooks\//, (t) => t.nav.notes],
  [/^\/progress/, (t) => t.nav.progress],
  [/^\/review/, (t) => t.nav.review],
  [/^\/settings/, (t) => t.nav.settings],
  [/^\/socratic/, (t) => t.titles.socratic],
  [/^\/explain/, (t) => t.titles.explain],
  [/^\/pricing/, (t) => t.titles.pricing],
  [/^\/login/, (t) => t.titles.signIn],
  [/^\/forgot-password/, (t) => t.titles.forgotPassword],
  [/^\/reset-password/, (t) => t.titles.resetPassword],
  [/^\/admin/, (t) => t.titles.admin],
];

export function titleFor(pathname: string, t: Dict): string | null {
  const match = ROUTES.find(([pattern]) => pattern.test(pathname));
  return match ? `${match[1](t)} — ${siteConfig.name}` : null;
}

export function RouteTitle() {
  const pathname = usePathname();
  const t = useT();

  useEffect(() => {
    const title = titleFor(pathname ?? '/', t);
    if (title) document.title = title;
  }, [pathname, t]);

  return null;
}
