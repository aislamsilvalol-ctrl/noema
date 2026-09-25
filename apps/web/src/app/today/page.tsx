'use client';

/**
 * Home. One ordered answer to "what is most useful to do now", top to bottom:
 * how much today holds, the lesson to continue, the reviews about to be
 * forgotten, the weakest concept with enough evidence to trust the number,
 * what has grown, and the one thing Mino remembers about where we stopped.
 *
 * Everything is composed on the client from endpoints that already exist —
 * the audit's point that "today" is a composition first and an engine change
 * second. Nothing is estimated where a real number exists, and every estimate
 * says it is one. The budget planner stays, folded under a <details>, so it
 * offers a fixed block without competing with the answer above it.
 *
 * A brand-new account (`firstRun`) sees one invitation and no planner call.
 */

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Mino } from '@/components/mino/Mino';
import { Shell } from '@/components/Shell';
import { ButtonLink } from '@/components/ui/Button';
import { PathStrip } from '@/components/ui/PathStrip';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { JourneyCard } from '@/components/professor/JourneyCard';
import { FocusHome } from '@/components/professor/FocusHome';
import { Loading } from '@/components/ui/Loading';
import { useLearningMode } from '@/lib/useLearningMode';
import {
  ApiError,
  api,
  type Journey,
  type LessonSummary,
  type Mastery,
  type Notebook,
  type SessionPlan,
  type Subject,
  type TeachingSession,
} from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';
import { journeyHref, lessonHref, NEW_LESSON } from '@/lib/lessonLinks';
import { rememberPrefill } from '@/lib/prefill';
import { titleFrom } from '@/lib/text';
import type { Dict } from '@/locales/en';

const BUDGETS = [10, 20, 30, 45, 60];

// Our own estimate for a review, used only when the planner has not said
// otherwise — and always shown with "≈" so it never reads as measured.
const MINUTES_PER_CARD = 0.5;

// A weak concept is only named when the number can be trusted: enough
// observations behind it, and low enough to be worth a lesson.
const WEAK_MIN_EVIDENCE = 4;
const WEAK_BELOW = 60;

function greeting(t: Dict): string {
  const hour = new Date().getHours();
  if (hour < 12) return t.today.greetingMorning;
  if (hour < 18) return t.today.greetingAfternoon;
  return t.today.greetingEvening;
}

/**
 * How long the due reviews take. The planner's number wins when it has one:
 * the minutes of its blocks that hold reviews are its estimate for exactly
 * these cards. Its total is not used — it covers the whole budget, not the
 * reviews — so without a review block the fallback is ours, marked as such.
 */
function reviewMinutes(due: number, plan: SessionPlan | null): { minutes: number; approx: boolean } {
  if (due === 0) return { minutes: 0, approx: false };
  const planned = (plan?.blocks ?? [])
    .filter((block) => block.items.some((item) => item.kind === 'card_review'))
    .reduce((sum, block) => sum + block.minutes, 0);
  if (planned > 0) return { minutes: Math.max(1, Math.round(planned)), approx: false };
  return { minutes: Math.max(1, Math.round(due * MINUTES_PER_CARD)), approx: true };
}

/** The one sentence Mino remembers, from the newest fold of the journey's memory. */
function minoRemembers(journey: Journey | null, t: Dict): string | null {
  const latest = journey?.memory?.[journey.memory.length - 1];
  const summary = (latest?.summary ?? {}) as Record<string, unknown>;
  const next = typeof summary.next_step === 'string' ? summary.next_step.trim() : '';
  if (next) return t.today.minoNextStep(next);
  const last = typeof summary.last_taught === 'string' ? summary.last_taught.trim() : '';
  if (last) return t.today.minoLastTaught(last);
  return null;
}

export default function TodayPage() {
  const router = useRouter();
  const t = useT();

  const [lesson, setLesson] = useState<TeachingSession | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [mastery, setMastery] = useState<Mastery[]>([]);
  const { mode, minutes: budget, loaded: budgetLoaded } = useLearningMode();
  const [due, setDue] = useState<number | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [openLessons, setOpenLessons] = useState<LessonSummary[]>([]);
  const [homeLoading, setHomeLoading] = useState(true);
  const [homeError, setHomeError] = useState<string | null>(null);

  const [minutes, setMinutes] = useState(30);
  const [plan, setPlan] = useState<SessionPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
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
      api.latestJourney(),
      api.mastery(),
      api.journeys(),
      api.openLessons(),
    ]).then((results) => {
      if (cancelled) return;
      const [session, dueCards, subjectPage, notebookPage, latestJourney, scores, trips, open] =
        results;
      if (open.status === 'fulfilled') setOpenLessons(open.value);
      if (session.status === 'fulfilled') setLesson(session.value);
      if (latestJourney.status === 'fulfilled') setJourney(latestJourney.value);
      if (dueCards.status === 'fulfilled') setDue(dueCards.value.length);
      if (subjectPage.status === 'fulfilled') setSubjects(subjectPage.value.items);
      if (notebookPage.status === 'fulfilled') setNotebooks(notebookPage.value.items);
      if (scores.status === 'fulfilled') setMastery(scores.value);
      if (trips.status === 'fulfilled') setJourneys(trips.value);

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

  const subjectName = lesson?.subject || lesson?.current_topic || '';
  const hasLibrary = subjects.length > 0 || notebooks.length > 0;
  // A brand-new account has nothing to plan or review. One invitation, no
  // planner call, and no "nothing is due" beside "start learning".
  const firstRun = !homeLoading && !hasLibrary && !lesson && !journey;
  const returning = !homeLoading && !firstRun;
  const hasLesson = journey !== null || lesson !== null;

  useEffect(() => {
    if (homeLoading || firstRun) return;
    void loadPlan(minutes);
  }, [firstRun, homeLoading, loadPlan, minutes]);

  const review = reviewMinutes(due ?? 0, plan);
  const rest = Math.max(0, budget - review.minutes);

  const weak =
    [...mastery]
      .filter((m) => m.components.effective_observations >= WEAK_MIN_EVIDENCE && m.mastery < WEAK_BELOW)
      .sort((a, b) => a.mastery - b.mastery)[0] ?? null;

  const conceptsSeen = journeys.flatMap((j) => j.concepts);
  const masteredAll = conceptsSeen.filter((c) => c.state === 'mastered').length;

  const remembered = minoRemembers(journey, t);

  return (
    <Shell>
      <header className="flex items-center gap-3">
        <Mino state="idle" size="sm" className="hidden sm:block" />
        <h1 className="font-display text-2xl text-ink-900">{greeting(t)}</h1>
      </header>

      {homeError && (
        <p role="alert" className="mt-6 text-sm text-critical">
          {homeError}
        </p>
      )}

      {/* Today — the budget from the learner's own preference, the due count
          as it is, and the lesson filling what is left. Drawn only once the
          preference has loaded, so the line never shows a default budget. */}
      {returning && budgetLoaded && (
        <section className="mt-10 max-w-reading" data-today-line>
          <p className="font-display text-xl text-ink-900">{t.today.todayLine(budget)}</p>
          {due !== null && (
            <p className="mt-1 text-sm text-ink-600">
              {due > 0
                ? t.today.todayComposition(due, review.minutes, review.approx, rest, hasLesson)
                : hasLesson
                  ? t.today.todayLessonOnly(budget)
                  : t.today.todayNothing}
            </p>
          )}
        </section>
      )}

      {/* Continue — the primary action. A journey resumes it; an older lesson
          resumes it; otherwise the invitation to start, which is the real
          first-run call to action. */}
      <section className={`max-w-reading ${returning ? 'mt-8' : 'mt-10'}`}>
        {homeLoading ? (
          <Loading mino />
        ) : mode === 'focus' ? (
          <FocusHome
            journey={journey}
            href={journey ? journeyHref(journey.id, openLessons) : NEW_LESSON}
            minutes={budget}
            due={due ?? 0}
          />
        ) : journey ? (
          <>
            <p className="font-mono text-xs text-ink-500">{t.today.continueTitle}</p>
            <JourneyCard
              journey={journey}
              className="mt-3"
              cta={{
                href: journeyHref(journey.id, openLessons),
                label: t.today.continueResume(journey.subject),
              }}
            />
          </>
        ) : lesson ? (
          <div className="border-t border-line pt-5">
            <p className="font-mono text-xs text-ink-500">{t.today.continueTitle}</p>
            <h2 className="mt-2 font-display text-xl text-ink-900">
              {subjectName || titleFrom(lesson.learning_goal)}
            </h2>
            {lesson.current_concept && (
              <p className="mt-1 text-sm text-ink-600">{t.today.onConcept(lesson.current_concept)}</p>
            )}
            <PathStrip plan={lesson.plan} className="mt-4" />
            <ButtonLink href={lessonHref(lesson.id)} variant="primary" className="mt-5">
              {subjectName ? t.today.continueResume(subjectName) : t.today.continueGeneric}
            </ButtonLink>
          </div>
        ) : (
          <div className="border-t border-line pt-5">
            <p className="font-mono text-xs text-ink-500">{t.today.startLearningTitle}</p>
            <h2 className="mt-2 font-display text-xl text-ink-900">{t.today.startLearningCta}</h2>
            <p className="mt-2 text-base text-ink-600">{t.today.startLearningBody}</p>
            <ButtonLink href="/learn/new" variant="primary" className="mt-5">
              {t.today.startLearningCta}
            </ButtonLink>
            {firstRun && <p className="mt-4 text-sm text-ink-500">{t.today.firstRunNote}</p>}
          </div>
        )}
      </section>

      {/* Below the fold: a hairline list, each row one fact and at most one
          secondary action. A row with nothing true to say is not drawn. */}
      {returning && (
        <ul className="mt-12 max-w-reading divide-y divide-line border-y border-line">
          {due !== null && due > 0 && (
            <li className="flex flex-wrap items-center justify-between gap-3 py-5" data-review-row>
              <div>
                <p className="font-mono text-xs text-ink-500">{t.today.reviewsTitle}</p>
                <p className="mt-1 text-md text-ink-900">
                  {t.today.reviewLine(due, review.minutes, review.approx)}
                </p>
              </div>
              <ButtonLink href="/review" variant="secondary" size="sm">
                {t.today.reviewsCta}
              </ButtonLink>
            </li>
          )}

          {weak && (
            <li className="flex flex-wrap items-center justify-between gap-3 py-5" data-weak-row>
              <div>
                <p className="font-mono text-xs text-ink-500">{t.today.weakTitle}</p>
                <p className="mt-1 text-md text-ink-900">
                  {t.today.weakLine(weak.concept_name, Math.round(weak.mastery))}
                </p>
              </div>
              <ButtonLink
                href={NEW_LESSON}
                variant="secondary"
                size="sm"
                onClick={() => rememberPrefill(t.today.weakMessage(weak.concept_name), true)}
              >
                {t.today.weakCta}
              </ButtonLink>
            </li>
          )}

          {conceptsSeen.length > 0 && (
            <li className="py-5" data-growth-row>
              <p className="font-mono text-xs text-ink-500">{t.today.growthTitle}</p>
              <p className="mt-1 text-md text-ink-900">
                {t.today.growthLine(masteredAll, conceptsSeen.length, journeys.length)}
              </p>
            </li>
          )}

          {remembered && (
            <li className="py-5" data-mino-row>
              <p className="font-mono text-xs text-ink-500">{t.chat.title}</p>
              <p className="mt-1 font-serif text-md text-ink-800">{remembered}</p>
            </li>
          )}
        </ul>
      )}

      {/* Your learning — subjects and notebooks as a short list, not a card grid. */}
      {!homeLoading && hasLibrary && (
        <section className="mt-12 max-w-reading">
          <p className="font-mono text-xs text-ink-500">{t.today.yourLearning}</p>
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

      {/* Plan a session — folded, so a fixed block is on offer without
          competing with the answer above. The planning logic is unchanged;
          it simply is not run for an account with nothing to plan. */}
      {returning && (
        <details className="mt-16 max-w-reading border-t border-line pt-8">
          <summary className="cursor-pointer font-mono text-xs text-ink-500">
            {t.today.planTitle}
          </summary>
          <p className="mt-2 text-sm text-ink-600">{t.today.planLede}</p>

          <div className="mt-4 flex items-center gap-2">
            <span className="font-mono text-xs text-ink-500">{t.today.iHave}</span>
            <SegmentedControl
              label={t.today.iHave}
              value={minutes}
              onChange={setMinutes}
              options={BUDGETS.map((budget) => ({
                value: budget,
                label: `${budget} ${t.today.min}`,
              }))}
            />
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
                {/* Secondary: Continue above is the screen's one primary action. */}
                <div className="mt-8 flex items-center gap-4">
                  <ButtonLink href="/review" variant="secondary">
                    {t.today.startSession}
                  </ButtonLink>
                  <span className="text-sm text-ink-500">
                    {t.today.aboutMinutes(Math.round(plan.estimated_minutes))}
                  </span>
                </div>
              </>
            )
          )}
        </details>
      )}
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
