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
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

const BAND = [
  { floor: 80, id: 'solid', tone: 'text-positive' },
  { floor: 60, id: 'holding', tone: 'text-ink-700' },
  { floor: 40, id: 'shaky', tone: 'text-ink-600' },
  { floor: 0, id: 'weak', tone: 'text-critical' },
] as const;

function band(score: number) {
  return BAND.find((b) => score >= b.floor) ?? BAND[BAND.length - 1]!;
}

function bandLabel(score: number, t: Dict): string {
  return t.progress.bands[band(score).id];
}

function percent(value: unknown): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';
}

export default function ProgressPage() {
  const router = useRouter();
  const t = useT();
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
      setError(err instanceof Error ? err.message : t.progress.couldNotLoad);
    } finally {
      setLoading(false);
    }
  }, [router, t]);

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
      setFitResult(err instanceof Error ? err.message : t.progress.fitFailed);
    } finally {
      setFitting(false);
    }
  }

  const busiest = Math.max(1, ...forecast.map((d) => d.due));

  return (
    <Shell>
      <h1 className="font-display text-2xl text-ink-900">{t.progress.title}</h1>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">{t.common.loading}</p>
      ) : (
        <>
          <section className="mt-12 max-w-reading">
            <h2 className="text-xs uppercase tracking-wide text-ink-500">
              {t.progress.whatYouKnow}
            </h2>

            {mastery.length === 0 ? (
              <p className="mt-3 text-base text-ink-600">
                {t.progress.emptyMastery}
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
                              {t.progress.provisional}
                            </span>
                          )}
                        </span>
                        <span
                          className={`shrink-0 font-mono text-sm ${band(shown).tone}`}
                        >
                          {shown}
                          <span className="ml-2 text-xs text-ink-400">
                            {bandLabel(shown, t)}
                          </span>
                        </span>
                      </button>

                      {expanded && (
                        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-l-2 border-line pl-4 text-xs text-ink-600">
                          <dt>{t.progress.howOftenRight}</dt>
                          <dd className="text-right font-mono">
                            {percent(row.components.competence)}
                          </dd>
                          <dt>{t.progress.recallNow}</dt>
                          <dd className="text-right font-mono">
                            {percent(row.components.retrievability)}
                          </dd>
                          <dt>{t.progress.fromPrereqs}</dt>
                          <dd className="text-right font-mono">
                            {percent(row.components.prior_mean)}
                          </dd>
                          <dt>{t.progress.evidence}</dt>
                          <dd className="text-right font-mono">
                            {typeof row.components.effective_observations === 'number'
                              ? row.components.effective_observations.toFixed(1)
                              : '—'}{' '}
                            {t.progress.answers}
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
              {t.progress.whatIsComing}
            </h2>
            {forecast.every((d) => d.due === 0) ? (
              <p className="mt-3 text-base text-ink-600">
                {t.progress.nothingScheduled}
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
                  {t.progress.reviewsOver(
                    forecast.reduce((sum, d) => sum + d.due, 0),
                    forecast.length,
                    busiest,
                  )}
                </p>
              </>
            )}
          </section>

          {calibration?.memory_model && calibration.planner && (
            <section className="mt-16 max-w-reading">
              <h2 className="text-xs uppercase tracking-wide text-ink-500">
                {t.progress.hasItBeenRight}
              </h2>
              <p className="mt-3 text-base text-ink-700">
                {calibration.memory_model.summary}
              </p>

              {calibration.memory_model.reliable ? (
                <dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-xs text-ink-600">
                  <dt>{t.progress.predicted}</dt>
                  <dd className="text-right font-mono">
                    {percent(calibration.memory_model.predicted_recall)}
                  </dd>
                  <dt>{t.progress.actual}</dt>
                  <dd className="text-right font-mono">
                    {percent(calibration.memory_model.actual_recall)}
                  </dd>
                  <dt>{t.progress.reviewsScored}</dt>
                  <dd className="text-right font-mono">
                    {calibration.memory_model.reviews_scored}
                  </dd>
                </dl>
              ) : (
                <p className="mt-2 text-sm text-ink-500">
                  {t.progress.notEnoughHistory}
                </p>
              )}

              <p className="mt-6 text-base text-ink-700">
                {calibration.planner.summary}
              </p>

              <div className="mt-8 border-t border-line pt-6">
                <h3 className="text-sm text-ink-900">{t.progress.fitTitle}</h3>
                <p className="mt-2 text-sm text-ink-600">
                  {t.progress.fitLede}
                </p>
                <button
                  type="button"
                  onClick={fit}
                  disabled={fitting}
                  className="mt-4 rounded-md border border-line px-4 py-2 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
                >
                  {fitting ? t.progress.fitting : t.progress.fitCta}
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
