'use client';

/**
 * Where Mino is on a product screen, and how much of him.
 *
 * The chat is the protagonist; the character lives at its edge. A presence
 * level — hidden · avatar-only · peek · half · contextual · celebration — is
 * derived from the controller's state, the viewport and the quality tier,
 * and this component draws the figure accordingly: resting his arms on the
 * bottom edge of the conversation while nothing is happening, rising when
 * he thinks or teaches, all the way up for a moment when something went
 * well, and never over the content on a phone (there, the message avatar
 * is his presence).
 */

import { useEffect, useState } from 'react';
import { MinoLive, useMino } from '@/components/mino/Mino';
import type { MinoState } from '@/components/mino/machine';

export type Presence = 'hidden' | 'avatar' | 'peek' | 'half' | 'contextual' | 'celebration';

export function presenceFor(state: MinoState, wide: boolean): Presence {
  if (!wide) return 'avatar';
  switch (state) {
    case 'happy':
    case 'celebrating':
      return 'celebration';
    case 'thinking':
    case 'teaching':
    case 'pointing':
    case 'listening':
    case 'curious':
    case 'questioning':
    case 'correcting':
    case 'writing':
    case 'exam':
      return 'half';
    case 'confused':
    case 'concerned':
      return 'contextual';
    case 'sleepy':
    case 'sleeping':
      return 'peek';
    default:
      return 'peek';
  }
}

// How far down the figure sits, as a share of its own height.
const OFFSET: Record<Presence, string> = {
  hidden: 'translate-y-full opacity-0',
  avatar: 'translate-y-full opacity-0',
  peek: 'translate-y-[58%]',
  half: 'translate-y-[34%]',
  contextual: 'translate-y-[34%]',
  celebration: 'translate-y-[8%]',
};

export function MinoPresence() {
  const mino = useMino();
  const [wide, setWide] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(min-width: 768px)');
    const update = () => setWide(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const presence = presenceFor(mino.state, wide);

  return (
    <div
      aria-hidden="true"
      data-mino-presence={presence}
      className={`pointer-events-none fixed bottom-0 right-4 z-10 hidden w-36 transition-[transform,opacity] duration-slow ease-noema md:block lg:right-8 lg:w-44 ${OFFSET[presence]}`}
    >
      <MinoLive size="xl" primary className="w-full" />
    </div>
  );
}
