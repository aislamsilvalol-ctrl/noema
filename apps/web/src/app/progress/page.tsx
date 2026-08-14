'use client';

/**
 * What the system thinks you know, and whether it has been right.
 *
 * Mastery is the product's central number and until now it existed only in the
 * database. A score nobody can see is a score nobody can disagree with, which
 * sounds convenient and is the opposite of useful: the engine stores its working
 * precisely so a learner can open it and say "no, I do know this".
 *
 * The calibration section is here for the same reason. A tool that tells you when
 * to study should show whether its predictions have held — including, loudly, when
 * it does not yet have the history to claim anything.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shell } from '@/components/Shell';
import {
  ApiError,
  api,
  type Calibration,
  type ForecastDay,
  type Mastery,
} from '@/lib/api';

const BAND = [
  { floor: 80, label: 'Solid', tone: 'text-positive' },
  { floor: 60, label: 'Holding', tone: 'text-ink-700' },
  { floor: 40, label: 'Shaky', tone: 'text-ink-600' },
  { floor: 0, label: 'Weak', tone: 'text-critical' },
];

function band(score: number) {
  return BAND.find((b) => score >= b.floor) ?? BAND[BAND.length - 1]!;
}

function percent(value: unknown): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';
}

export default function ProgressPage() {
  const router = useRouter();
  const [mastery, setMastery] = useState<Mastery[]>([]);
  const [forecast, setForecast] = useState<ForecastDay[]>([]);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fitting, setFitting] = useState(false);
  const [fitResult, setFitResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [scores, days, honesty] = await Promise.all([
        api.mastery(),
        api.forecast(14),
        api.calibration(),
      ]);
      // Weakest first: the list exists to be acted on, and the top of it should be
      // where the work is.
      setMastery([...scores].sort((a, b) => a.mastery - b.mastery));
      setForecast(days);
      setCalibration(honesty);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not load your progress.');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function fit() {
    setFitting(true);
    setFitResult(null);
    try {
      const result = await api.fitSchedule();
      setFitResult(result.summary);
      if (result.adopted) await load();
    } catch (err) {
      setFitResult(err instanceof Error ? err.message : 'The fit could not run.');
    } finally {
      setFitting(false);
    }
  }

  const busiest = Math.max(1, ...forecast.map((d) => d.due));

  return (
    <Shell>
      <h1 className="font-display text-2xl text-ink-900">Progress</h1>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">Loading…</p>
      ) : (
        <>
          <section className="mt-12 max-w-reading">
            <h2 className="text-xs uppercase tracking-wide text-ink-500">
              What you know
            </h2>

            {mastery.length === 0 ? (
              <p className="mt-3 text-base text-ink-600">
                Nothing scored yet. Mastery is computed per concept from answers and
                reviews, so it appears once a document has been read and questions
                have been answered — not from having uploaded something.
              </p>
            ) : (
              <ul className="mt-4 divide-y divide-line border-y border-line">
                {mastery.map((row) => {
                  const shown = Math.round(row.mastery);
                  const expanded = open === row.concept_id;
                  return (
                    <li key={row.concept_id} className="py-3">
                      <button
                        type="button"
                        onClick={() => setOpen(expanded ? null : row.concept_id)}
                        className="flex w-full items-baseline justify-between text-left"
                      >
                        <span className="min-w-0 pr-4">
                          <span className="block truncate text-sm text-ink-800">
                            {row.concept_name}
                          </span>
                          {row.provisional && (
                            // Said out loud rather than hidden behind an asterisk:
                            // a number from two answers is a guess wearing a
                            // number's clothes.
                            <span className="mt-0.5 block text-xs text-ink-400">
                              provisional — too little evidence to trust yet
                            </span>
                          )}
                        </span>
                        <span
                          className={`shrink-0 font-mono text-sm ${band(shown).tone}`}
                        >
                          {shown}
                          <span className="ml-2 text-xs text-ink-400">
                            {band(shown).label}
                          </span>
                        </span>
                      </button>

                      {expanded && (
                        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-l-2 border-line pl-4 text-xs text-ink-600">
                          <dt>How often you get it right</dt>
                          <dd className="text-right font-mono">
                            {percent(row.components.competence)}
                          </dd>
                          <dt>How likely you are to recall it now</dt>
                          <dd className="text-right font-mono">
                            {percent(row.components.retrievability)}
                          </dd>
                          <dt>Expected from its prerequisites</dt>
                          <dd className="text-right font-mono">
                            {percent(row.components.prior_mean)}
                          </dd>
                          <dt>Evidence behind the score</dt>
                          <dd className="text-right font-mono">
                            {typeof row.components.effective_observations === 'number'
                              ? row.components.effective_observations.toFixed(1)
                              : '—'}{' '}
                            answers
                          </dd>
                        </dl>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="mt-16 max-w-reading">
            <h2 className="text-xs uppercase tracking-wide text-ink-500">
              What is coming
            </h2>
            {forecast.every((d) => d.due === 0) ? (
              <p className="mt-3 text-base text-ink-600">
                Nothing scheduled in the next two weeks.
              </p>
            ) : (
              <>
                <ul className="mt-4 flex items-end gap-1" aria-hidden>
                  {forecast.map((day) => (
                    <li
                      key={day.date}
                      title={`${day.date}: ${day.due}`}
                      style={{ height: `${Math.max(4, (day.due / busiest) * 72)}px` }}
                      className="flex-1 rounded-sm bg-ink-200"
                    />
                  ))}
                </ul>
                <p className="mt-3 text-sm text-ink-600">
                  {forecast.reduce((sum, d) => sum + d.due, 0)} reviews over the next{' '}
                  {forecast.length} days, busiest day {busiest}. Spikes are worth
                  knowing about before they arrive.
                </p>
              </>
            )}
          </section>

          {calibration?.memory_model && calibration.planner && (
            <section className="mt-16 max-w-reading">
              <h2 className="text-xs uppercase tracking-wide text-ink-500">
                Has it been right?
              </h2>
              <p className="mt-3 text-base text-ink-700">
                {calibration.memory_model.summary}
              </p>

              {calibration.memory_model.reliable ? (
                <dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-xs text-ink-600">
                  <dt>It predicted you would recall</dt>
                  <dd className="text-right font-mono">
                    {percent(calibration.memory_model.predicted_recall)}
                  </dd>
                  <dt>You actually recalled</dt>
                  <dd className="text-right font-mono">
                    {percent(calibration.memory_model.actual_recall)}
                  </dd>
                  <dt>Reviews scored</dt>
                  <dd className="text-right font-mono">
                    {calibration.memory_model.reviews_scored}
                  </dd>
                </dl>
              ) : (
                <p className="mt-2 text-sm text-ink-500">
                  Not enough history to claim anything yet. The numbers appear once
                  there are enough scored reviews to mean something.
                </p>
              )}

              <p className="mt-6 text-base text-ink-700">
                {calibration.planner.summary}
              </p>

              <div className="mt-8 border-t border-line pt-6">
                <h3 className="text-sm text-ink-900">Fit the schedule to you</h3>
                <p className="mt-2 text-sm text-ink-600">
                  The memory model ships with parameters fitted on a large public
                  dataset. They are a good starting point and they are not you. This
                  searches your earlier reviews for better ones and checks them
                  against your later ones — adopting them only if they win on
                  reviews the search never saw.
                </p>
                <button
                  type="button"
                  onClick={fit}
                  disabled={fitting}
                  className="mt-4 rounded-md border border-line px-4 py-2 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
                >
                  {fitting ? 'Fitting…' : 'Fit to my history'}
                </button>
                {fitResult && (
                  <p className="mt-3 text-sm text-ink-700">{fitResult}</p>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </Shell>
  );
}
