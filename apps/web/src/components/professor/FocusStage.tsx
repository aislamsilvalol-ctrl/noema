'use client';

/**
 * The Focus Stage header: what the learner in Focus mode always knows.
 *
 * WHERE AM I — the mission of this sitting, in plain words. WHAT AM I DOING —
 * the session map: the concepts of this lesson with ✓ · ← now · ○. HOW MUCH
 * IS LEFT — the same map, read the other way. Beside them the two recovery
 * controls the mode exists for: "Me perdi" (Mino finds where we were, never
 * restarts) and "Resume pra mim" (a ten-second recap from state, no model
 * call), and an optional timer that offers to stop or go five more minutes
 * when it ends — an offer, never pressure.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { api, type Journey, type JourneyRecap } from '@/lib/api';
import { useT } from '@/lib/i18n';

const TIMERS = [5, 10, 15] as const;

export function FocusStage({
  journey,
  minutes,
  onLost,
  onStop,
  onExtend,
  streaming,
}: {
  journey: Journey | null;
  minutes: number;
  onLost: () => void;
  onStop: () => void;
  onExtend: () => void;
  streaming: boolean;
}) {
  const t = useT();
  const copy = t.professor.focus;
  const [recap, setRecap] = useState<JourneyRecap | null>(null);
  const [recapOpen, setRecapOpen] = useState(false);
  const [timer, setTimer] = useState<number | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [ended, setEnded] = useState(false);
  const tick = useRef<ReturnType<typeof setInterval> | null>(null);

  const unit = journey ? journey.plan[journey.current.module] : undefined;
  const lesson = journey && unit ? unit.lessons[journey.current.lesson] : undefined;
  const concepts = lesson?.concepts ?? [];
  const stages = new Map((journey?.concepts ?? []).map((c) => [c.name.toLowerCase(), c.state]));
  const current = journey?.current.concept ?? '';
  const doneCount = concepts.filter((c) => {
    const s = stages.get(c.toLowerCase());
    return s === 'mastered' || s === 'learning';
  }).length;

  useEffect(() => {
    if (timer === null) return;
    setRemaining(timer * 60);
    setEnded(false);
    tick.current = setInterval(() => {
      setRemaining((r) => {
        if (r === null) return r;
        if (r <= 1) {
          if (tick.current) clearInterval(tick.current);
          setEnded(true);
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => {
      if (tick.current) clearInterval(tick.current);
    };
  }, [timer]);

  async function toggleRecap() {
    if (recapOpen) {
      setRecapOpen(false);
      return;
    }
    if (journey) {
      try {
        setRecap(await api.journeyRecap(journey.id));
      } catch {
        setRecap(null);
      }
    }
    setRecapOpen(true);
  }

  const mm = remaining !== null ? Math.floor(remaining / 60) : 0;
  const ss = remaining !== null ? String(remaining % 60).padStart(2, '0') : '00';

  return (
    <section className="mt-4 rounded-lg border border-line bg-raised p-5 shadow-elevation-1" data-focus-stage>
      <p className="text-xs uppercase tracking-wide text-signal">{copy.missionLabel}</p>
      <p className="mt-1 font-display text-lg text-ink-900">
        {current ? copy.mission(minutes, current) : copy.missionGeneric(minutes)}
      </p>

      {concepts.length > 0 && (
        <ol className="mt-4 space-y-1" aria-label={copy.sessionMap} data-session-map>
          {concepts.map((concept) => {
            const stage = stages.get(concept.toLowerCase());
            const done = stage === 'mastered' || stage === 'learning';
            const now = concept.toLowerCase() === current.toLowerCase();
            return (
              <li key={concept} className="flex items-center gap-2 text-sm">
                <span aria-hidden="true" className={done || now ? 'text-signal' : 'text-ink-300'}>
                  {done || now ? '●' : '○'}
                </span>
                <span className={now ? 'text-ink-900' : done ? 'text-ink-500' : 'text-ink-600'}>
                  {concept}
                </span>
                {done && !now && <span className="text-xs text-positive">✓</span>}
                {now && <span className="text-xs uppercase tracking-wide text-signal">{copy.now}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {concepts.length > 0 && (
        <p className="mt-2 text-xs text-ink-400">{copy.leftOf(doneCount, concepts.length)}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onLost} disabled={streaming} data-lost>
          {copy.lost}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void toggleRecap()} aria-expanded={recapOpen}>
          {copy.recap}
        </Button>
        <span className="ml-auto flex items-center gap-1 text-xs text-ink-500">
          {timer === null ? (
            <>
              <span>{copy.timer}</span>
              {TIMERS.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setTimer(m)}
                  className="rounded px-1.5 py-0.5 transition-colors duration-fast hover:text-ink-900"
                >
                  {m}
                </button>
              ))}
            </>
          ) : (
            <>
              <span className="font-mono text-ink-700" aria-live="off">
                {mm}:{ss}
              </span>
              <button
                type="button"
                onClick={() => {
                  setTimer(null);
                  setRemaining(null);
                  setEnded(false);
                }}
                className="px-1.5 transition-colors duration-fast hover:text-ink-900"
              >
                {copy.noTimer}
              </button>
            </>
          )}
        </span>
      </div>

      {recapOpen && (
        <dl className="mt-4 grid gap-3 border-t border-line pt-4 text-sm sm:grid-cols-3" data-recap>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-500">{copy.recapKnow}</dt>
            <dd className="mt-1 text-ink-800">{recap?.know.length ? recap.know.join(', ') : copy.recapNothingYet}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-500">{copy.recapNow}</dt>
            <dd className="mt-1 text-ink-800">{recap?.now || current || copy.recapNothingYet}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-500">{copy.recapNext}</dt>
            <dd className="mt-1 text-ink-800">{recap?.next.length ? recap.next.join(' → ') : copy.recapNothingYet}</dd>
          </div>
          {recap?.parked.length ? (
            <div className="sm:col-span-3">
              <dt className="text-xs uppercase tracking-wide text-ink-500">{copy.parkedLabel}</dt>
              <dd className="mt-1 text-ink-800">{recap.parked.join(' · ')}</dd>
            </div>
          ) : null}
        </dl>
      )}

      {ended && (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4" data-timer-ended>
          <p className="text-sm text-ink-800">{copy.timeUp}</p>
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              setEnded(false);
              setTimer(null);
              window.setTimeout(() => setTimer(5), 0);
              onExtend();
            }}
          >
            {copy.fiveMore}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setEnded(false);
              setTimer(null);
              setRemaining(null);
              onStop();
            }}
          >
            {copy.stopToday}
          </Button>
        </div>
      )}
    </section>
  );
}
