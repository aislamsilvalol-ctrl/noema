'use client';

/**
 * The Mino controller: the one place that decides what the character does.
 *
 * Screens talk to it in product terms — `on('input_typing')`, `react('correct')`,
 * `lookAt(x, y)`, `focus(element)` — and it owns everything else: the current
 * and previous state, transient reactions that return on their own, the idle
 * scheduler (rare blinks and glances, never a two-second loop), pointer
 * awareness sampled through requestAnimationFrame and smoothed with a spring,
 * visibility, reduced motion and the quality tier.
 *
 * One controller can drive several rigs (the landing's hero Mino and the
 * companion that follows the scroll are the same character), which is why
 * the pose is held here and rigs only draw it.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  EVENT_TO_STATE,
  POSES,
  TRANSIENT,
  tracksPointer,
  type MinoEvent,
  type MinoState,
  type Pose,
} from '@/components/mino/machine';

export type Quality = 'high' | 'medium' | 'low' | 'reduced';

export interface MinoHandle {
  state: MinoState;
  previous: MinoState | null;
  pose: Pose;
  blink: number;
  quality: Quality;
  /** A product event. The machine picks the state. */
  on: (event: MinoEvent) => void;
  /** A scripted state, for storyboarded sections that direct the character. */
  setState: (state: MinoState) => void;
  react: (outcome: 'correct' | 'wrong') => void;
  /** Look toward a point in viewport pixels; the rig's box decides the angle. */
  lookAt: (x: number, y: number) => void;
  /** Look toward an element (the input being typed into). */
  focus: (element: Element | null) => void;
  reset: () => void;
  /** The rig this controller measures gaze against. */
  bind: (element: Element | null) => void;
}

const MinoContext = createContext<MinoHandle | null>(null);

const IDLE_MIN_MS = 7000;
const IDLE_MAX_MS = 15000;
const SLEEPY_AFTER_MS = 90_000;
const BLINK_MS = 140;
const SPRING = { stiffness: 120, damping: 16 };

function detectQuality(): Quality {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'reduced';
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return 'reduced';
  const nav = navigator as Navigator & { hardwareConcurrency?: number; deviceMemory?: number };
  const cores = nav.hardwareConcurrency ?? 4;
  const memory = nav.deviceMemory ?? 4;
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  if (cores <= 2 || memory <= 2) return 'low';
  if (coarse || cores <= 4) return 'medium';
  return 'high';
}

export function MinoProvider({ children }: { children: ReactNode }) {
  const [state, setStateRaw] = useState<MinoState>('idle');
  const [previous, setPrevious] = useState<MinoState | null>(null);
  const [blink, setBlink] = useState(0);
  const [quality, setQuality] = useState<Quality>('reduced');
  // The gaze/head target the spring moves toward, and the smoothed value.
  const target = useRef({ x: 0, y: 0 });
  const smooth = useRef({ x: 0, y: 0, vx: 0, vy: 0 });
  const [gaze, setGaze] = useState({ x: 0, y: 0 });
  const rig = useRef<Element | null>(null);
  const transientTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sleepTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastInteraction = useRef(Date.now());
  const stateRef = useRef<MinoState>('idle');
  const frame = useRef<number | null>(null);

  useEffect(() => {
    setQuality(detectQuality());
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setQuality(detectQuality());
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const setState = useCallback((next: MinoState) => {
    if (transientTimer.current) clearTimeout(transientTimer.current);
    setStateRaw((current) => {
      if (current !== next) setPrevious(current);
      stateRef.current = next;
      return next;
    });
    const transient = TRANSIENT[next];
    if (transient) {
      transientTimer.current = setTimeout(() => {
        // Only return if nothing else moved the character meanwhile.
        if (stateRef.current === next) setState(transient.after);
      }, transient.ms);
    }
  }, []);

  const touch = useCallback(() => {
    lastInteraction.current = Date.now();
    if (sleepTimer.current) clearTimeout(sleepTimer.current);
    sleepTimer.current = setTimeout(() => {
      if (stateRef.current === 'idle') setState('sleepy');
    }, SLEEPY_AFTER_MS);
  }, [setState]);

  const on = useCallback(
    (event: MinoEvent) => {
      touch();
      setState(EVENT_TO_STATE[event]);
    },
    [setState, touch],
  );

  const react = useCallback(
    (outcome: 'correct' | 'wrong') => on(outcome === 'correct' ? 'exercise_correct' : 'exercise_wrong'),
    [on],
  );

  const reset = useCallback(() => {
    target.current = { x: 0, y: 0 };
    setState('idle');
  }, [setState]);

  const bind = useCallback((element: Element | null) => {
    rig.current = element;
  }, []);

  // Pixel → gaze: relative to the rig's centre, clamped, with a dead zone so
  // the eyes settle instead of jittering around the middle.
  const lookAt = useCallback((x: number, y: number) => {
    const box = rig.current?.getBoundingClientRect();
    if (!box) return;
    const cx = box.left + box.width / 2;
    const cy = box.top + box.height * 0.42;
    const range = Math.max(box.width, 240) * 1.6;
    const gx = Math.max(-1, Math.min(1, (x - cx) / range));
    const gy = Math.max(-1, Math.min(1, (y - cy) / range));
    target.current = { x: Math.abs(gx) < 0.03 ? 0 : gx, y: Math.abs(gy) < 0.03 ? 0 : gy };
  }, []);

  const focus = useCallback(
    (element: Element | null) => {
      if (!element) {
        target.current = { x: 0, y: 0 };
        return;
      }
      const box = element.getBoundingClientRect();
      lookAt(box.left + box.width * 0.3, box.top + box.height / 2);
    },
    [lookAt],
  );

  // Pointer awareness: sampled, not handled — mousemove only records the last
  // position; the spring below reads it once per frame.
  useEffect(() => {
    if (quality === 'reduced' || quality === 'low') return;
    if (!window.matchMedia('(pointer: fine)').matches) return;
    let last: { x: number; y: number } | null = null;
    const onMove = (event: PointerEvent) => {
      last = { x: event.clientX, y: event.clientY };
    };
    const onLeave = () => {
      last = null;
      target.current = { x: 0, y: 0 };
    };
    const tick = () => {
      if (last && tracksPointer(stateRef.current)) lookAt(last.x, last.y);
      pointerFrame = window.setTimeout(tick, 80); // ~12 samples/s is plenty for eyes
    };
    let pointerFrame = window.setTimeout(tick, 80);
    window.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerleave', onLeave);
    return () => {
      window.clearTimeout(pointerFrame);
      window.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerleave', onLeave);
    };
  }, [quality, lookAt]);

  // The spring: one rAF loop, paused when the tab is hidden, stopped when at rest.
  useEffect(() => {
    if (quality === 'reduced') {
      setGaze({ x: 0, y: 0 });
      return;
    }
    let previousTime = performance.now();
    let running = true;
    const step = (now: number) => {
      if (!running) return;
      const dt = Math.min(0.05, (now - previousTime) / 1000);
      previousTime = now;
      const s = smooth.current;
      const t = target.current;
      const ax = SPRING.stiffness * (t.x - s.x) - SPRING.damping * s.vx;
      const ay = SPRING.stiffness * (t.y - s.y) - SPRING.damping * s.vy;
      s.vx += ax * dt;
      s.vy += ay * dt;
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      const moving = Math.abs(s.vx) + Math.abs(s.vy) > 0.002 || Math.abs(t.x - s.x) + Math.abs(t.y - s.y) > 0.002;
      if (moving) setGaze({ x: s.x, y: s.y });
      frame.current = document.hidden ? null : requestAnimationFrame(step);
      if (document.hidden) {
        const resume = () => {
          document.removeEventListener('visibilitychange', resume);
          previousTime = performance.now();
          frame.current = requestAnimationFrame(step);
        };
        document.addEventListener('visibilitychange', resume);
      }
    };
    frame.current = requestAnimationFrame(step);
    return () => {
      running = false;
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [quality]);

  // Idle life: a blink every 7–15 s, sometimes a glance, never on a fixed beat.
  useEffect(() => {
    if (quality === 'reduced') return;
    let cancelled = false;
    const schedule = () => {
      const wait = IDLE_MIN_MS + Math.random() * (IDLE_MAX_MS - IDLE_MIN_MS);
      idleTimer.current = setTimeout(() => {
        if (cancelled) return;
        if (stateRef.current !== 'sleeping') {
          setBlink(1);
          setTimeout(() => setBlink(0), BLINK_MS);
          // one in three idle beats: a short glance to the side, then back
          if (stateRef.current === 'idle' && Math.random() < 0.34) {
            target.current = { x: (Math.random() - 0.5) * 0.8, y: (Math.random() - 0.5) * 0.3 };
            setTimeout(() => {
              if (stateRef.current === 'idle') target.current = { x: 0, y: 0 };
            }, 900 + Math.random() * 600);
          }
        }
        schedule();
      }, wait);
    };
    schedule();
    touch();
    return () => {
      cancelled = true;
      if (idleTimer.current) clearTimeout(idleTimer.current);
      if (sleepTimer.current) clearTimeout(sleepTimer.current);
    };
  }, [quality, touch]);

  const pose = useMemo<Pose>(() => {
    const base = POSES[state];
    const follow = tracksPointer(state) && quality !== 'reduced';
    // In tracking states the pointer steers gaze and a fraction of the head;
    // elsewhere the state's own gaze holds, softened by whatever the spring is doing.
    const gx = follow ? gaze.x : base.gaze.x;
    const gy = follow ? gaze.y : base.gaze.y;
    return {
      ...base,
      gaze: { x: gx, y: gy },
      turn: follow ? base.turn + gx * 0.35 : base.turn,
      tilt: follow ? base.tilt + gy * -2 : base.tilt,
    };
  }, [state, gaze, quality]);

  const value = useMemo<MinoHandle>(
    () => ({ state, previous, pose, blink, quality, on, setState, react, lookAt, focus, reset, bind }),
    [state, previous, pose, blink, quality, on, setState, react, lookAt, focus, reset, bind],
  );

  return <MinoContext.Provider value={value}>{children}</MinoContext.Provider>;
}

/** The shared controller, or null outside a provider (a standalone Mino makes its own). */
export function useMinoOptional(): MinoHandle | null {
  return useContext(MinoContext);
}

export function useMino(): MinoHandle {
  const handle = useContext(MinoContext);
  if (!handle) throw new Error('useMino must be used inside <MinoProvider>');
  return handle;
}
