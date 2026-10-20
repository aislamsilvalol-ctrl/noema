'use client';

/**
 * Home: the learner's own place (docs/dashboard-redesign.md). It answers, in
 * this order and without a scroll for the first three: where am I, what am I
 * learning, what do I do now — and then how I am growing and what else there
 * is to explore.
 *
 *   hero      the territory, and Continue set in its sky
 *   trail     the journey: modules, lessons, the point you stand on, and the
 *             concepts it holds
 *   agora     one sentence from the engine and at most two ways to act on it
 *   progress  four numbers and today's small goals
 *   resume    other lessons and notebooks, when there are any
 *   explore   the journey's next stretch and a few ideas to start from
 *
 * Everything is composed on the client from endpoints that already exist,
 * each allowed to fail on its own: a missing journey must not blank the
 * reviews, and a failed recommendation leaves the page usable. Nothing is
 * estimated where a real number exists. A learner who chose Modo TDAH as
 * their way of learning gets its own home (FocusHome) instead.
 */

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { Shell } from '@/components/Shell';
import { FocusHome } from '@/components/professor/FocusHome';
import { taskLabel } from '@/components/foco/Foco';
import { useProgression } from '@/components/progress/Progression';
import { DashboardHero, type HeroLesson } from '@/components/dashboard/DashboardHero';
import { JourneyProgress } from '@/components/dashboard/JourneyProgress';
import { MapLink } from '@/components/dashboard/MapLink';
import { NextAction } from '@/components/dashboard/NextAction';
import { ProgressSummary } from '@/components/dashboard/ProgressSummary';
import { ExploreTile, LearningTile } from '@/components/dashboard/Tiles';
import {
  dayPart,
  firstName,
  heroPlate,
  placeIn,
  plateFor,
  recommend,
  remembered,
  weakConcept,
} from '@/components/dashboard/homeState';
import { useLearningMode } from '@/lib/useLearningMode';
import {
  ApiError,
  api,
  type Journey,
  type LessonSummary,
  type Mastery,
  type NextActivity,
  type Notebook,
  type Subject,
  type TeachingSession,
  type User,
} from '@/lib/api';
import { track, trackOnce } from '@/lib/analytics';
import { useT } from '@/lib/i18n';
import { journeyHref, lessonHref, NEW_LESSON } from '@/lib/lessonLinks';
import { rememberPrefill } from '@/lib/prefill';
import { titleFrom } from '@/lib/text';
import '@/styles/dashboard.css';

export default function TodayPage() {
  const router = useRouter();
  const t = useT();
  const copy = t.home;

  const [me, setMe] = useState<User | null>(null);
  const [lesson, setLesson] = useState<TeachingSession | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [mastery, setMastery] = useState<Mastery[]>([]);
  const [due, setDue] = useState<number | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [openLessons, setOpenLessons] = useState<LessonSummary[]>([]);
  const [next, setNext] = useState<NextActivity | null>(null);
  const [nextSettled, setNextSettled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [homeError, setHomeError] = useState<string | null>(null);
  const { mode, minutes: budget } = useLearningMode();
  const progress = useProgression();
  // Read once on mount: the greeting does not change under the learner.
  const [part] = useState(() => dayPart(new Date().getHours()));

  useEffect(() => {
    trackOnce('dashboard_viewed');
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([
      api.latestSession(),
      api.dueCards(undefined, 200),
      api.subjects(),
      api.notebooks(),
      api.latestJourney(),
      api.mastery(),
      api.journeys(),
      api.openLessons(),
      api.me(),
    ]).then((results) => {
      if (cancelled) return;
      const [session, dueCards, subjectPage, notebookPage, latestJourney, scores, trips, open, account] =
        results;
      if (open.status === 'fulfilled') setOpenLessons(open.value);
      if (session.status === 'fulfilled') setLesson(session.value);
      if (latestJourney.status === 'fulfilled') setJourney(latestJourney.value);
      if (dueCards.status === 'fulfilled') setDue(dueCards.value.length);
      if (subjectPage.status === 'fulfilled') setSubjects(subjectPage.value.items);
      if (notebookPage.status === 'fulfilled') setNotebooks(notebookPage.value.items);
      if (scores.status === 'fulfilled') setMastery(scores.value);
      if (trips.status === 'fulfilled') setJourneys(trips.value);
      if (account.status === 'fulfilled') setMe(account.value);

      const unauthorized = results.some(
        (r) => r.status === 'rejected' && r.reason instanceof ApiError && r.reason.isUnauthorized,
      );
      if (unauthorized) {
        router.push('/login');
        return;
      }
      if (results.every((r) => r.status === 'rejected')) setHomeError(t.today.couldNotPlan);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [router, t]);

  // The engine's one answer to "what now?" — also Modo TDAH's next task.
  useEffect(() => {
    let cancelled = false;
    api
      .nextActivity()
      .then((value) => {
        if (!cancelled) setNext(value);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setNextSettled(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasLibrary = subjects.length > 0 || notebooks.length > 0;
  // A brand-new account: one question, a field, a few ideas. No planner, no
  // "nothing is due" beside "start learning".
  const firstDay = !loading && !hasLibrary && !lesson && !journey;
  const hasLesson = journey !== null || lesson !== null;

  const heroLesson: HeroLesson | null = useMemo(() => {
    if (journey) {
      const place = placeIn(journey);
      return {
        subject: journey.subject,
        headline: place.lesson ?? place.module ?? journey.subject,
        next: place.concept,
        place,
        href: journeyHref(journey.id, openLessons),
      };
    }
    if (lesson) {
      const subject = lesson.subject || lesson.current_topic || titleFrom(lesson.learning_goal);
      const headline = lesson.current_topic && lesson.current_topic !== subject ? lesson.current_topic : subject;
      return {
        subject,
        headline,
        next: lesson.current_concept && lesson.current_concept !== headline ? lesson.current_concept : null,
        place: null,
        href: lessonHref(lesson.id),
      };
    }
    return null;
  }, [journey, lesson, openLessons]);

  const weak = weakConcept(mastery, journey);
  const recommendation = recommend({ next, weak, due: due ?? 0, hasLesson });
  const plate = loading ? null : heroPlate({ firstDay, journey, next });
  const name = firstName(me?.display_name);
  const reviewMinutes =
    next?.kind === 'review' ? next.minutes_estimate : Math.max(1, Math.round((due ?? 0) * 0.5));
  // Reviews beside Continue only when they are not already the "Agora" line.
  const heroReview =
    due && due > 0 && recommendation?.kind !== 'review' ? { due, minutes: reviewMinutes } : null;

  const memory = remembered(journey);
  const memoryLine = memory ? ('next' in memory ? t.today.minoNextStep(memory.next) : t.today.minoLastTaught(memory.last)) : null;

  const conceptsSeen = journeys.flatMap((j) => j.concepts ?? []);
  const masteredAll = conceptsSeen.filter((c) => c.state === 'mastered').length;

  // Pick up again: lessons and notebooks other than the one in the hero.
  const heroSession = journey ? openLessons.find((l) => l.journey_id === journey.id)?.id : lesson?.id;
  const resume = openLessons.filter((l) => l.id !== heroSession && l.journey_id !== journey?.id).slice(0, 4);
  const resumeNotebooks = notebooks.slice(0, Math.max(0, 4 - resume.length));

  // Explore: the journey's real next stretch first, then ideas not already
  // being studied. Ideas are labelled as ideas, never "recommended for you".
  const upcoming = journey?.plan?.[(journey.current?.module ?? 0) + 1] ?? null;
  const studying = new Set(journeys.map((j) => j.subject.trim().toLowerCase()));
  const ideas = copy.explore.ideas.filter((idea) => !studying.has(idea.title.trim().toLowerCase()));
  const exploreIdeas = ideas.slice(0, upcoming ? 2 : 3);

  if (mode === 'focus') {
    return (
      <Shell>
        <section className="max-w-reading">
          {loading ? null : (
            <FocusHome
              journey={journey}
              href={journey ? journeyHref(journey.id, openLessons) : NEW_LESSON}
              minutes={budget}
              due={due ?? 0}
            />
          )}
        </section>
      </Shell>
    );
  }

  const greeting = copy.greeting[part](name);

  return (
    <Shell>
      <DashboardHero
        loading={loading}
        plate={plate}
        part={part}
        greeting={greeting}
        ask={copy.ask[part]}
        lesson={firstDay ? null : heroLesson}
        review={heroReview}
      />

      {homeError && (
        <p role="alert" className="mt-6 text-sm text-critical">
          {homeError}
        </p>
      )}

      <div className="mx-auto max-w-[1180px]">
        {/* A first day: how it goes, in three lines, under the question. */}
        {firstDay && (
          <ol className="mt-14 grid gap-8 border-t border-line pt-8 md:mt-16 md:grid-cols-3" data-first-day-steps>
            {copy.firstDay.steps.map((step, index) => (
              <li key={step} className="flex gap-4">
                <span className="font-display text-2xl tabular-nums text-dash-ember">{String(index + 1).padStart(2, '0')}</span>
                <span className="pt-1.5 text-md text-ink-800">{step}</span>
              </li>
            ))}
          </ol>
        )}

        {/* The trail and the map it holds: where you are on the way. */}
        {journey && (journey.plan?.length ?? 0) > 0 && (
          <section aria-labelledby="home-trail" className="mt-14 md:mt-16">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 id="home-trail" className="font-display text-xl text-ink-900">
                {copy.trail.title}
                <span className="ml-3 text-base text-ink-500">{journey.subject}</span>
              </h2>
              <MapLink />
            </div>
            <div className="mt-8">
              <JourneyProgress journey={journey} />
            </div>
          </section>
        )}

        {!loading && nextSettled && !firstDay && (
          <div className="mt-14 md:mt-16">
            <NextAction
              recommendation={recommendation}
              focusTask={next && next.kind !== 'start' ? taskLabel(next, t) : null}
              focusMinutes={next?.minutes_estimate ?? 10}
              part={part}
              memory={memoryLine}
            />
          </div>
        )}

        {!loading && !firstDay && (
          <div className="mt-14 md:mt-16">
            <ProgressSummary
              mastered={masteredAll}
              seen={conceptsSeen.length}
              progress={progress}
              today={journey?.momentum ? { mastered: journey.momentum.mastered_today, events: journey.momentum.events_today } : null}
            />
          </div>
        )}

        {(resume.length > 0 || resumeNotebooks.length > 0) && (
          <section aria-labelledby="home-resume" className="mt-14 md:mt-16">
            <h2 id="home-resume" className="font-display text-xl text-ink-900">
              {copy.resume.title}
            </h2>
            <div className="dash-rail -mx-6 mt-6 flex snap-x snap-mandatory scroll-px-6 gap-3 overflow-x-auto px-6 pb-2 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 lg:grid-cols-3">
              {resume.map((item, index) => {
                const subject = item.subject || item.current_topic || titleFrom(item.learning_goal);
                return (
                  <LearningTile
                    key={item.id}
                    index={index}
                    href={lessonHref(item.id)}
                    plate={plateFor(subject)}
                    kicker={subject}
                    title={item.current_topic && item.current_topic !== subject ? item.current_topic : titleFrom(item.learning_goal)}
                    context={item.current_concept ? copy.resume.stoppedAt(item.current_concept) : null}
                    onClick={() => track('continue_learning_clicked', { from: 'resume' })}
                  />
                );
              })}
              {resumeNotebooks.map((notebook, index) => (
                <LearningTile
                  key={notebook.id}
                  index={resume.length + index}
                  href={`/notebooks/${notebook.id}`}
                  plate={plateFor(notebook.title)}
                  kicker={copy.resume.notebook}
                  title={notebook.title}
                  context={null}
                />
              ))}
            </div>
          </section>
        )}

        {!loading && !firstDay && (upcoming || exploreIdeas.length > 0) && (
          <section aria-labelledby="home-explore" className="mt-14 md:mt-16">
            <h2 id="home-explore" className="font-display text-xl text-ink-900">
              {copy.explore.title}
            </h2>
            <div className="dash-rail -mx-6 mt-6 flex snap-x snap-mandatory scroll-px-6 gap-3 overflow-x-auto px-6 pb-2 md:mx-0 md:grid md:grid-cols-3 md:gap-4 md:overflow-visible md:px-0">
              {upcoming && journey && (
                <ExploreTile
                  href={journeyHref(journey.id, openLessons)}
                  plate="routes"
                  kicker={copy.explore.fromHere}
                  title={upcoming.title}
                  context={copy.explore.after(journey.plan?.[journey.current?.module ?? 0]?.title ?? journey.subject)}
                  onClick={() => track('explore_clicked', { source: 'journey' })}
                />
              )}
              {exploreIdeas.map((idea, index) => (
                <ExploreTile
                  key={idea.title}
                  index={index + 1}
                  href="/learn/new"
                  plate={plateFor(idea.title)}
                  kicker={copy.explore.idea}
                  title={idea.title}
                  context={idea.context}
                  onClick={() => {
                    track('explore_clicked', { source: 'idea' });
                    rememberPrefill(copy.explore.prefill(idea.title));
                  }}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </Shell>
  );
}
