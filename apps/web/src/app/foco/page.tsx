'use client';

/**
 * Modo TDAH — the home. Almost empty on purpose.
 *
 * One task, the reason it is the task (from real numbers), how long it takes,
 * a duration, and one button. If a sitting is already under way — here or on
 * another device — the button continues it instead. No rail, no lists, no
 * feed: the way back to the rest of NOEMA is one quiet link at the top.
 *
 * The task is `GET /me/next-activity`, the same answer any screen gets; the
 * sitting is `POST /focus/sessions`. Nothing here is a second engine.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { FocoGuide, reasonLabel, sessionTaskLabel, taskLabel } from '@/components/foco/Foco';
import { Button } from '@/components/ui/Button';
import { Loading } from '@/components/ui/Loading';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import {
  ApiError,
  api,
  type FocusMinutes,
  type FocusSession,
  type NextActivity,
} from '@/lib/api';
import { humanError } from '@/lib/errors';
import { trackOnce } from '@/lib/analytics';
import { useT } from '@/lib/i18n';

type Duration = FocusMinutes | 'auto';
const DURATIONS: Duration[] = [5, 10, 15, 25, 'auto'];

export default function FocoHomePage() {
  const t = useT();
  const router = useRouter();
  const [current, setCurrent] = useState<FocusSession | null>(null);
  const [activity, setActivity] = useState<NextActivity | null>(null);
  const [loading, setLoading] = useState(true);
  const [duration, setDuration] = useState<Duration>('auto');
  const [goal, setGoal] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    trackOnce('adhd_mode_enabled', { via: 'foco' });
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.focusCurrent(), api.nextActivity()])
      .then(([open, next]) => {
        if (cancelled) return;
        setCurrent(open);
        setActivity(next);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isUnauthorized) {
          router.push('/login?next=/foco');
          return;
        }
        setError(t.foco.loadFailed);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router, t]);

  async function begin(event?: FormEvent) {
    event?.preventDefault();
    if (busy) return;
    if (activity?.kind === 'start' && !goal.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const started = await api.focusStart(duration === 'auto' ? null : duration, goal.trim());
      router.push(`/foco/sessao?id=${encodeURIComponent(started.id)}`);
    } catch (err) {
      setError(humanError(err, t, 'save'));
      setBusy(false);
    }
  }

  async function endCurrent() {
    if (!current || busy) return;
    setBusy(true);
    try {
      await api.focusAbandon(current.id);
      setCurrent(null);
      setActivity(await api.nextActivity());
    } catch (err) {
      setError(humanError(err, t, 'save'));
    } finally {
      setBusy(false);
    }
  }

  const estimate =
    duration === 'auto' ? (activity?.minutes_estimate ?? null) : duration;

  return (
    <div className="flex min-h-screen flex-col bg-surface px-6 pb-10 pt-[max(1.5rem,env(safe-area-inset-top))]">
      <nav className="mx-auto w-full max-w-md">
        <Link
          href="/today"
          className="inline-flex min-h-11 items-center text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
          data-foco-leave
        >
          ← {t.foco.backToNormal}
        </Link>
      </nav>

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-10" data-foco-home>
        <div className="flex items-center gap-3">
          <FocoGuide state={busy ? 'thinking' : 'focused'} />
          <p className="font-mono text-xs uppercase tracking-[0.12em] text-signal">{t.foco.name}</p>
        </div>

        {loading ? (
          <Loading className="mt-10" />
        ) : current ? (
          <section className="mt-8" data-foco-current>
            <h1 className="text-base text-ink-600">{t.foco.yourFocus}</h1>
            <p className="mt-2 font-display text-3xl leading-tight text-ink-900">
              {sessionTaskLabel(current, t)}
            </p>
            <p className="mt-3 text-sm text-ink-500">
              {t.foco.pausedNote(current.steps_done, current.steps_total)}
            </p>
            <Button
              variant="primary"
              size="lg"
              className="mt-8 w-full"
              onClick={() => router.push(`/foco/sessao?id=${encodeURIComponent(current.id)}`)}
              data-foco-continue
            >
              {t.foco.continueSession}
            </Button>
            <button
              type="button"
              onClick={() => void endCurrent()}
              disabled={busy}
              className="mt-4 min-h-11 w-full text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
            >
              {t.foco.endSession}
            </button>
          </section>
        ) : activity ? (
          <form className="mt-8" onSubmit={(event) => void begin(event)} data-foco-next={activity.kind}>
            <h1 className="text-base text-ink-600">{t.foco.yourFocus}</h1>
            {activity.kind === 'start' ? (
              <>
                <label htmlFor="foco-goal" className="mt-2 block font-display text-3xl leading-tight text-ink-900">
                  {t.foco.goalLabel}
                </label>
                <input
                  id="foco-goal"
                  value={goal}
                  onChange={(event) => setGoal(event.target.value)}
                  placeholder={t.foco.goalPlaceholder}
                  maxLength={400}
                  className="mt-4 h-12 w-full rounded-md border border-line bg-raised px-3 text-base text-ink-900 outline-none transition-colors duration-fast placeholder:text-ink-400 focus:border-primary"
                />
              </>
            ) : (
              <>
                <p className="mt-2 font-display text-3xl leading-tight text-ink-900" data-foco-task>
                  {taskLabel(activity, t)}
                </p>
                <p className="mt-3 text-sm text-ink-500" data-foco-reason>
                  {reasonLabel(activity, t)}
                </p>
              </>
            )}

            <div className="mt-8">
              <p className="text-sm text-ink-600">{t.foco.duration}</p>
              <SegmentedControl
                label={t.foco.duration}
                value={duration}
                onChange={setDuration}
                className="mt-2"
                options={DURATIONS.map((value) => ({
                  value,
                  label: value === 'auto' ? t.foco.auto : t.foco.minutes(value),
                }))}
              />
              {estimate !== null && (
                <p className="mt-2 text-xs text-ink-400" data-foco-estimate>
                  {t.foco.about(estimate)}
                </p>
              )}
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="mt-8 w-full"
              disabled={activity.kind === 'start' && !goal.trim()}
              busy={busy ? t.common.loading : undefined}
              data-foco-begin
            >
              {t.foco.begin}
            </Button>
          </form>
        ) : null}

        {error && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {error}
          </p>
        )}
      </main>

      <p className="mx-auto w-full max-w-md text-xs text-ink-400">{t.foco.tagline}</p>
    </div>
  );
}
