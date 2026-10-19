'use client';

/**
 * The focus card, as `/foco` draws it: one mission, three steps, the one
 * that is now, and a clock that really runs once the card is on screen.
 * Still under reduced motion.
 */

import { useEffect, useRef, useState } from 'react';
import { useI18n } from '@/lib/i18n';
import { prefersReducedMotion } from '../v6/useSceneProgress';
import { useInView } from './useInView';

const SESSION = 5 * 60;

export function FocusDemo() {
  const { t } = useI18n();
  const card = t.landing7.focus.card;
  const box = useRef<HTMLDivElement>(null);
  const inView = useInView(box, 0.5);
  const [left, setLeft] = useState(SESSION);

  useEffect(() => {
    if (!inView || prefersReducedMotion()) return;
    const timer = window.setInterval(() => setLeft((s) => (s > 1 ? s - 1 : SESSION)), 1000);
    return () => window.clearInterval(timer);
  }, [inView]);

  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;

  return (
    <div ref={box} className="l7-focus-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-signal">{card.mission}</p>
          <p className="mt-1 font-display text-xl text-ink-900">{card.goal}</p>
        </div>
        <p className="l7-clock" aria-label={clock}>
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <circle cx="18" cy="18" r="16" className="l7-clock-track" />
            <circle cx="18" cy="18" r="16" className="l7-clock-fill" pathLength={1} style={{ strokeDashoffset: 1 - left / SESSION }} />
          </svg>
          <span className="font-mono">{clock}</span>
        </p>
      </div>
      <ol className="mt-5 space-y-2">
        {card.steps.map((step, index) => (
          <li key={step} className="flex items-center gap-3 text-base">
            <span aria-hidden="true" className={index === 0 ? 'text-signal' : 'text-ink-300'}>
              {index === 0 ? '●' : '○'}
            </span>
            <span className={index === 0 ? 'text-ink-900' : 'text-ink-500'}>{step}</span>
            {index === 0 && <span className="font-mono text-xs text-signal">{card.now}</span>}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-ink-400">{card.left}</p>
    </div>
  );
}
