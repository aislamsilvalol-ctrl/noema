'use client';

/**
 * The journey as a trail: modules are stretches of the way, lessons are the
 * stops on them. Walked stops are mineral, the one you stand on is ember and
 * breathes, the ones ahead are open rings. On a desktop it runs left to right
 * like a path across the plate above it; on a phone it runs down the page,
 * with only the stretch you are on opened up.
 *
 * Draws what the server planned; computes nothing about the learner.
 */

import type { Journey } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { useReveal } from './Landscape';

type Stop = 'done' | 'current' | 'next';

function stopOf(status: string, isCurrent: boolean): Stop {
  if (isCurrent) return 'current';
  return status === 'done' || status === 'skipped' ? 'done' : 'next';
}

function Dot({ stop, title }: { stop: Stop; title: string }) {
  const base = 'relative block shrink-0 rounded-full';
  if (stop === 'current') {
    return (
      <span className={`${base} dash-here h-4 w-4 bg-dash-ember ring-4 ring-dash-ember/20`} title={title}>
        <span className="sr-only">{title}</span>
      </span>
    );
  }
  return (
    <span
      className={`${base} h-3 w-3 ${stop === 'done' ? 'bg-dash-mineral' : 'border-2 border-ink-300 bg-surface'}`}
      title={title}
    />
  );
}

export function JourneyProgress({ journey }: { journey: Journey }) {
  const t = useT();
  const copy = t.home.trail;
  const [ref, shown] = useReveal<HTMLDivElement>();
  const plan = journey.plan ?? [];
  const at = journey.current ?? { module: 0, lesson: 0, concept: '' };
  if (plan.length === 0) return null;

  const modules = plan.map((module, m) => {
    const lessons = module.lessons.map((lesson, l) => ({
      title: lesson.title,
      stop: stopOf(lesson.status, m === at.module && l === at.lesson),
    }));
    const done = lessons.filter((l) => l.stop === 'done').length;
    const state: Stop = m === at.module ? 'current' : m < at.module || done === lessons.length ? 'done' : 'next';
    return { title: module.title, lessons, done, state };
  });

  return (
    <div ref={ref} data-shown={shown} className="dash-reveal" data-journey-trail>
      {/* Desktop: one line across, each stretch as wide as its stops. */}
      <ol className="hidden md:flex md:gap-2">
        {modules.map((module, m) => (
          <li
            key={`${module.title}-${m}`}
            className="min-w-0"
            style={{ flex: `${Math.max(module.lessons.length, 1)} 1 0%` }}
            aria-current={module.state === 'current' ? 'step' : undefined}
          >
            <div className="relative flex h-6 items-center">
              <span
                aria-hidden="true"
                className={`dash-line absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 ${
                  module.state === 'next' ? 'bg-line' : 'bg-dash-mineral/40'
                }`}
                style={{ animationDelay: `${120 + m * 140}ms` }}
              />
              <span
                className="relative grid w-full items-center"
                style={{ gridTemplateColumns: `repeat(${Math.max(module.lessons.length, 1)}, minmax(0, 1fr))` }}
              >
                {module.lessons.map((lesson, l) => (
                  <Dot key={`${lesson.title}-${l}`} stop={lesson.stop} title={lesson.title} />
                ))}
              </span>
            </div>
            <p
              className={`mt-4 truncate text-sm ${
                module.state === 'current' ? 'font-medium text-ink-900' : 'text-ink-500'
              }`}
              title={module.title}
            >
              {module.title}
            </p>
            <p className="mt-0.5 font-mono text-xs text-ink-400">
              {module.state === 'current' ? (
                <span className="text-dash-ember">{copy.here}</span>
              ) : (
                copy.moduleOf(module.done, module.lessons.length)
              )}
            </p>
          </li>
        ))}
      </ol>

      {/* Phone: down the page; the stretch you are on lists its lessons. */}
      <ol className="space-y-0 md:hidden">
        {modules.map((module, m) => (
          <li
            key={`${module.title}-${m}`}
            className="relative pb-5 pl-8 last:pb-0"
            aria-current={module.state === 'current' ? 'step' : undefined}
          >
            {m < modules.length - 1 && (
              <span
                aria-hidden="true"
                className={`absolute bottom-0 left-[7px] top-5 w-[2px] ${module.state === 'next' ? 'bg-line' : 'bg-dash-mineral/40'}`}
              />
            )}
            <span className="absolute left-0 top-1 flex h-4 w-4 items-center justify-center">
              <Dot stop={module.state} title={module.title} />
            </span>
            <div className="flex items-baseline justify-between gap-3">
              <p className={`text-base ${module.state === 'current' ? 'font-medium text-ink-900' : 'text-ink-500'}`}>
                {module.title}
              </p>
              <span className="shrink-0 font-mono text-xs text-ink-400">
                {copy.moduleOf(module.done, module.lessons.length)}
              </span>
            </div>
            {module.state === 'current' && (
              <ul className="mt-3 space-y-2.5">
                {module.lessons.map((lesson, l) => (
                  <li key={`${lesson.title}-${l}`} className="flex items-center gap-3 text-sm">
                    <span className="flex w-4 justify-center">
                      <Dot stop={lesson.stop} title={lesson.title} />
                    </span>
                    <span className={lesson.stop === 'current' ? 'text-ink-900' : lesson.stop === 'done' ? 'text-ink-500' : 'text-ink-600'}>
                      {lesson.title}
                    </span>
                    {lesson.stop === 'current' && <span className="font-mono text-xs text-dash-ember">{copy.here}</span>}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
