'use client';

/**
 * The language menu.
 *
 * A native <select>: three options do not justify a custom dropdown, and the
 * native one is the only one that is free on every screen reader and phone.
 * Labelled in the current language, but its options never are — each language
 * names itself, because this menu matters most to someone staring at an
 * interface they cannot read.
 */

import { LOCALES, useI18n, type Locale } from '@/lib/i18n';

export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();

  return (
    <select
      value={locale}
      onChange={(event) => setLocale(event.target.value as Locale)}
      aria-label={t.common.language}
      className={`rounded-md border border-line bg-transparent px-2 py-1 text-xs text-ink-500 transition-colors duration-state hover:text-ink-900 ${className}`}
    >
      {LOCALES.map((option) => (
        <option key={option.code} value={option.code}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
