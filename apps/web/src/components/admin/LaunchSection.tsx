'use client';

/**
 * The launch funnel, as the database counts it (`GET /admin/launch`):
 * signups, activation, active learners, successful sessions and the North
 * Star, retention, paying users, and what the AI cost. Small tables and bar
 * strips in plain SVG; no chart library. A dash is "nothing to divide by
 * yet", never zero.
 */

import { useEffect, useState } from 'react';
import { api, type AdminLaunch } from '@/lib/api';
import { useT } from '@/lib/i18n';

const WINDOWS = [14, 30, 90] as const;

type Day = AdminLaunch['daily'][number];

function pct(value: number | null | undefined): string {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function ratio(value: number | null | undefined): string {
  return value == null ? '—' : value.toFixed(2);
}

function brl(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { style: 'currency', currency: 'BRL' });
}

function usd(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { style: 'currency', currency: 'USD' });
}

export function LaunchSection() {
  const t = useT();
  const copy = t.admin.launch;
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<AdminLaunch | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    api
      .adminLaunch(days)
      .then((report) => {
        if (!cancelled) setData(report);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : copy.loadError);
      });
    return () => {
      cancelled = true;
    };
  }, [days, copy.loadError]);

  return (
    <section data-admin-launch>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-mono text-xs text-ink-500">{copy.title}</h2>
        <div role="group" aria-label={copy.window} className="flex gap-1 font-mono text-xs">
          {WINDOWS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={days === n}
              onClick={() => setDays(n)}
              className={`rounded-sm px-2 py-1 transition-colors duration-state ${
                days === n ? 'bg-primary text-primary-fg' : 'text-ink-600 hover:text-ink-900'
              }`}
            >
              {copy.days(n)}
            </button>
          ))}
        </div>
      </div>

      {loadError && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {loadError}
        </p>
      )}

      {data && (
        <>
          <p className="mt-2 max-w-reading text-sm text-ink-600">{copy.note(data.days)}</p>

          <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            <Figure label={copy.signups} value={String(data.signups)} />
            <Figure
              label={copy.activation}
              value={pct(data.activation_rate)}
              hint={copy.activationOf(data.activation_cohort_activated, data.activation_cohort)}
            />
            <Figure label={copy.dauWau} value={`${data.dau} · ${data.wau}`} />
            <Figure label={copy.northStar} value={ratio(data.north_star)} hint={copy.northStarNote} />
            <Figure
              label={copy.retention}
              value={`${pct(data.d1_rate)} · ${pct(data.d7_rate)}`}
              hint={copy.retentionOf(data.d1_retained, data.d1_cohort, data.d7_retained, data.d7_cohort)}
            />
            <Figure label={`${copy.paying} · ${copy.mrr}`} value={`${data.paying_users} · ${brl(data.mrr_cents)}`} />
            <Figure label={copy.aiCost} value={usd(data.ai_cost_cents)} hint={`${data.ai_calls} ${t.admin.ops.aiCalls}`} />
            <Figure label={copy.aiFailureRate} value={pct(data.ai_failure_rate)} hint={`${data.ai_failures} ${t.admin.ops.aiFailures}`} />
          </dl>

          <h3 className="mt-10 font-mono text-xs text-ink-500">{copy.daily}</h3>
          <div className="mt-3 grid max-w-reading gap-3 text-sm">
            <Strip label={copy.series.signups} days={data.daily} pick={(d) => d.signups} />
            <Strip label={copy.series.dau} days={data.daily} pick={(d) => d.dau} />
            <Strip label={copy.series.lessons} days={data.daily} pick={(d) => d.lessons_started} />
            <Strip label={copy.series.successful} days={data.daily} pick={(d) => d.successful_sessions} />
            <Strip label={copy.series.aiCalls} days={data.daily} pick={(d) => d.ai_calls} />
          </div>

          <div className="mt-10 grid gap-10 md:grid-cols-2">
            <div>
              <h3 className="font-mono text-xs text-ink-500">{copy.weekly}</h3>
              <table className="mt-3 w-full text-sm" data-launch-weekly>
                <thead>
                  <tr className="border-b border-line text-left text-xs text-ink-500">
                    <th className="pb-2 font-normal">{copy.week}</th>
                    <th className="pb-2 text-right font-normal">{copy.active}</th>
                    <th className="pb-2 text-right font-normal">{copy.successful}</th>
                    <th className="pb-2 text-right font-normal">{copy.northStar}</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {data.weekly.map((w) => (
                    <tr key={w.week_start} className="border-b border-line">
                      <td className="py-1.5 text-ink-600">{w.week_start}</td>
                      <td className="py-1.5 text-right text-ink-900">{w.active_learners}</td>
                      <td className="py-1.5 text-right text-ink-900">{w.successful_sessions}</td>
                      <td className="py-1.5 text-right text-ink-900">{ratio(w.north_star)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <h3 className="font-mono text-xs text-ink-500">{copy.sessions}</h3>
              <dl className="mt-3 grid gap-2 text-sm">
                {(['teaching', 'focus', 'review'] as const).map((kind) => (
                  <Line key={kind} label={copy.kinds[kind]} value={String(data.successful_sessions[kind] ?? 0)} />
                ))}
                <Line label={copy.lessons} value={`${data.lessons_started} · ${data.lessons_completed}`} />
                <Line label={copy.focus} value={`${data.focus_started} · ${data.focus_completed}`} />
                <Line label={copy.feedback} value={String(data.feedback_reports)} />
              </dl>
            </div>
          </div>

          <h3 className="mt-10 font-mono text-xs text-ink-500">{copy.revenue}</h3>
          <table className="mt-3 w-full max-w-reading text-sm" data-launch-revenue>
            <thead>
              <tr className="border-b border-line text-left text-xs text-ink-500">
                <th className="pb-2 font-normal">{copy.plan}</th>
                <th className="pb-2 text-right font-normal">{copy.paying}</th>
                <th className="pb-2 text-right font-normal">{copy.comped}</th>
                <th className="pb-2 text-right font-normal">{copy.price}</th>
                <th className="pb-2 text-right font-normal">{copy.mrr}</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {data.revenue.map((r) => (
                <tr key={r.plan} className="border-b border-line">
                  <td className="py-1.5 text-ink-600">{r.plan}</td>
                  <td className="py-1.5 text-right text-ink-900">{r.paying}</td>
                  <td className="py-1.5 text-right text-ink-900">{r.comped}</td>
                  <td className="py-1.5 text-right text-ink-900">{brl(r.price_cents)}</td>
                  <td className="py-1.5 text-right text-ink-900">{brl(r.mrr_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-10 max-w-reading border-l-2 border-line pl-4 text-xs text-ink-500">
            <p className="font-medium uppercase tracking-wide">{copy.definitions}</p>
            <dl className="mt-2 grid gap-1.5">
              {Object.entries(data.definitions).map(([name, text]) => (
                <div key={name}>
                  <dt className="inline font-mono text-ink-600">{name}</dt> <dd className="inline">{text}</dd>
                </div>
              ))}
            </dl>
            {data.not_recorded.length > 0 && (
              <p className="mt-3">
                {copy.notRecorded} {data.not_recorded.join(', ')}
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="font-mono text-lg text-ink-900">{value}</dd>
      {hint && <dd className="mt-0.5 text-xs text-ink-500">{hint}</dd>}
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-line pb-2">
      <dt className="text-ink-600">{label}</dt>
      <dd className="font-mono text-ink-900">{value}</dd>
    </div>
  );
}

/**
 * One series as a strip of bars, one per day, scaled to its own maximum. The
 * total sits at the end; the day and value are in each bar's title.
 */
export function Strip({ label, days, pick }: { label: string; days: Day[]; pick: (day: Day) => number }) {
  const values = days.map(pick);
  const max = Math.max(...values, 0);
  const total = values.reduce((sum, v) => sum + v, 0);
  const width = 4;
  const gap = 1;
  const height = 28;
  return (
    <div className="grid grid-cols-[9rem_1fr_3.5rem] items-end gap-3" data-strip={label}>
      <span className="text-ink-600">{label}</span>
      <svg
        role="img"
        aria-label={`${label}: ${total}`}
        viewBox={`0 0 ${values.length * (width + gap)} ${height}`}
        preserveAspectRatio="none"
        className="h-7 w-full"
      >
        <line x1="0" y1={height - 0.5} x2={values.length * (width + gap)} y2={height - 0.5} className="stroke-line" />
        {values.map((v, i) => {
          const h = max > 0 ? Math.max((v / max) * (height - 2), v > 0 ? 1.5 : 0) : 0;
          return (
            <rect
              key={days[i]!.day}
              x={i * (width + gap)}
              y={height - 1 - h}
              width={width}
              height={h}
              className="fill-primary"
            >
              <title>{`${days[i]!.day}: ${v}`}</title>
            </rect>
          );
        })}
      </svg>
      <span className="text-right font-mono text-ink-900">{total}</span>
    </div>
  );
}
