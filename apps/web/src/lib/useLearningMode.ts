'use client';

/**
 * How this learner prefers to learn — Normal or Focus (TDAH / ADHD-friendly).
 *
 * Read once per screen from the account's preferences and cached in
 * sessionStorage so the Focus Stage draws in the right shape on the first
 * paint of the next screen too. A preference, switched at will; never a
 * diagnosis and never inferred from behaviour.
 */

import { useCallback, useEffect, useState } from 'react';
import { track } from '@/lib/analytics';
import { api, type LearningMode, type Preferences } from '@/lib/api';

const KEY = 'noema.preferences';
/** Fired on `window` when the preference changes somewhere else on the page. */
const CHANGED = 'noema:preferences';

function cached(): Preferences | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Preferences) : null;
  } catch {
    return null;
  }
}

function remember(value: Preferences) {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // storage blocked: the value still lives in state for this visit
  }
}

/**
 * Back to normal mode, in place: the preference is saved, every screen using
 * this hook redraws in normal mode, and nobody is sent to Settings for it.
 */
export async function leaveFocusMode(): Promise<Preferences> {
  const value = await api.updatePreferences({ learning_mode: 'normal' });
  remember(value);
  window.dispatchEvent(new CustomEvent<Preferences>(CHANGED, { detail: value }));
  return value;
}

export function useLearningMode(): {
  mode: LearningMode;
  minutes: number;
  loaded: boolean;
  setMode: (mode: LearningMode) => Promise<void>;
  setMinutes: (minutes: number) => Promise<void>;
} {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const seen = cached();
    if (seen) {
      setPrefs(seen);
      setLoaded(true);
    }
    let cancelled = false;
    api
      .preferences()
      .then((value) => {
        if (cancelled) return;
        setPrefs(value);
        remember(value);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    const onChanged = (event: Event) => {
      const value = (event as CustomEvent<Preferences>).detail;
      if (value) setPrefs(value);
    };
    window.addEventListener(CHANGED, onChanged);
    return () => {
      cancelled = true;
      window.removeEventListener(CHANGED, onChanged);
    };
  }, []);

  const update = useCallback(async (patch: Partial<Preferences>) => {
    const value = await api.updatePreferences(patch);
    setPrefs(value);
    remember(value);
  }, []);

  return {
    mode: prefs?.learning_mode ?? 'normal',
    minutes: prefs?.session_minutes ?? 7,
    loaded,
    setMode: async (mode) => {
      await update({ learning_mode: mode });
      if (mode === 'focus') track('adhd_mode_enabled', { via: 'preference' });
    },
    setMinutes: (minutes) => update({ session_minutes: minutes }),
  };
}
