'use client';

/**
 * The landing page's story, told in beats rather than a grid of cards.
 *
 * Six chapters after the hero, each one claim with one small, in-system
 * illustration beside it — a lesson block, mastery bars, a confident wrong
 * verdict, a citation, a generated question, a review card. They are built
 * from the product's own pieces and tokens, static and labelled as the
 * story, never presented as live output. Each beat registers with the
 * scroll observer so the companion Mino changes with the chapter; under
 * reduced motion nothing changes at all (see `useScrollMinoState`).
 */

import type { MinoState as Pose } from '@/brand/mino';
import { Markdown } from '@/lib/markdown';
import { useT } from '@/lib/i18n';

export const BEAT_POSES: readonly { id: string; state: Pose }[] = [
  { id: 'beat-tutor', state: 'pointing' },
  { id: 'beat-concepts', state: 'thinking' },
  { id: 'beat-errors', state: 'studying' },
  { id: 'beat-sources', state: 'reading' },
  { id: 'beat-practice', state: 'pointing' },
  { id: 'beat-return', state: 'studying' },
];

export function Beats({
  registerSection,
}: {
  registerSection: (id: string) => (element: Element | null) => void;
}) {
  const t = useT();
  const s = t.landing.samples;
  const pillars = t.landing.pillars;

  const visuals = [
    <div key="tutor" className="rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
      <p className="border-l-2 border-line pl-3 text-sm text-ink-600">{s.learner}</p>
      <p className="mt-4 text-xs uppercase tracking-wide text-signal">NOEMA</p>
      <Markdown text={s.lesson} className="mt-2 text-sm" />
    </div>,

    <ul key="concepts" className="divide-y divide-line rounded-lg border border-line bg-raised px-5 py-2">
      {s.concepts.map(([name, score]) => (
        <li key={name} className="py-3">
          <div className="flex items-baseline justify-between gap-4 text-sm">
            <span className="text-ink-800">{name}</span>
            <span className={`font-mono ${score < 40 ? 'text-critical' : score < 60 ? 'text-ink-600' : 'text-positive'}`}>
              {score}
            </span>
          </div>
          <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-sunken">
            <div
              className={`h-full rounded-full ${score < 40 ? 'bg-critical' : score < 60 ? 'bg-primary' : 'bg-positive'}`}
              style={{ width: `${score}%` }}
            />
          </div>
        </li>
      ))}
    </ul>,

    <div key="errors" className="rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
      <div className="flex flex-wrap gap-2">
        {t.question.confidence.map((label) => (
          <span
            key={label}
            className={`rounded-md border px-2.5 py-1 text-xs ${
              label === t.question.confidence[t.question.confidence.length - 1]
                ? 'border-signal text-ink-900'
                : 'border-line text-ink-500'
            }`}
          >
            {label}
          </span>
        ))}
      </div>
      <div className="mt-4 border-l-2 border-critical pl-4">
        <p className="text-sm font-medium text-critical">{s.verdict}</p>
        <p className="mt-1 text-xs text-ink-500">{s.misconception}</p>
      </div>
    </div>,

    <div key="sources" className="rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
      <p className="font-serif text-md text-ink-800">{s.excerpt}</p>
      <p className="mt-3 text-xs text-ink-500">{s.source}</p>
      <p className="mt-4 border-t border-line pt-3 text-xs text-ink-500">{s.notFound}</p>
    </div>,

    <div key="practice" className="rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
      <p className="text-xs text-ink-500">{s.generated}</p>
      <ul className="mt-3 space-y-2">
        {s.options.map((option, index) => (
          <li
            key={option}
            className={`rounded-md border px-4 py-2.5 text-sm ${
              index === 1 ? 'border-signal text-ink-900' : 'border-line text-ink-700'
            }`}
          >
            {option}
          </li>
        ))}
      </ul>
    </div>,

    <div key="return" className="rounded-lg border border-signal bg-raised p-5 shadow-elevation-2">
      <p className="text-sm text-ink-500">{s.options[0]}?</p>
      <p className="mt-2 font-serif text-lg text-ink-900">{s.due}</p>
      <p className="mt-4 text-xs text-ink-500">{s.next}</p>
    </div>,
  ];

  return (
    <div data-mino-section="pillars" className="border-t border-line">
      <div className="mx-auto max-w-6xl px-6">
        <p className="pt-16 text-xs uppercase tracking-wide text-ink-500">{t.landing.beatsLabel}</p>
        {pillars.map((pillar, index) => {
          const pose = BEAT_POSES[index];
          const flip = index % 2 === 1;
          return (
            <section
              key={pillar.title}
              ref={pose ? registerSection(pose.id) : undefined}
              className={`grid gap-10 py-16 md:grid-cols-2 md:items-center md:py-24 ${
                flip ? 'md:[&>*:first-child]:order-2' : ''
              }`}
            >
              <div className="max-w-reading">
                <span className="font-mono text-xs text-signal">{String(index + 2).padStart(2, '0')}</span>
                <h2 className="mt-3 font-display text-2xl text-ink-900">{pillar.title}</h2>
                <p className="mt-4 text-base text-ink-600">{pillar.body}</p>
              </div>
              <div aria-hidden="true" className="w-full max-w-md md:justify-self-center">
                {visuals[index]}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
