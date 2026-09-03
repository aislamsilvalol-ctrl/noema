'use client';

/**
 * Mino, with behaviour.
 *
 * The art is unchanged: the same six files, resolved through the same map in
 * `brand/mino.ts`, so official character art remains a filename swap. What this
 * adds is a state machine over that art — ten product states mapped onto six
 * poses, a crossfade when the pose changes, and micro-motion on the whole
 * figure that reads as "alive" rather than "animated": a 2% breath at rest, a
 * slight lean while thinking, one short spring when something went well, and
 * nothing at all when asleep.
 *
 * Deliberately whole-figure. The poses are served as `<img>`, which keeps them
 * out of the DOM (an SVG with a script payload cannot run from an image), and
 * that also means no eyes or arms to animate individually. Blinks and eye
 * movement wait for inlined official art; the design system (§8) notes this.
 *
 * Reduced motion: the global rule in `globals.css` collapses every animation
 * and transition, so a visitor who asked for less motion gets the pose change
 * and nothing moving. No separate branch needed here.
 */

import { MINO_ASSETS, type MinoState as Pose } from '@/brand/mino';

export type MinoState =
  | 'idle'
  | 'thinking'
  | 'teaching'
  | 'listening'
  | 'celebrating'
  | 'curious'
  | 'reviewing'
  | 'sleeping'
  | 'confused'
  | 'focused';

//: Which of the six drawings each state shows. Several states share a pose and
//: differ only in motion — that is the point of separating state from art.
const POSE: Record<MinoState, Pose> = {
  idle: 'hero',
  curious: 'hero',
  sleeping: 'hero',
  confused: 'hero',
  thinking: 'thinking',
  teaching: 'pointing',
  listening: 'reading',
  reviewing: 'studying',
  focused: 'reading',
  celebrating: 'celebrating',
};

const MOTION: Record<MinoState, string> = {
  idle: 'mino-breathe',
  curious: 'mino-breathe',
  listening: 'mino-turn',
  thinking: 'mino-lean',
  teaching: '',
  reviewing: 'mino-breathe',
  focused: '',
  celebrating: 'mino-spring',
  confused: 'mino-tilt',
  sleeping: '',
};

const SIZE = {
  sm: 'w-12 h-12',
  md: 'w-20 h-20',
  lg: 'w-40 h-40',
  xl: 'w-full max-w-sm',
} as const;

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
  const pose = POSE[state];

  return (
    <span
      data-mino-state={state}
      className={`mino relative inline-block shrink-0 ${SIZE[size]} ${className}`}
      style={style}
    >
      {/* `key` on the pose: a new element mounts on each change and fades in
          over the old one's ghost, which is a crossfade without holding two
          images in state. Decorative — the surrounding copy carries meaning. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        key={pose}
        src={MINO_ASSETS[pose]}
        alt=""
        aria-hidden="true"
        width={480}
        height={480}
        draggable={false}
        className={`mino-figure h-full w-full select-none ${MOTION[state]}`}
      />
    </span>
  );
}
