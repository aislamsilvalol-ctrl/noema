'use client';

/**
 * Light / Dark / System, remembered per device.
 *
 * The choice is written to `data-theme` on <html>. `globals.css` keys every
 * token off that attribute (and off `prefers-color-scheme` when it is absent),
 * so switching is a token change, not a re-render — the ground and text colours
 * transition, nothing remounts, nothing flashes white.
 *
 * `system` means "remove the attribute and let the media query decide", which
 * is also what a visitor who has never touched the control gets. The stored
 * value is read before first paint by the inline script in `layout.tsx`, for
 * the same reason the attribute exists at all: a dark-mode visitor must not see
 * a white page for one frame while React wakes up.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark' | 'system';

export const THEME_STORAGE_KEY = 'noema.theme';

function isTheme(value: string | null): value is Theme {
  return value === 'light' || value === 'dark' || value === 'system';
}

/** Applied by the pre-hydration script too — keep the two in step. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'system',
  setTheme: () => undefined,
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('system');

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (isTheme(stored)) setThemeState(stored);
    } catch {
      // Storage blocked: system it is, which is what the page already shows.
    }
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // The choice still applies to this visit.
    }
  }, []);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

/**
 * Runs before hydration so the first paint already has the right ground.
 * Inlined into <head> by `layout.tsx`; deliberately tiny and dependency-free.
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t)}}catch(e){}})();`;
