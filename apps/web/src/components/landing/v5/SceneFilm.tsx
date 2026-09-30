'use client';

import { useEffect, useRef, useState } from 'react';
import { Landscape, type Scene } from './Landscape';

/**
 * A landscape that lives: the still is the frame, a short film plays over it.
 *
 * The still paints first and stays the LCP; the film is fetched only after the
 * page has settled, never for reduced motion or Save-Data, and only while the
 * scene is on screen. It fades in once it is actually playing, so a slow
 * network shows the still, never a black box. Each film starts and ends on the
 * still's own frame, so the loop has no seam; the slow camera move is ours
 * (CSS on `.scene-camera`), not baked into the footage, so it never jumps.
 *
 * Phones get their own vertical cut when one exists.
 */

export type Film = {
  /** Base path without suffix, e.g. `/brand/film/valley`. */
  src: string;
  /** A `-mobile` cut exists for portrait screens. */
  mobile?: boolean;
};

function wantsFilm(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return !connection?.saveData;
}

export function SceneFilm({
  scene,
  film,
  priority = false,
  position,
}: {
  scene: Scene;
  film: Film;
  priority?: boolean;
  position?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [cut, setCut] = useState<string | null>(null);
  // The phone cut is already framed on Mino; only the wide cut is re-anchored.
  const [framed, setFramed] = useState(false);
  const [playing, setPlaying] = useState(false);

  // Choose the cut after the page has painted: the still is what loads first.
  useEffect(() => {
    if (!wantsFilm()) return;
    const portrait = window.matchMedia('(max-width: 640px) and (orientation: portrait)').matches;
    const base = film.mobile && portrait ? `${film.src}-mobile` : film.src;
    const go = () => {
      setFramed(base.endsWith('-mobile'));
      setCut(base);
    };
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number })
      .requestIdleCallback;
    if (priority) {
      const timer = window.setTimeout(() => (idle ? idle(go) : go()), 1200);
      return () => window.clearTimeout(timer);
    }
    go();
  }, [film.mobile, film.src, priority]);

  // Play only while the scene is on screen; below the fold, load only then.
  useEffect(() => {
    const el = video.current;
    const target = box.current;
    if (!cut || !el || !target) return;
    if (typeof IntersectionObserver === 'undefined') {
      el.preload = 'auto';
      void el.play?.()?.catch(() => undefined);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          if (el.preload !== 'auto') el.preload = 'auto';
          void el.play().catch(() => undefined);
        } else {
          el.pause();
        }
      },
      { rootMargin: '200px 0px' },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [cut]);

  return (
    <div ref={box} className="scene-camera" aria-hidden="true">
      <div className="scene-drift">
        <Landscape scene={scene} priority={priority} position={position} />
        {cut && (
          <video
            ref={video}
            className={`scene-film ${playing ? 'is-playing' : ''}`}
            muted
            loop
            playsInline
            preload="none"
            disablePictureInPicture
            onPlaying={() => setPlaying(true)}
            style={{ objectPosition: framed ? '50% 50%' : position }}
          >
            <source src={`${cut}.webm`} type='video/webm; codecs="vp9"' />
            <source src={`${cut}.mp4`} type="video/mp4" />
          </video>
        )}
      </div>
    </div>
  );
}
