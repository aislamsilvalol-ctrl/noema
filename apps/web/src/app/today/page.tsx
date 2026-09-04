'use client';

/**
 * Home. The one question it answers is "where was I", not "what fits in 30
 * minutes" — that was the audit's clearest finding about this screen.
 *
 * So it leads with Continue learning (the last open lesson, read from
 * `/ai/sessions/latest`), then Reviews due, then Your learning, and only then
 * the time-budget planner — which is unchanged, just no longer the first thing
 * a returning learner sees. Every section reads existing endpoints; none of the
 * planning or scheduling logic is touched.
 */

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Mino } from '@/components/mino/Mino';
import { Shell } from '@/components/Shell';
import { ButtonLink } from '@/components/ui/Button';
import { PathStrip } from '@/components/ui/PathStrip';
import {
  ApiError,
  api,
  type Notebook,
  type SessionPlan,
  type Subject,
  type TeachingSession,
} from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

const BUDGETS = [10, 20, 30, 45, 60];

/** A goal typed as a sentence, cut at a word so it can stand as a title. */
function titleFrom(goal: string): string {
  const oneLine = goal.replace(/\s+/g, ' ').trim();
  if (oneLine.length <= 72) return oneLine;
  const cut = oneLine.slice(0, 72);
  return `${cut.slice(0, cut.lastIndexOf(' ') > 40 ? cut.lastIndexOf(' ') : 72).replace(/[.,;:]$/, '')}…`;
}

function greeting(t: Dict): string {
  const hour = new Date().getHours();
  if (hour < 12) return t.today.greetingMorning;
  if (hour < 18) return t.today.greetingAfternoon;
  return t.today.greetingEvening;
}

export default function TodayPage() {
  const router = useRouter();
  const t = useT();

  const [lesson, setLesson] = useState<TeachingSession | null>(null);
  const [due, setDue] = useState<number | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [homeLoading, setHomeLoading] = useState(true);
  const [homeError, setHomeError] = useState<string | null>(null);

  const [minutes, setMinutes] = useState(30);
  const [plan, setPlan] = useState<SessionPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [planError, setPlanError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Each panel is allowed to fail on its own — a missing lesson must not blank
    // the reviews count, and vice versa. `latestSession` is newest, so it leads.
    Promise.allSettled([
      api.latestSession(),
      api.dueCards(undefined, 200),
      api.subjects(),
      api.notebooks(),
    ]).then((results) => {
      if (cancelled) return;
      const [session, dueCards, subjectPage, notebookPage] = results;
      if (session.status === 'fulfilled') setLesson(session.value);
      if (dueCards.status === 'fulfilled') setDue(dueCards.value.length);
      if (subjectPage.status === 'fulfilled') setSubjects(subjectPage.value.items);
      if (notebookPage.status === 'fulfilled') setNotebooks(notebookPage.value.items);

      const unauthorized = results.some(
        (r) => r.status === 'rejected' && r.reason instanceof ApiError && r.reason.isUnauthorized,
      );
      if (unauthorized) {
        router.push('/login');
        return;
      }
      if (results.every((r) => r.status === 'rejected')) {
        setHomeError(t.today.couldNotPlan);
      }
      setHomeLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [router, t]);

  const loadPlan = useCallback(
    async (budget: number) => {
      setPlanLoading(true);
      try {
        setPlan(await api.plan(budget));
        setPlanError(null);
      } catch (err) {
        if (err instanceof ApiError && err.isUnauthorized) {
          router.push('/login');
          return;
        }
        setPlanError(humanError(err, t, 'load'));
      } finally {
        setPlanLoading(false);
      }
    },
    [router, t],
  );

  useEffect(() => {
    void loadPlan(minutes);
  }, [loadPlan, minutes]);

  const subjectName = lesson?.subject || lesson?.current_topic || '';
  const hasLibrary = subjects.length > 0 || notebooks.length > 0;

  return (
    <Shell>
      <header className="flex items-center gap-4">
        <Mino state="idle" size="md" className="hidden sm:block" />
        <h1 className="font-display text-2xl text-ink-900">{greeting(t)}</h1>
      </header>

      {homeError && (
        <p role="alert" className="mt-6 text-sm text-critical">
          {homeError}
        </p>
      )}

      {/* Continue learning — the lead. A live lesson resumes it; otherwise the
          invitation to start one, which is the real first-run call to action. */}
      <section className="mt-10 max-w-reading">
        {homeLoading ? (
          <p className="text-sm text-ink-500">{t.common.loading}</p>
        ) : lesson ? (
          <div className="rounded-lg border border-line bg-raised p-6 shadow-elevation-1">
            <p className="text-xs uppercase tracking-wide text-ink-500">
              {t.today.continueTitle}
            </p>
            <h2 className="mt-2 font-display text-xl text-ink-900">
              {subjectName || titleFrom(lesson.learning_goal)}
            </h2>
            {lesson.current_concept && (
              <p className="mt-1 text-sm text-ink-600">{t.today.onConcept(lesson.current_concept)}</p>
            )}
            <PathStrip plan={lesson.plan} className="mt-4" />
            <ButtonLink href="/chat" variant="primary" className="mt-5">
              {subjectName
                ? t.today.continueResume(subjectName)
                : t.today.continueGeneric}
            </ButtonLink>
          </div>
        ) : (
          <div className="rounded-lg border border-line p-6">
            <p className="text-xs uppercase tracking-wide text-ink-500">
              {t.today.startLearningTitle}
            </p>
            <h2 className="mt-2 font-display text-xl text-ink-900">
              {t.today.startLearningCta}
            </h2>
            <p className="mt-2 text-base text-ink-600">{t.today.startLearningBody}</p>
            <ButtonLink href="/learn/new" variant="primary" className="mt-5">
              {t.today.startLearningCta}
            </ButtonLink>
          </div>
        )}
      </section>

      {/* Reviews due — a count and one action, only when there is something. */}
      {!homeLoading && due !== null && (
        <section className="mt-12 max-w-reading">
          <p className="text-xs uppercase tracking-wide text-ink-500">{t.today.reviewsTitle}</p>
          {due > 0 ? (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-y border-line py-4">
              <span className="text-md text-ink-900">{t.today.reviewsDue(due)}</span>
              <ButtonLink href="/review" variant="secondary" size="sm">
                {t.today.reviewsCta}
              </ButtonLink>
            </div>
          ) : (
            <p className="mt-2 text-sm text-ink-600">{t.today.reviewsNone}</p>
          )}
        </section>
      )}

      {/* Your learning — subjects and notebooks as a short list, not a card grid. */}
      {!homeLoading && hasLibrary && (
        <section className="mt-12 max-w-reading">
          <p className="text-xs uppercase tracking-wide text-ink-500">{t.today.yourLearning}</p>
          <ul className="mt-3 divide-y divide-line border-y border-line">
            {notebooks.slice(0, 6).map((notebook) => (
              <li key={notebook.id}>
                <Link
                  href={`/notebooks/${notebook.id}`}
                  className="group flex items-baseline justify-between py-3 transition-colors duration-state"
                >
                  <span className="text-sm text-ink-800 group-hover:text-accent">
                    {notebook.title}
                  </span>
                  <span className="text-xs text-accent">{t.today.openNotebook} →</span>
                </Link>
              </li>
            ))}
          </ul>
          {notebooks.length === 0 && subjects.length > 0 && (
            <Link href="/library" className="mt-3 inline-block text-sm text-accent">
              {t.nav.library} →
            </Link>
          )}
        </section>
      )}

      {/* Plan a session — the former lead, now a deliberate choice below the
          fold. The planning logic is unchanged. */}
      <section className="mt-16 max-w-reading border-t border-line pt-8">
        <p className="text-xs uppercase tracking-wide text-ink-500">{t.today.planTitle}</p>
        <p className="mt-2 text-sm text-ink-600">{t.today.planLede}</p>

        <div className="mt-4 flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-ink-500">{t.today.iHave}</span>
          {BUDGETS.map((budget) => (
            <button
              key={budget}
              type="button"
              onClick={() => setMinutes(budget)}
              className={`rounded-md px-2.5 py-1 text-sm transition-colors duration-state ${
                budget === minutes ? 'bg-primary text-primary-fg' : 'text-ink-600 hover:text-ink-900'
              }`}
            >
              {budget}m
            </button>
          ))}
        </div>

        {planError && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {planError}
          </p>
        )}

        {planLoading ? (
          <p className="mt-6 text-sm text-ink-500">{t.today.planning}</p>
        ) : plan && plan.blocks.length === 0 ? (
          <p className="mt-6 text-base text-ink-600">{t.today.emptyBody}</p>
        ) : (
          plan && (
            <>
              <p className="mt-4 max-w-reading font-serif text-md text-ink-700">
                {plan.rationale}
              </p>
              <ol className="mt-6 space-y-6">
                {plan.blocks.map((block, index) => (
                  <li key={`${block.kind}-${index}`} className="border-t border-line pt-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <h3 className="text-md text-ink-900">
                        {t.today.blocks[block.kind] ?? block.kind}
                      </h3>
                      <span className="font-mono text-xs text-ink-400">
                        {block.minutes < 1 ? t.today.lessThanMinute : Math.round(block.minutes)}{' '}
                        {t.today.min}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-ink-600">{block.why}</p>
                    <p className="mt-2 text-xs text-ink-400">
                      {summarise(block.items.map((item) => item.kind), t)}
                      {block.items.some((i) => i.concept_name) && (
                        <>
                          {' · '}
                          {[
                            ...new Set(block.items.map((i) => i.concept_name).filter(Boolean)),
                          ]
                            .slice(0, 3)
                            .join(', ')}
                        </>
                      )}
                    </p>
                  </li>
                ))}
              </ol>
              <div className="mt-8 flex items-center gap-4">
                <ButtonLink href="/review" variant="primary">
                  {t.today.startSession}
                </ButtonLink>
                <span className="text-sm text-ink-500">
                  {t.today.aboutMinutes(Math.round(plan.estimated_minutes))}
                </span>
              </div>
            </>
          )
        )}
      </section>
    </Shell>
  );
}

/** "8 reviews, 2 questions" — counts by kind, in the order they appear. */
function summarise(kinds: string[], t: Dict): string {
  const counts = new Map<string, number>();
  for (const kind of kinds) counts.set(kind, (counts.get(kind) ?? 0) + 1);

  return [...counts.entries()]
    .map(([kind, count]) => t.today.countOf(count, t.today.kinds[kind] ?? kind))
    .join(', ');
}
