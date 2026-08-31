'use client';

import { useEffect, useRef, useState } from 'react';
import type { MinoState } from '@/brand/mino';

export interface MinoSection {
  id: string;
  state: MinoState;
}

/**
 * Which of `sections` is currently in the vertical middle of the viewport,
 * expressed as the Mino state that section maps to.
 *
 * One `IntersectionObserver` with a band collapsed around the viewport's
 * centre (`rootMargin: '-45% 0px -45% 0px'`) rather than the default
 * edge-to-edge box -- a section only "counts" once it has scrolled to where
 * a reader's eye actually is, so two adjacent short sections do not both
 * claim to be current at once the way an edge-triggered observer would.
 * This only *observes* scroll position; it never sets `scrollTop` or calls
 * `scrollIntoView` itself, so normal, native scrolling is completely
 * unaffected -- there is no hijacking here to disable.
 *
 * Does nothing under `prefers-reduced-motion: reduce`: no observer is ever
 * created, and the state stays at `sections[0]`'s value (`'hero'` today)
 * for the whole visit. A visitor who has asked for less motion should not
 * receive a mascot that keeps changing outside their control, even smoothly.
 */
export function useScrollMinoState(sections: readonly MinoSection[]): {
  state: MinoState;
  registerSection: (id: string) => (element: Element | null) => void;
} {
  const [state, setState] = useState<MinoState>(sections[0]?.state ?? 'hero');
  const stateById = useRef(new Map(sections.map((s) => [s.id, s.state])));
  const elements = useRef(new Map<string, Element>());
  const observer = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    stateById.current = new Map(sections.map((s) => [s.id, s.state]));
  }, [sections]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof IntersectionObserver === 'undefined') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    observer.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const id = entry.target.getAttribute('data-mino-section');
          const next = id ? stateById.current.get(id) : undefined;
          if (next) setState(next);
        }
      },
      { rootMargin: '-45% 0px -45% 0px', threshold: 0 },
    );

    for (const element of elements.current.values()) {
      observer.current.observe(element);
    }

    return () => {
      observer.current?.disconnect();
      observer.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sections` is
    // read once to build the id->state map above; re-running this effect on
    // every render of a caller that inlines a fresh array literal would tear
    // down and rebuild the observer for no reason. The map ref already keeps
    // the mapping current for the callback above.
  }, []);

  function registerSection(id: string) {
    return (element: Element | null) => {
      const previous = elements.current.get(id);
      if (previous && observer.current) observer.current.unobserve(previous);

      if (element) {
        element.setAttribute('data-mino-section', id);
        elements.current.set(id, element);
        observer.current?.observe(element);
      } else {
        elements.current.delete(id);
      }
    };
  }

  return { state, registerSection };
}
