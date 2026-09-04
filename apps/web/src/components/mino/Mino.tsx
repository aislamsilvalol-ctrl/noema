'use client';

/**
 * Mino, on screen.
 *
 * Two ways to place the character:
 *
 * - `<Mino state="curious" />` — a standalone figure with its own small
 *   controller: it blinks, breathes, settles into the state's pose and
 *   follows nothing. This is what product screens use (empty states, the
 *   Professor header, reviews, 404): one figure, one state, no wiring.
 *
 * - `<MinoLive />` inside a `<MinoProvider>` — the shared character. The
 *   provider holds the state and the gaze; every `MinoLive` draws the same
 *   pose, so the hero figure and the scroll companion are one Mino, and
 *   product events (`useMino().on(...)`) move all of them at once.
 *
 * Both render the same rig. Sizes are the same four as before.
 */

import { useEffect, useRef, useState } from 'react';
import { POSES, type MinoState } from '@/components/mino/machine';
import { MinoProvider, useMino, useMinoOptional } from '@/components/mino/MinoController';
import { MinoRig } from '@/components/mino/rig/MinoRig';

export type { MinoState } from '@/components/mino/machine';

const SIZE = {
  sm: 'w-12 h-12',
  md: 'w-20 h-20',
  lg: 'w-40 h-40',
  xl: 'w-full max-w-sm',
} as const;

function Figure({
  state,
  size,
  className,
  style,
  bind,
  pose,
  blink,
}: {
  state: MinoState;
  size: keyof typeof SIZE;
  className: string;
  style?: React.CSSProperties;
  bind?: (element: Element | null) => void;
  pose: (typeof POSES)[MinoState];
  blink: number;
}) {
  return (
    <span
      ref={bind}
      data-mino-state={state}
      className={`mino relative inline-block shrink-0 ${SIZE[size]} ${className}`}
      style={style}
    >
      <MinoRig pose={pose} blink={blink} className="mino-figure h-full w-full select-none" />
    </span>
  );
}

/** Standalone: the state's pose, a blink now and then, nothing else to wire. */
export function Mino({
  state = 'idle',
  size = 'md',
  className = '',
  style,
}: {
  state?: MinoState;
  size?: keyof typeof SIZE;
  className?: string;
  style?: React.CSSProperties;
}) {
  const shared = useMinoOptional();
  const [blink, setBlink] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A standalone figure blinks on its own, rarely; inside a provider the
  // provider's blink is used so every figure blinks together.
  useEffect(() => {
    if (shared) return;
    if (typeof window.matchMedia !== 'function') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let cancelled = false;
    const schedule = () => {
      timer.current = setTimeout(() => {
        if (cancelled) return;
        setBlink(1);
        setTimeout(() => setBlink(0), 140);
        schedule();
      }, 6000 + Math.random() * 9000);
    };
    schedule();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [shared]);

  return (
    <Figure
      state={state}
      size={size}
      className={className}
      style={style}
      pose={POSES[state]}
      blink={shared ? shared.blink : blink}
    />
  );
}

/** The shared character. Must sit inside `<MinoProvider>`. */
export function MinoLive({
  size = 'xl',
  className = '',
  style,
  primary = false,
}: {
  size?: keyof typeof SIZE;
  className?: string;
  style?: React.CSSProperties;
  /** The figure gaze is measured against; exactly one per provider. */
  primary?: boolean;
}) {
  const mino = useMino();
  return (
    <Figure
      state={mino.state}
      size={size}
      className={className}
      style={style}
      bind={primary ? mino.bind : undefined}
      pose={mino.pose}
      blink={mino.blink}
    />
  );
}

export { MinoProvider, useMino };
