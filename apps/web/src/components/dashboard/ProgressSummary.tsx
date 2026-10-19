'use client';

/**
 * Four signals, set like a magazine's numbers, and one quiet line of today's
 * small goals. Every number is the server's: concepts mastered (journeys),
 * level and its stage (progression), days studied this week (the weekly
 * "days" mission — the closest this product comes to a streak, on purpose),
 * and what landed today (the journey's momentum). A signal with no source is
 * not drawn; nothing is estimated here.
 */

import Link from 'next/link';
import type { Mission, Progression } from '@/lib/api';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';
import { useReveal } from './Landscape';

type MissionId = keyof Dict['progression']['missions'];
type Stage = keyof Dict['progression']['stages'];

interface Signal {
  key: string;
  value: string;
  suffix?: string;
  label: string;
  bar?: number;
}

export function ProgressSummary({
  mastered,
  seen,
  progress,
  today,
}: {
  mastered: number;
  seen: number;
  progress: Progression | null;
  today: { mastered: number; events: number } | null;
}) {
  const t = useT();
  const copy = t.home.progress;
  const [ref, shown] = useReveal<HTMLElement>();

  const signals: Signal[] = [];
  if (seen > 0) signals.push({ key: 'mastered', value: String(mastered), label: copy.mastered(seen) });
  if (progress) {
    const span = Math.max(progress.next_level_at - progress.level_floor, 1);
    const into = Math.min(Math.max(progress.xp_total - progress.level_floor, 0), span);
    signals.push({
      key: 'level',
      value: String(progress.level),
      label: copy.level(t.progression.stages[progress.stage as Stage] ?? progress.stage),
      bar: into / span,
    });
    const days = progress.missions.find((m) => m.id === 'days');
    if (days) signals.push({ key: 'week', value: String(days.progress), suffix: `/${days.target}`, label: copy.week(days.target) });
  }
  // A zero today is not progress worth a number; the signal waits for one.
  if (today && (today.mastered > 0 || today.events > 0)) {
    signals.push({
      key: 'today',
      value: String(today.mastered > 0 ? today.mastered : today.events),
      label: copy.today(today.mastered),
    });
  }
  if (signals.length === 0) return null;

  const daily: Mission[] = (progress?.missions ?? []).filter((m) => m.period === 'daily');

  return (
    <section ref={ref} data-shown={shown} aria-labelledby="home-progress" className="dash-reveal" data-progress-summary>
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="home-progress" className="font-display text-xl text-ink-900">
          {copy.title}
        </h2>
        <Link href="/progress" className="text-sm text-accent underline-offset-4 hover:underline">
          {copy.all} →
        </Link>
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-8 border-t border-line pt-6 lg:grid-cols-4">
        {signals.map((signal) => (
          <div key={signal.key} data-signal={signal.key}>
            <dt className="sr-only">{signal.label}</dt>
            <dd>
              <span className="font-display text-3xl tabular-nums text-ink-900">
                {signal.value}
                {signal.suffix && <span className="text-xl text-ink-400">{signal.suffix}</span>}
              </span>
              <span className="mt-1 block text-sm text-ink-500" aria-hidden="true">
                {signal.label}
              </span>
              {signal.bar !== undefined && (
                <span className="mt-3 block h-[3px] w-full max-w-[10rem] overflow-hidden rounded-full bg-line" aria-hidden="true">
                  <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round(signal.bar * 100)}%` }} />
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {daily.length > 0 && (
        <p className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-500" data-daily-goals>
          <span className="font-mono text-xs text-ink-400">{copy.goals}</span>
          {daily.map((mission) => (
            <span key={mission.id} className={`inline-flex items-center gap-2 ${mission.done ? 'text-ink-400' : ''}`}>
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${mission.done ? 'bg-dash-mineral' : 'border border-ink-400'}`}
              />
              {t.progression.missions[mission.id as MissionId] ?? mission.id}
              {!mission.done && (
                <span className="font-mono text-xs text-ink-400">
                  {mission.progress}/{mission.target}
                </span>
              )}
            </span>
          ))}
        </p>
      )}
    </section>
  );
}
