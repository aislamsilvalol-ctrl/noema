'use client';

/**
 * The study rail: what you are studying, kept in view beside the lesson.
 *
 * The lesson column is the conversation; this is the subject. The rail
 * shows the journey the engine is running — objective, where we are in
 * the plan, what the engine believes you know, what you parked for later,
 * what it remembers of earlier sessions, and how much moved today — so
 * the learner reads "I am studying psychology", not "I am chatting with a
 * bot that knows psychology". Every line comes from the journey the
 * server already returned; nothing here calls a model.
 */

import type { Journey } from '@/lib/api';
import { useT } from '@/lib/i18n';

const STAGE_MARK: Record<string, string> = {
  mastered: '●',
  learning: '◐',
  introduced: '◔',
  uncertain: '◯',
  needs_review: '◯',
  not_started: '·',
};

export function StudyRail({ journey }: { journey: Journey | null }) {
  const t = useT();
  const copy = t.studyRail;
  if (!journey) {
    return (
      <div className="text-sm text-ink-500">
        <p className="font-mono text-xs text-ink-400">{copy.title}</p>
        <p className="mt-3">{copy.empty}</p>
      </div>
    );
  }

  const modules = journey.plan ?? [];
  const current = journey.current;
  const concepts = journey.concepts ?? [];
  const known = concepts.filter((c) => c.state === 'mastered' || c.state === 'learning');
  const shaky = concepts.filter((c) => c.state === 'uncertain' || c.state === 'needs_review');
  const parked = (journey.parked ?? []) as { topic?: string }[];
  // The newest fold of the engine's memory, rendered by the keys it writes.
  const latest = (journey.memory ?? [])[journey.memory?.length ? journey.memory.length - 1 : 0];
  const remembered: string[] = [];
  if (latest?.summary) {
    for (const key of ['learned', 'struggles', 'learner_patterns', 'next']) {
      const value = (latest.summary as Record<string, unknown>)[key];
      if (typeof value === 'string' && value.trim()) remembered.push(value.trim());
      else if (Array.isArray(value))
        for (const v of value) if (typeof v === 'string' && v.trim()) remembered.push(v.trim());
    }
  }
  const momentum = journey.momentum;

  return (
    <div className="text-sm">
      <p className="font-mono text-xs text-ink-400">{copy.title}</p>
      <h2 className="mt-2 font-display text-xl text-ink-900">{journey.subject}</h2>
      {journey.objective && <p className="mt-1 text-ink-600">{journey.objective}</p>}

      {/* where we are */}
      <section className="mt-8 border-t border-line pt-4">
        <p className="font-mono text-xs text-ink-400">{copy.where}</p>
        <ol className="mt-2">
          {modules.map((module, mi) => {
            const here = current?.module === mi;
            return (
              <li key={`${mi}-${module.title}`} className={`py-1 ${here ? 'text-ink-900' : 'text-ink-500'}`}>
                <div className="flex items-baseline gap-2">
                  <span className="w-5 shrink-0 font-mono text-xs text-ink-400">{String(mi + 1).padStart(2, '0')}</span>
                  <span className={module.status === 'done' ? 'line-through decoration-ink-300' : ''}>
                    {module.title}
                  </span>
                </div>
                {here && (
                  <ol className="ml-7 mt-1 border-l border-line pl-3">
                    {module.lessons.map((lesson, li) => {
                      const now = current?.lesson === li;
                      return (
                        <li
                          key={`${li}-${lesson.title}`}
                          className={`py-0.5 text-xs ${now ? 'text-signal' : 'text-ink-500'}`}
                        >
                          {lesson.title}
                          {now && current?.concept && <span className="text-ink-600"> · {current.concept}</span>}
                        </li>
                      );
                    })}
                  </ol>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      {/* what it believes you know */}
      {concepts.length > 0 && (
        <section className="mt-6 border-t border-line pt-4">
          <p className="font-mono text-xs text-ink-400">{copy.knows}</p>
          <ul className="mt-2 space-y-1">
            {[...known, ...shaky].slice(0, 8).map((c) => (
              <li key={c.name} className="flex items-baseline gap-2">
                <span
                  aria-hidden="true"
                  className={`w-3 text-xs ${c.state === 'mastered' ? 'text-positive' : c.state === 'learning' ? 'text-signal' : 'text-ink-400'}`}
                >
                  {STAGE_MARK[c.state] ?? '·'}
                </span>
                <span className={c.state === 'mastered' || c.state === 'learning' ? 'text-ink-800' : 'text-ink-500'}>
                  {c.name}
                </span>
                {c.misconceptions && c.misconceptions.length > 0 && (
                  <span className="text-xs text-critical">{copy.misconception}</span>
                )}
              </li>
            ))}
          </ul>
          {shaky.length > 0 && <p className="mt-2 text-xs text-ink-400">{copy.shakyHint(shaky.length)}</p>}
        </section>
      )}

      {/* parked for later */}
      {parked.length > 0 && (
        <section className="mt-6 border-t border-line pt-4">
          <p className="font-mono text-xs text-ink-400">{copy.parked}</p>
          <ul className="mt-2 space-y-1 text-ink-700">
            {parked.map((p, i) => (
              <li key={`${i}-${p.topic}`}>{p.topic}</li>
            ))}
          </ul>
        </section>
      )}

      {/* what it remembers */}
      {remembered.length > 0 && (
        <section className="mt-6 border-t border-line pt-4">
          <p className="font-mono text-xs text-ink-400">{copy.remembers}</p>
          <ul className="mt-2 space-y-1 font-serif text-ink-700">
            {remembered.slice(0, 5).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      {/* today */}
      {momentum && (momentum.events_today > 0 || momentum.mastered_today > 0) && (
        <section className="mt-6 border-t border-line pt-4">
          <p className="font-mono text-xs text-ink-400">{copy.today}</p>
          <p className="mt-2 text-ink-700">{copy.momentum(momentum.events_today, momentum.mastered_today)}</p>
        </section>
      )}
    </div>
  );
}
