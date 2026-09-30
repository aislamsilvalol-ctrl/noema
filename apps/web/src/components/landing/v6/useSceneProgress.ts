'use client';

import { useEffect, type RefObject } from 'react';

/**
 * Scroll progress through a pinned scene, as a CSS variable.
 *
 * Writes `--p` (0 when the section's top reaches the top of the viewport, 1
 * when its bottom reaches the bottom) on the section itself; everything that
 * moves is CSS reading it. A section with `data-steps="n"` also gets
 * `data-step` (0…n-1), for the swaps that should play as a cut with its own
 * short transition rather than follow the finger.
 *
 * Every scene shares one passive scroll listener and one rAF per frame; the
 * browser scrolls natively, nothing is hijacked. Under reduced motion the
 * hook does nothing and the page renders its static compositions.
 */

const scenes = new Set<HTMLElement>();
let frame = 0;

function measure() {
  frame = 0;
  const vh = window.innerHeight;
  for (const el of scenes) {
    const rect = el.getBoundingClientRect();
    const travel = rect.height - vh;
    const p = travel > 0 ? Math.min(1, Math.max(0, -rect.top / travel)) : rect.top <= 0 ? 1 : 0;
    el.style.setProperty('--p', p.toFixed(4));
    const steps = Number(el.dataset.steps);
    if (steps > 0) {
      const step = String(Math.min(steps - 1, Math.floor(p * steps)));
      if (el.dataset.step !== step) el.dataset.step = step;
    }
  }
}

/** Measures again on the next frame — for when the page's layout changed
 * under the scenes (pinning switched on) without a scroll. */
export function refreshScenes() {
  if (scenes.size) schedule();
}

function schedule() {
  if (frame) return;
  if (typeof window.requestAnimationFrame !== 'function') return measure();
  frame = window.requestAnimationFrame(measure);
}

export function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function useSceneProgress(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    scenes.add(el);
    if (scenes.size === 1) {
      window.addEventListener('scroll', schedule, { passive: true });
      window.addEventListener('resize', schedule);
    }
    schedule();
    return () => {
      scenes.delete(el);
      el.style.removeProperty('--p');
      if (scenes.size === 0) {
        window.removeEventListener('scroll', schedule);
        window.removeEventListener('resize', schedule);
        if (frame) window.cancelAnimationFrame(frame);
        frame = 0;
      }
    };
  }, [ref]);
}
