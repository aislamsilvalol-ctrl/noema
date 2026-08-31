'use client';

import { useEffect, useState } from 'react';

const MAX_ROTATE_DEG = 2.5;
const MAX_TRANSLATE_PX = 5;

/**
 * A small, desktop-only tilt for the hero Mino illustration that follows the
 * cursor -- a few degrees of rotation and a few pixels of shift, nothing a
 * visitor would consciously notice as "an animation."
 *
 * `active` is decided once, from real capability rather than viewport width:
 * `(hover: hover) and (pointer: fine)` is true only for an input that can
 * actually hover *and* point precisely, so a touchscreen never attaches the
 * listener at all (there is no cursor to track, and a width-based check
 * alone would still fire it on a touch laptop with a wide screen). Also off
 * entirely under `prefers-reduced-motion: reduce`. Neither condition is
 * re-evaluated after mount -- a device's input capability does not change
 * mid-visit, and reacting to it live would be complexity this never needs.
 *
 * `node` is `useState`, not a plain ref, deliberately: the listener-attaching
 * effect below needs to re-run once the caller's `ref={containerRef}`
 * actually resolves to a real element, and a `useRef` mutation is invisible
 * to React -- it would not schedule that re-run. `useState` makes attaching
 * the DOM node itself the trigger, so the order the caller happens to attach
 * the ref in relative to this hook's own first effect run does not matter.
 */
export function useHeroTilt(): {
  containerRef: (element: HTMLElement | null) => void;
  style: React.CSSProperties;
  active: boolean;
} {
  const [active, setActive] = useState(false);
  const [style, setStyle] = useState<React.CSSProperties>({});
  const [node, setNode] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setActive(canHover && !reduced);
  }, []);

  useEffect(() => {
    if (!active || !node) return;

    function onMove(event: MouseEvent) {
      const box = node!.getBoundingClientRect();
      const x = (event.clientX - (box.left + box.width / 2)) / (box.width / 2);
      const y = (event.clientY - (box.top + box.height / 2)) / (box.height / 2);
      const clampedX = Math.max(-1, Math.min(1, x));
      const clampedY = Math.max(-1, Math.min(1, y));
      setStyle({
        transform: `rotate(${(clampedX * MAX_ROTATE_DEG).toFixed(2)}deg) translate(${(clampedX * MAX_TRANSLATE_PX).toFixed(1)}px, ${(clampedY * MAX_TRANSLATE_PX).toFixed(1)}px)`,
      });
    }

    function onLeave() {
      setStyle({ transform: 'none' });
    }

    node.addEventListener('mousemove', onMove);
    node.addEventListener('mouseleave', onLeave);
    return () => {
      node.removeEventListener('mousemove', onMove);
      node.removeEventListener('mouseleave', onLeave);
    };
  }, [active, node]);

  return { containerRef: setNode, style, active };
}
