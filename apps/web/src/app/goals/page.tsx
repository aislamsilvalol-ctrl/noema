'use client';

/**
 * Goals with a date on them.
 *
 * The screen exists to deliver one sentence: whether the deadline holds at the
 * pace you said you have. Everything else is supporting detail. A goal feature
 * that accepts "all of pharmacology by Friday" without comment is not planning,
 * it is agreeing — and the learner finds out on Friday either way.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shell } from '@/components/Shell';
import { Mino } from '@/components/mino/Mino';
import { Button } from '@/components/ui/Button';
import { Input, Select } from '@/components/ui/Input';
import { Notice } from '@/components/ui/Notice';
import { ApiError, api, type Goal, type Notebook } from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

function humanDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  });
}

export default function GoalsPage() {
  const router = useRouter();
  const t = useT();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [notebookId, setNotebookId] = useState('');
  const [dueOn, setDueOn] = useState('');
  const [minutes, setMinutes] = useState(30);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [rows, page] = await Promise.all([api.goals(), api.notebooks()]);
      setGoals(rows);
      setNotebooks(page.items);
      if (page.items[0]) setNotebookId((current) => current || page.items[0]!.id);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(humanError(err, t, 'load'));
    } finally {
      setLoading(false);
    }
  }, [router, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await api.createGoal(notebookId, title.trim(), dueOn, minutes);
      setOpen(false);
      setTitle('');
      await load();
    } catch (err) {
      setError(humanError(err, t, 'save'));
    } finally {
      setBusy(false);
    }
  }

  async function drop(goalId: string) {
    setError(null);
    try {
      await api.deleteGoal(goalId);
      await load();
    } catch (err) {
      setError(humanError(err, t, 'save'));
    }
  }

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.goals.title}</h1>
        <Button size="sm" onClick={() => setOpen(!open)}>
          {open ? t.common.cancel : t.goals.newGoal}
        </Button>
      </header>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {open && (
        <div className="mt-8 max-w-reading rounded-lg border border-line p-5">
          <label className="block">
            <span className="font-mono text-xs text-ink-500">{t.goals.goalLabel}</span>
            <Input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t.goals.goalPlaceholder}
              // The form only exists while open, so this runs each time it
              // opens — from the header button or the empty state's action.
              autoFocus
              className="mt-1.5 block w-full"
            />
          </label>

          <div className="mt-4 flex flex-wrap gap-4">
            <label className="block">
              <span className="font-mono text-xs text-ink-500">
                {t.goals.notebook}
              </span>
              <Select
                value={notebookId}
                onChange={(event) => setNotebookId(event.target.value)}
                className="mt-1.5 block"
              >
                {notebooks.map((notebook) => (
                  <option key={notebook.id} value={notebook.id}>
                    {notebook.title}
                  </option>
                ))}
              </Select>
            </label>

            <label className="block">
              <span className="font-mono text-xs text-ink-500">{t.goals.by}</span>
              <Input
                type="date"
                value={dueOn}
                onChange={(event) => setDueOn(event.target.value)}
                className="mt-1.5 block"
              />
            </label>

            <label className="block">
              <span className="font-mono text-xs text-ink-500">
                {t.goals.minutesADay}
              </span>
              <Input
                type="number"
                min={5}
                max={480}
                value={minutes}
                onChange={(event) => setMinutes(Number(event.target.value))}
                className="mt-1.5 block w-28"
              />
            </label>
          </div>

          <Button
            variant="primary"
            className="mt-5"
            onClick={create}
            disabled={!title.trim() || !dueOn || !notebookId}
            busy={busy ? t.goals.workingOut : undefined}
          >
            {t.goals.setGoal}
          </Button>
          <p className="mt-2 text-xs text-ink-400">
            {t.goals.toldStraightAway}
          </p>
        </div>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">{t.common.loading}</p>
      ) : goals.length === 0 && !open ? (
        // A goal needs a notebook to point at; without one the form would
        // open on an empty select, so the action goes to Notes instead.
        <Notice
          kind="empty"
          title={t.goals.emptyTitle}
          body={notebooks.length > 0 ? t.goals.emptyBody : t.goals.noNotebookBody}
          action={
            notebooks.length > 0
              ? { label: t.goals.emptyAction, onClick: () => setOpen(true) }
              : { label: t.goals.noNotebookAction, href: '/library' }
          }
          mino={<Mino state="curious" size="lg" />}
        />
      ) : (
        goals.map((goal) => (
          <section key={goal.id} className="mt-12 max-w-reading">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="font-display text-xl text-ink-900">{goal.title}</h2>
              <span className="text-sm text-ink-500">
                {humanDate(goal.due_on)} · {t.goals.daysLeft(goal.days_left)}
              </span>
            </div>

            <p
              className={`mt-3 text-base ${
                goal.achieved_at
                  ? 'text-positive'
                  : goal.reachable
                    ? 'text-ink-700'
                    : 'text-critical'
              }`}
            >
              {goal.summary}
            </p>

            {!goal.reachable && !goal.achieved_at && (
              <p className="mt-2 text-sm text-ink-500">
                {t.goals.projection(
                  Math.round(goal.projected_mastery),
                  Math.round(goal.target_mastery),
                )}
              </p>
            )}

            {goal.milestones.length > 0 && (
              <ol className="mt-6 divide-y divide-line border-y border-line">
                {goal.milestones.slice(0, 12).map((milestone) => (
                  <li
                    key={milestone.concept_id}
                    className="flex items-baseline justify-between py-2.5"
                  >
                    <span className="min-w-0 pr-4 text-sm text-ink-800">
                      <span className="mr-3 font-mono text-xs text-ink-400">
                        d{milestone.day}
                      </span>
                      {milestone.name}
                    </span>
                    <span className="shrink-0 font-mono text-xs text-ink-400">
                      {Math.round(milestone.from_mastery)} →{' '}
                      {Math.round(milestone.to_mastery)} ·{' '}
                      {Math.round(milestone.estimated_minutes)}m
                    </span>
                  </li>
                ))}
              </ol>
            )}

            {goal.milestones.length > 12 && (
              <p className="mt-2 text-xs text-ink-400">
                {t.goals.andMore(goal.milestones.length - 12)}
              </p>
            )}

            <button
              type="button"
              onClick={() => void drop(goal.id)}
              className="mt-4 text-xs text-ink-500 transition-colors duration-state hover:text-critical"
            >
              {t.goals.dropGoal}
            </button>
          </section>
        ))
      )}
    </Shell>
  );
}
