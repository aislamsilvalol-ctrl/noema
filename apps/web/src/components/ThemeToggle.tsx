'use client';

/**
 * Light / Dark / System as a segmented control.
 *
 * Three options with the current one visibly selected — recognition, not a
 * cycling button whose next state you have to remember. Radio semantics so a
 * screen reader announces "Dark, selected, 2 of 3" and arrow keys move between
 * options, which a row of three buttons would not give for free.
 */

import { useTheme, type Theme } from '@/lib/theme';
import { useT } from '@/lib/i18n';

const OPTIONS: Theme[] = ['light', 'dark', 'system'];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const t = useT();
  const labels: Record<Theme, string> = {
    light: t.settings.themeLight,
    dark: t.settings.themeDark,
    system: t.settings.themeSystem,
  };

  return (
    <div
      role="radiogroup"
      aria-label={t.settings.appearance}
      className="inline-flex rounded-md border border-line p-0.5"
    >
      {OPTIONS.map((option) => {
        const selected = option === theme;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => setTheme(option)}
            className={`rounded-sm px-3 py-1.5 text-sm transition-colors duration-state ${
              selected ? 'bg-ink-900 text-ink-50' : 'text-ink-600 hover:text-ink-900'
            }`}
          >
            {labels[option]}
          </button>
        );
      })}
    </div>
  );
}
