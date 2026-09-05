'use client';

/**
 * A journey at a glance: the subject, where the lesson is, how much of the
 * course is behind, and the concepts of the current lesson with their stage.
 * Used on Home ("continue") and Progress ("your journeys"). Draws what the
 * server decided; computes nothing about the learner.
 */

import { ButtonLink } from '@/components/ui/Button';
import type { Journey } from '@/lib/api';
import { useT } from '@/lib/i18n';

const STAGE_TONE: Record<string, string> = {
  not_started: 'border-line bg-transparent',
  introduced: 'border-ink-400 bg-transparent',
  learning: 'border-signal bg-transparent',
  uncertain: 'border-critical bg-transparent',
  mastered: 'border-positive bg-positive',
  needs_review: 'border-caution bg-caution',
};

export function JourneyCard({
  journey,
  cta,
  className = '',
}: {
  journey: Journey;
  /** The "continue" link; omitted on lists that are only for reading. */
  cta?: { href: string; label: string };
  className?: string;
}) {
  const t = useT();
  const unit = journey.plan[journey.current.module];
  const lesson = unit?.lessons[journey.current.lesson];
  const total = journey.plan.reduce((sum, m) => sum + m.lessons.length, 0);
  const done = journey.plan.reduce(
    (sum, m) => sum + m.lessons.filter((l) => l.status === 'done' || l.status === 'skipped').length,
    0,
  );
  const mastered = journey.concepts.filter((c) => c.state === 'mastered').length;
  const shaky = journey.concepts.filter(
    (c) => c.state === 'uncertain' || c.state === 'needs_review',
  ).length;

  return (
    <article
      className={`rounded-lg border border-line bg-raised p-6 shadow-elevation-1 ${className}`}
      data-journey={journey.id}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-display text-xl text-ink-900">{journey.subject}</h3>
        <span className="text-xs text-ink-500">{t.professor.course.lessons(done, total)}</span>
      </div>
      {lesson && (
        <p className="mt-1 text-sm text-ink-600">
          {unit?.title} · {lesson.title}
        </p>
      )}
      <div className="mt-3 h-px w-full bg-line">
        <div
          className="h-px bg-signal transition-[width] duration-slow ease-noema"
          style={{ width: `${total ? (done / total) * 100 : 0}%` }}
        />
      </div>
      {journey.concepts.length > 0 && (
        <>
          <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5" aria-label={t.professor.course.concepts}>
            {journey.concepts.slice(0, 8).map((concept) => (
              <li key={concept.name} className="flex items-center gap-2 text-xs text-ink-600">
                <span
                  aria-hidden="true"
                  className={`inline-block h-2 w-2 rounded-full border ${STAGE_TONE[concept.state] ?? STAGE_TONE.not_started}`}
                />
                <span>{concept.name}</span>
                <span className="sr-only">{t.professor.course.stages[concept.state] ?? concept.state}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ink-500">{t.progress.journeySummary(mastered, shaky)}</p>
        </>
      )}
      {cta && (
        <ButtonLink href={cta.href} variant="primary" className="mt-5">
          {cta.label}
        </ButtonLink>
      )}
    </article>
  );
}
