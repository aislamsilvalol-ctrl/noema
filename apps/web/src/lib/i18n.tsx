'use client';

/**
 * Locale detection, choice, and the dictionary that follows from them.
 *
 * Three rules, in priority order:
 *
 * 1. An explicit choice wins, forever. It is stored and never second-guessed —
 *    a Brazilian reading in English on purpose does not want the site deciding
 *    they made a mistake.
 * 2. Otherwise the browser's language list decides. `navigator.languages` is
 *    the user's own ranking; the first entry we can serve, we serve.
 * 3. Otherwise English, which is also what the server renders. The first paint
 *    is always English and the detected locale applies on hydration — a brief
 *    flash for non-English users, which is honest, unlike rendering Portuguese
 *    on the server for a crawler that asked for nothing.
 *
 * The dictionaries are typed off the English one, so a key missing from a
 * translation is a compile error rather than an English sentence appearing in
 * the middle of a Portuguese screen three weeks after someone adds a feature.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { en, type Dict } from '@/locales/en';
import { pt } from '@/locales/pt';
import { es } from '@/locales/es';

export type Locale = 'en' | 'pt' | 'es';

export const LOCALES: { code: Locale; label: string }[] = [
  // Each language named in itself: the moment this menu matters most is when
  // the interface is in a language the reader cannot understand.
  { code: 'en', label: 'English' },
  { code: 'pt', label: 'Português' },
  { code: 'es', label: 'Español' },
];

const DICTS: Record<Locale, Dict> = { en, pt, es };

//: localStorage rather than a cookie: the choice only affects client rendering,
//: and a cookie would promise the server honours it, which it does not (yet).
const STORAGE_KEY = 'noema.locale';

function isLocale(value: string | null): value is Locale {
  return value === 'en' || value === 'pt' || value === 'es';
}

/** The browser's own preference order, reduced to what we can serve. */
export function detectLocale(): Locale {
  if (typeof navigator === 'undefined') return 'en';
  for (const tag of navigator.languages ?? [navigator.language]) {
    const base = tag.slice(0, 2).toLowerCase();
    if (isLocale(base)) return base;
  }
  return 'en';
}

interface I18n {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Dict;
}

const I18nContext = createContext<I18n>({
  locale: 'en',
  setLocale: () => undefined,
  t: en,
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  // Starts 'en' to match the server's HTML; corrected on mount. Starting with
  // the detected value would make the first client render disagree with the
  // server markup, which React treats as a bug because it is one.
  const [locale, setLocaleState] = useState<Locale>('en');

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    setLocaleState(isLocale(stored) ? stored : detectLocale());
  }, []);

  useEffect(() => {
    // Screen readers pick pronunciation from this; leaving it "en" over
    // Portuguese text produces gibberish for exactly the users who depend on it.
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage can be full or blocked; the choice still applies to this visit.
    }
  }, []);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t: DICTS[locale] }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}

/** The dictionary alone, for components that only read. */
export function useT(): Dict {
  return useContext(I18nContext).t;
}
