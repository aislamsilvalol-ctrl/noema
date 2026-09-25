'use client';

/**
 * Progress made visible, in NOEMA's own terms: a level named for a place on
 * the way (first steps, trail, crossing, altitude, horizon), missions that
 * are small pieces of real learning, and marks stamped like a map's signs.
 *
 * Every number comes from the server, which earns it from the learning
 * evidence; the page sends only its time zone. Nothing here spawns "+10 XP"
 * over buttons, and nothing is coloured like a slot machine: one family of
 * cobalt and ink, shapes instead of rainbow tiers.
 */

import { useEffect, useState } from 'react';
import { api, type MarkState, type Mission, type Progression } from '@/lib/api';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

type Stage = keyof Dict['progression']['stages'];
type MissionId = keyof Dict['progression']['missions'];
type MarkId = keyof Dict['progression']['marks'];

const SEEN_LEVEL = 'noema.level.seen';

function timeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function useProgression(): Progression | null {
  const [progress, setProgress] = useState<Progression | null>(null);
  useEffect(() => {
    let cancelled = false;
    // Started inside a promise so even a synchronous failure lands in the
    // catch below: progress is a layer over learning and must never break it.
    Promise.resolve()
      .then(() => api.progress(timeZone()))
      .then((value) => {
        if (!cancelled) setProgress(value);
      })
      // Progress is a layer over learning: if it fails, the page just shows less.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return progress;
}

function stageName(t: Dict, stage: string): string {
  return t.progression.stages[stage as Stage] ?? stage;
}

function LevelLine({ progress }: { progress: Progression }) {
  const t = useT();
  const span = Math.max(progress.next_level_at - progress.level_floor, 1);
  const into = Math.min(Math.max(progress.xp_total - progress.level_floor, 0), span);
  return (
    <div>
      <p className="text-md text-ink-900">
        {t.progression.levelLine(progress.level, stageName(t, progress.stage))}
      </p>
      <div
        className="mt-2 h-px w-full bg-line"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={span}
        aria-valuenow={into}
        aria-label={t.progression.toNext(span - into)}
      >
        <div className="h-px bg-primary" style={{ width: `${(into / span) * 100}%` }} />
      </div>
      <p className="mt-2 text-sm text-ink-500">
        {t.progression.toNext(span - into)}
        {progress.xp_today > 0 && ` · ${t.progression.xpToday(progress.xp_today)}`}
      </p>
    </div>
  );
}

function MissionList({ missions }: { missions: Mission[] }) {
  const t = useT();
  return (
    <ol className="mt-3 divide-y divide-line border-y border-line">
      {missions.map((mission, index) => (
        <li key={mission.id} className="flex items-baseline gap-4 py-3" data-mission={mission.id}>
          <span className="w-6 shrink-0 font-mono text-sm text-ink-400">
            {String(index + 1).padStart(2, '0')}
          </span>
          <span className={`min-w-0 flex-1 text-base ${mission.done ? 'text-ink-500' : 'text-ink-900'}`}>
            {t.progression.missions[mission.id as MissionId] ?? mission.id}
          </span>
          <span className="shrink-0 font-mono text-sm text-ink-500">
            {mission.done ? (
              <span aria-label={t.progression.earned} className="text-primary">
                ✓
              </span>
            ) : (
              `${mission.progress} / ${mission.target}`
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** A mark is a stamp: a ring and a sign, drawn; dashed and faint until earned. */
const SIGNS: Record<string, string> = {
  first_lesson: 'M12 7v10M7 12h10',
  first_mastered: 'M12 6l6 11H6z',
  first_checkpoint: 'M7 12l3.5 3.5L17 9',
  week_streak: 'M6 15l3-6 3 6 3-6 3 6',
  ten_mastered: 'M12 5l2.2 4.5 4.8.7-3.5 3.4.8 4.9L12 16.2 7.7 18.5l.8-4.9L5 10.2l4.8-.7z',
  hundred_recalls: 'M12 7a5 5 0 1 0 0 10 5 5 0 1 0 0-10M12 10.5v3',
  path_complete: 'M5 17c3-8 11-2 14-10',
};

function Stamp({ mark }: { mark: MarkState }) {
  const t = useT();
  const copy = t.progression.marks[mark.id as MarkId];
  return (
    <li className="flex items-center gap-3" data-mark={mark.id} data-earned={mark.earned}>
      <svg
        viewBox="0 0 24 24"
        className={`h-10 w-10 shrink-0 ${mark.earned ? 'text-primary' : 'text-ink-300'}`}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.25}
        aria-hidden
      >
        <circle cx="12" cy="12" r="11" strokeDasharray={mark.earned ? undefined : '2 2'} />
        <path d={SIGNS[mark.id] ?? 'M8 12h8'} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="min-w-0">
        <span className={`block text-base ${mark.earned ? 'text-ink-900' : 'text-ink-500'}`}>
          {copy?.name ?? mark.id}
        </span>
        <span className="block text-sm text-ink-500">
          {mark.earned ? copy?.hint : t.progression.notYet}
        </span>
      </span>
    </li>
  );
}

/** A level reached since the last visit: said once, briefly, then out of the way. */
function LevelUp({ progress }: { progress: Progression }) {
  const t = useT();
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      const seen = Number(window.localStorage.getItem(SEEN_LEVEL) ?? '0');
      if (seen && progress.level > seen) setShow(true);
      if (!seen || progress.level > seen) {
        window.localStorage.setItem(SEEN_LEVEL, String(progress.level));
      }
    } catch {
      // No storage: no announcement, nothing lost.
    }
  }, [progress.level]);
  if (!show) return null;
  return (
    <div className="mt-8 rounded-lg bg-primary px-6 py-8 text-primary-fg" role="status" data-level-up>
      <p className="font-display text-3xl">{t.progression.levelUp(progress.level)}</p>
      <p className="mt-2 text-md opacity-85">
        {t.progression.levelUpBody(stageName(t, progress.stage))}
      </p>
      <button
        type="button"
        onClick={() => setShow(false)}
        className="mt-5 text-sm underline underline-offset-4"
      >
        {t.progression.dismiss}
      </button>
    </div>
  );
}

/** Today: the day's missions and where the level stands. Below learning, never above it. */
export function TodayProgress() {
  const t = useT();
  const progress = useProgression();
  if (!progress) return null;
  return (
    <section className="mt-12 max-w-reading" data-today-progress>
      <LevelUp progress={progress} />
      <h2 className="mt-8 text-sm text-ink-500">{t.progression.todayTitle}</h2>
      <MissionList missions={progress.missions.filter((m) => m.period === 'daily')} />
      <div className="mt-6">
        <LevelLine progress={progress} />
      </div>
    </section>
  );
}

/** Progress: the whole path — level, the week's missions, the marks. */
export function PathPanel() {
  const t = useT();
  const progress = useProgression();
  if (!progress) return null;
  return (
    <section className="mt-10 max-w-reading" aria-labelledby="path-title" data-path>
      <h2 id="path-title" className="text-lg text-ink-900">
        {t.progression.pathTitle}
      </h2>
      <div className="mt-4">
        <LevelLine progress={progress} />
      </div>
      <h3 className="mt-10 text-sm text-ink-500">{t.progression.weekTitle}</h3>
      <MissionList missions={progress.missions.filter((m) => m.period === 'weekly')} />
      <h3 className="mt-10 text-sm text-ink-500">{t.progression.marksTitle}</h3>
      <ul className="mt-4 grid gap-5 sm:grid-cols-2">
        {progress.marks.map((mark) => (
          <Stamp key={mark.id} mark={mark} />
        ))}
      </ul>
      <p className="mt-8 text-sm text-ink-500">{t.progression.note}</p>
    </section>
  );
}

/** After a session: what it added, from the server's own count. */
export function SessionProgress() {
  const t = useT();
  const progress = useProgression();
  if (!progress) return null;
  const daily = progress.missions.filter((m) => m.period === 'daily');
  return (
    <section className="mt-10 max-w-reading" data-session-progress>
      <h2 className="text-sm text-ink-500">{t.progression.sessionTitle}</h2>
      <p className="mt-2 font-display text-2xl text-ink-900">
        {t.progression.xpToday(progress.xp_today)}
      </p>
      <p className="mt-1 text-sm text-ink-600">
        {t.progression.missionsDone(daily.filter((m) => m.done).length, daily.length)}
      </p>
      <div className="mt-6">
        <LevelLine progress={progress} />
      </div>
    </section>
  );
}
