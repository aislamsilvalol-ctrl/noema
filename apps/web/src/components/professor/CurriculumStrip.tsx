'use client';

/**
 * Where the journey is: the course the engine planned, folded to one line.
 *
 * The current module and lesson, how many lessons are behind, and the
 * concepts of this lesson with their stage — introduced, learning, uncertain,
 * mastered, needs review — drawn as small marks, never as percentages. It
 * opens to the whole plan on request. Nothing here is computed: the server
 * decides the plan and the stages; this draws them.
 */

import { useState } from 'react';
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

export function CurriculumStrip({ journey }: { journey: Journey }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const unit = journey.plan[journey.current.module];
  const lesson = unit?.lessons[journey.current.lesson];
  const total = journey.plan.reduce((sum, m) => sum + m.lessons.length, 0);
  const done = journey.plan.reduce(
    (sum, m) => sum + m.lessons.filter((l) => l.status === 'done' || l.status === 'skipped').length,
    0,
  );
  const stages = new Map(journey.concepts.map((c) => [c.name.toLowerCase(), c.state]));
  if (!unit || !lesson) return null;

  return (
    <div className="mt-3 text-sm" data-curriculum>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-ink-500">{unit.title}</span>
        <span aria-hidden="true" className="text-ink-300">
          ·
        </span>
        <span className="text-ink-900">{lesson.title}</span>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="ml-auto text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
        >
          {t.professor.course.lessons(done, total)}
        </button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1" aria-label={t.professor.course.concepts}>
        {lesson.concepts.map((concept) => {
          const stage = stages.get(concept.toLowerCase()) ?? 'not_started';
          return (
            <li key={concept} className="flex items-center gap-2 text-xs text-ink-600">
              <span
                aria-hidden="true"
                className={`inline-block h-2 w-2 rounded-full border ${STAGE_TONE[stage] ?? STAGE_TONE.not_started}`}
              />
              <span>{concept}</span>
              <span className="sr-only">{t.professor.course.stages[stage] ?? stage}</span>
            </li>
          );
        })}
      </ul>
      {open && (
        <ol className="mt-4 space-y-3 border-l border-line pl-4">
          {journey.plan.map((m, mi) => (
            <li key={`${m.title}-${mi}`}>
              <p className={`text-xs uppercase tracking-wide ${mi === journey.current.module ? 'text-signal' : 'text-ink-400'}`}>
                {m.title}
              </p>
              <ul className="mt-1 space-y-0.5">
                {m.lessons.map((l, li) => {
                  const current = mi === journey.current.module && li === journey.current.lesson;
                  return (
                    <li
                      key={`${l.title}-${li}`}
                      className={
                        current
                          ? 'text-ink-900'
                          : l.status === 'done' || l.status === 'skipped'
                            ? 'text-ink-400 line-through decoration-ink-300'
                            : 'text-ink-600'
                      }
                    >
                      {l.title}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
