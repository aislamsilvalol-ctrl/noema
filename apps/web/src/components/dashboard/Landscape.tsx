'use client';

/**
 * A NOEMA plate: the responsive picture (AVIF, then WebP, at 640/1000/1600)
 * and nothing else. The hero's is the one priority image on Home; every tile
 * is lazy. `onLoad` lets the hero fade its plate in once the bytes are there
 * instead of popping a half-drawn photograph over the sky.
 */

import { useEffect, useRef, useState, type RefObject } from 'react';
import type { Plate } from './homeState';

const WIDTHS = [640, 1000, 1600];

function srcSet(plate: Plate, ext: string) {
  return WIDTHS.map((w) => `/brand/landscapes/${plate}-${w}.${ext} ${w}w`).join(', ');
}

export function Landscape({
  plate,
  sizes = '100vw',
  priority = false,
  className = '',
  onLoad,
}: {
  plate: Plate;
  sizes?: string;
  priority?: boolean;
  className?: string;
  onLoad?: () => void;
}) {
  return (
    <picture className={className}>
      <source type="image/avif" srcSet={srcSet(plate, 'avif')} sizes={sizes} />
      <source type="image/webp" srcSet={srcSet(plate, 'webp')} sizes={sizes} />
      <img
        src={`/brand/landscapes/${plate}-1000.webp`}
        alt=""
        width={1600}
        height={900}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        decoding="async"
        onLoad={onLoad}
        // A cached image can finish before React attaches onLoad.
        ref={(img) => {
          if (img?.complete && img.naturalWidth > 0) onLoad?.();
        }}
      />
    </picture>
  );
}

/**
 * True once the element has been on screen — for the bands and tiles that
 * rise into place. Without IntersectionObserver (tests, old browsers) it is
 * true at once: content is never hidden waiting for an animation.
 */
export function useReveal<T extends Element>(): [RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShown(true);
          observer.disconnect();
        }
      },
      { rootMargin: '0px 0px -8% 0px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, shown];
}
