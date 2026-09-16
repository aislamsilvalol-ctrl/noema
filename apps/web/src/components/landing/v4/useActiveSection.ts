'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Which registered section is at the reader's eye: one IntersectionObserver
 * with a band around the viewport's middle, no scroll listeners. Returns the
 * active id, or the first id until anything else takes the centre. Under
 * reduced motion no observer is created and the first id stays — a visitor
 * who asked for less motion should not get a character that keeps changing.
 */
export function useActiveSection(ids: readonly string[]): {
  active: string;
  register: (id: string) => (element: Element | null) => void;
} {
  const [active, setActive] = useState(ids[0] ?? '');
  const elements = useRef(new Map<string, Element>());
  const observer = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    if (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    observer.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const id = entry.target.getAttribute('data-section');
          if (id) setActive(id);
        }
      },
      { rootMargin: '-40% 0px -45% 0px', threshold: 0 },
    );
    for (const element of elements.current.values()) observer.current.observe(element);
    return () => {
      observer.current?.disconnect();
      observer.current = null;
    };
  }, []);

  function register(id: string) {
    return (element: Element | null) => {
      const previous = elements.current.get(id);
      if (previous && observer.current) observer.current.unobserve(previous);
      if (element) {
        element.setAttribute('data-section', id);
        elements.current.set(id, element);
        observer.current?.observe(element);
      } else {
        elements.current.delete(id);
      }
    };
  }

  return { active, register };
}
