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
import { api, type LearningMode, type Preferences } from '@/lib/api';

const KEY = 'noema.preferences';

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
    return () => {
      cancelled = true;
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
    setMode: (mode) => update({ learning_mode: mode }),
    setMinutes: (minutes) => update({ session_minutes: minutes }),
  };
}
