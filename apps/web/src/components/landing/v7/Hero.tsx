'use client';

/**
 * The opening shot, in layers: the terraces (Mino painted out of the plate),
 * Mino himself near the camera, seen from behind, looking over the valley,
 * and the promise in the sky.
 *
 * Scroll is a camera move: the land pushes in slowly while Mino, being
 * close, slides past and out of the frame — we walk on past him into the
 * world. A fine pointer adds a little depth (the plate and Mino move apart).
 * Mino breathes, and shifts his weight each time the subject turns over.
 * All of it is transform and opacity, read from `--p`, `--mx`, `--my`;
 * reduced motion gets the still composition.
 */

import { useEffect, useRef, useState, type RefObject } from 'react';
import { ButtonLink } from '@/components/ui/Button';
import { useI18n } from '@/lib/i18n';
import { prefersReducedMotion } from '../v6/useSceneProgress';

const PLATE = '/brand/hero/terraces';
const WIDTHS = [640, 1000, 1600];

function srcSet(ext: string) {
  return WIDTHS.map((w) => `${PLATE}-${w}.${ext} ${w}w`).join(', ');
}

export function Hero({
  sectionRef,
  href,
  label,
  showNote,
  onStart,
}: {
  sectionRef: RefObject<HTMLElement | null>;
  href: string;
  label: string;
  showNote: boolean;
  onStart: () => void;
}) {
  const { t } = useI18n();
  const copy = t.landing7.hero;
  const subjects = t.landing4.hero.subjects;
  const frame = useRef<HTMLDivElement>(null);
  const [rotating, setRotating] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const timer = window.setInterval(() => setRotating((i) => (i + 1) % subjects.length), 2600);
    return () => window.clearInterval(timer);
  }, [subjects.length]);

  // Depth from the pointer, on devices that have one.
  useEffect(() => {
    const el = frame.current;
    if (!el || prefersReducedMotion() || !window.matchMedia?.('(pointer: fine)').matches) return;
    let raf = 0;
    let x = 0;
    let y = 0;
    const apply = () => {
      raf = 0;
      el.style.setProperty('--mx', x.toFixed(3));
      el.style.setProperty('--my', y.toFixed(3));
    };
    const move = (event: PointerEvent) => {
      x = (event.clientX / window.innerWidth) * 2 - 1;
      y = (event.clientY / window.innerHeight) * 2 - 1;
      if (!raf) raf = window.requestAnimationFrame(apply);
    };
    window.addEventListener('pointermove', move, { passive: true });
    return () => {
      window.removeEventListener('pointermove', move);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <section ref={sectionRef} className="v6-pin v6-hero l7-hero" style={{ '--len': '140vh' } as React.CSSProperties}>
      <div ref={frame} className="v6-frame l7-hero-frame scene">
        <div className="l7-plate" aria-hidden="true">
          <picture>
            <source type="image/avif" srcSet={srcSet('avif')} sizes="100vw" />
            <source type="image/webp" srcSet={srcSet('webp')} sizes="100vw" />
            <img src={`${PLATE}.jpg`} alt="" width={1600} height={900} fetchPriority="high" decoding="async" />
          </picture>
        </div>
        <div className="l7-mino" aria-hidden="true">
          <div className="l7-mino-sway" data-sway={rotating % 2 ? 'a' : 'b'}>
            <picture>
              <source type="image/avif" srcSet="/brand/hero/mino.avif" />
              <img src="/brand/hero/mino.webp" alt="" width={781} height={1100} decoding="async" />
            </picture>
          </div>
        </div>
        <div className="v6-veil" aria-hidden="true" />
        <div className="content v6-hero-type">
          <h1 className="v6-mega">
            {copy.line}
            <span className="v6-subject" aria-live="off">
              <span key={rotating} className="inline-block animate-fade-up">
                {subjects[rotating] ?? ''}
              </span>
            </span>
          </h1>
          <div className="v6-hero-foot">
            <p className="v6-lede">{copy.sub}</p>
            <div className="l7-hero-act">
              <ButtonLink href={href} size="lg" onClick={onStart} className="btn-ember">
                {label}
              </ButtonLink>
              {showNote && <span className="l7-note">{copy.note}</span>}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
