'use client';

import { useEffect, useState, type RefObject } from 'react';

/**
 * True once the element has been on screen (at `threshold` of it), and stays
 * true. Without IntersectionObserver (old browsers, tests) it is `null`: the
 * caller shows its finished state instead of waiting for a cue that will
 * never come.
 */
export function useInView(ref: RefObject<HTMLElement | null>, threshold = 0.35): boolean | null {
  const [seen, setSeen] = useState<boolean | null>(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setSeen(null);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, threshold]);

  return seen;
}
