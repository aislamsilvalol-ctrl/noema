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
  // The server owns the plan; a journey it has not planned yet (or an older
  // record without a position) still draws its subject and its link.
  const plan = journey.plan ?? [];
  const concepts = journey.concepts ?? [];
  const unit = plan[journey.current?.module ?? 0];
  const lesson = unit?.lessons[journey.current?.lesson ?? 0];
  const total = plan.reduce((sum, m) => sum + m.lessons.length, 0);
  const done = plan.reduce(
    (sum, m) => sum + m.lessons.filter((l) => l.status === 'done' || l.status === 'skipped').length,
    0,
  );
  const mastered = concepts.filter((c) => c.state === 'mastered').length;
  // Where we are, said once: a unit, lesson or concept that only repeats the
  // subject (a young plan often names all four the same) is left out.
  const seen = new Set([journey.subject.trim().toLowerCase()]);
  const place = [unit?.title, lesson?.title, journey.current?.concept].filter((part): part is string => {
    const key = (part ?? '').trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const namedConcepts = concepts.filter(
    (c) => c.name.trim().toLowerCase() !== journey.subject.trim().toLowerCase(),
  );
  const shaky = concepts.filter((c) => c.state === 'uncertain' || c.state === 'needs_review').length;

  return (
    <article
      className={`border-t border-line pt-5 ${className}`}
      data-journey={journey.id}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-display text-xl text-ink-900">{journey.subject}</h3>
        <span className="text-xs text-ink-500">{t.professor.course.lessons(done, total)}</span>
      </div>
      {place.length > 0 && (
        <p className="mt-1 text-md text-ink-600" data-journey-place>
          {place.join(' › ')}
        </p>
      )}
      <div className="mt-3 h-px w-full bg-line">
        <div
          className="h-px bg-primary transition-[width] duration-slow ease-noema"
          style={{ width: `${total ? (done / total) * 100 : 0}%` }}
        />
      </div>
      {namedConcepts.length > 0 && (
        <>
          <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5" aria-label={t.professor.course.concepts}>
            {namedConcepts.slice(0, 8).map((concept) => (
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
        <ButtonLink href={cta.href} variant="primary" size="lg" className="mt-6">
          {cta.label}
        </ButtonLink>
      )}
    </article>
  );
}
