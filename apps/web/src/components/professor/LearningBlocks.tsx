'use client';

/**
 * The learning blocks Mino can place inside a reply.
 *
 * The engine writes a fenced block whose language is `noema:<tool>` and whose
 * body is one JSON object; the markdown parser hands it here as
 * `{ kind: 'tool', tool, data }`. Each tool is a small piece of the product's
 * own UI — layers, steps, a comparison, a quiz, a flashcard — drawn in the
 * same tokens as everything else. A block the client does not recognise, or
 * whose JSON is malformed, renders as ordinary code so nothing is lost.
 *
 * Blocks never decide anything about the learner: the quiz carries the
 * engine's answer, the UI compares and emits `correct` / `wrong` through
 * `onEvent`, and the character reacts to that — never the other way round.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useT } from '@/lib/i18n';

export type LearningEvent = 'correct' | 'wrong' | 'reveal';

export function LearningBlock({
  tool,
  data,
  onEvent,
}: {
  tool: string;
  data: Record<string, unknown>;
  onEvent?: (event: LearningEvent, detail?: Record<string, unknown>) => void;
}) {
  switch (tool) {
    case 'layers':
      return <Layers data={data} />;
    case 'steps':
      return <Steps data={data} />;
    case 'compare':
      return <Compare data={data} />;
    case 'quiz':
      return <Quiz data={data} onEvent={onEvent} />;
    case 'flashcard':
      return <Flashcard data={data} onEvent={onEvent} />;
    case 'check':
      return <Check data={data} />;
    default:
      return (
        <pre className="overflow-x-auto rounded-md bg-sunken p-3 font-mono text-sm text-ink-800">
          <code>{JSON.stringify(data, null, 2)}</code>
        </pre>
      );
  }
}

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
const text = (value: unknown): string => (typeof value === 'string' ? value : '');

/** A visible part above a line and a deeper part below it — the iceberg. */
function Layers({ data }: { data: Record<string, unknown> }) {
  const above = strings(data.above);
  const below = strings(data.below);
  return (
    <figure className="my-2 overflow-hidden rounded-lg border border-line bg-raised shadow-elevation-1">
      {text(data.title) && (
        <figcaption className="px-5 pt-4 text-xs uppercase tracking-wide text-ink-500">
          {text(data.title)}
        </figcaption>
      )}
      <div className="px-5 py-4">
        <p className="text-xs text-ink-500">{text(data.above_label)}</p>
        <ul className="mt-1 space-y-1">
          {above.map((item) => (
            <li key={item} className="text-base text-ink-900">
              {item}
            </li>
          ))}
        </ul>
      </div>
      <div className="relative border-t-2 border-signal bg-sunken px-5 py-4">
        <p className="text-xs text-ink-500">{text(data.below_label)}</p>
        <ul className="mt-1 space-y-1">
          {below.map((item) => (
            <li key={item} className="text-base text-ink-800">
              {item}
            </li>
          ))}
        </ul>
        {text(data.note) && <p className="mt-3 text-sm text-ink-600">{text(data.note)}</p>}
      </div>
    </figure>
  );
}

function Steps({ data }: { data: Record<string, unknown> }) {
  const items = strings(data.items);
  return (
    <figure className="my-2 rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
      {text(data.title) && (
        <figcaption className="text-xs uppercase tracking-wide text-ink-500">{text(data.title)}</figcaption>
      )}
      <ol className="mt-3 space-y-3">
        {items.map((item, index) => (
          <li key={item} className="flex gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary font-mono text-xs text-primary-fg">
              {index + 1}
            </span>
            <span className="text-base text-ink-800">{item}</span>
          </li>
        ))}
      </ol>
    </figure>
  );
}

function Compare({ data }: { data: Record<string, unknown> }) {
  const columns = strings(data.columns);
  const rows = Array.isArray(data.rows) ? data.rows.map(strings) : [];
  return (
    <div className="my-2 overflow-x-auto rounded-lg border border-line bg-raised shadow-elevation-1">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th key={column} className="px-4 py-3 font-medium text-ink-900">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-4 py-3 align-top text-ink-800">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Quiz({
  data,
  onEvent,
}: {
  data: Record<string, unknown>;
  onEvent?: (event: LearningEvent, detail?: Record<string, unknown>) => void;
}) {
  const t = useT();
  const options = strings(data.options);
  const answer = typeof data.answer === 'number' ? data.answer : -1;
  const [chosen, setChosen] = useState<number | null>(null);
  const done = chosen !== null;
  const correct = done && chosen === answer;

  function pick(index: number) {
    if (done) return;
    setChosen(index);
    onEvent?.(index === answer ? 'correct' : 'wrong', {
      question: text(data.question),
      chosen: options[index] ?? '',
      chosenIndex: index,
      concept: text(data.concept),
    });
  }

  return (
    <div className="my-2 rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
      <p className="font-display text-lg text-ink-900">{text(data.question)}</p>
      <ul className="mt-4 space-y-2" role="group" aria-label={text(data.question)}>
        {options.map((option, index) => {
          const tone = done
            ? index === answer
              ? 'border-positive text-ink-900'
              : chosen === index
                ? 'border-critical text-ink-900'
                : 'border-line text-ink-500'
            : 'border-line text-ink-800 hover:border-ink-400';
          return (
            <li key={option}>
              <button
                type="button"
                onClick={() => pick(index)}
                disabled={done}
                aria-pressed={chosen === index}
                className={`w-full rounded-md border bg-raised px-4 py-3 text-left text-base transition-colors duration-fast ${tone}`}
              >
                {option}
              </button>
            </li>
          );
        })}
      </ul>
      {done && (
        <div className={`mt-4 border-l-2 pl-4 ${correct ? 'border-positive' : 'border-critical'}`}>
          <p className={`text-sm font-medium ${correct ? 'text-positive' : 'text-critical'}`}>
            {correct ? t.question.correct : t.question.notQuite}
          </p>
          {text(data.explain) && <p className="mt-1 text-sm text-ink-700">{text(data.explain)}</p>}
        </div>
      )}
    </div>
  );
}

/**
 * An open question the learner answers in their own words, in the composer.
 * The rubric stayed on the server; Mino grades the answer in the next turn.
 */
function Check({ data }: { data: Record<string, unknown> }) {
  const t = useT();
  const teachBack = text(data.kind) === 'teach_back';
  return (
    <div className="my-2 rounded-lg border border-signal bg-raised p-5 shadow-elevation-1" data-lesson-check>
      <p className="text-xs uppercase tracking-wide text-signal">
        {teachBack ? t.professor.check.teachBack : t.professor.check.title}
      </p>
      <p className="mt-2 font-display text-lg text-ink-900">{text(data.question)}</p>
      <p className="mt-3 text-xs text-ink-400">{t.professor.check.hint}</p>
    </div>
  );
}

function Flashcard({
  data,
  onEvent,
}: {
  data: Record<string, unknown>;
  onEvent?: (event: LearningEvent, detail?: Record<string, unknown>) => void;
}) {
  const t = useT();
  const [flipped, setFlipped] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        setFlipped((f) => !f);
        if (!flipped) onEvent?.('reveal');
      }}
      aria-pressed={flipped}
      className="my-2 w-full max-w-md text-left [perspective:1400px] focus-visible:outline-none"
    >
      <div
        className={`grid transition-transform duration-slow ease-noema [transform-style:preserve-3d] ${flipped ? '[transform:rotateY(180deg)]' : ''}`}
      >
        <div className="col-start-1 row-start-1 rounded-lg border border-line bg-raised p-5 shadow-elevation-1 [backface-visibility:hidden]">
          <p className="font-serif text-md text-ink-900">{text(data.front)}</p>
          <p className="mt-4 text-xs text-ink-400">{t.review.showAnswer}</p>
        </div>
        <div className="col-start-1 row-start-1 rounded-lg border border-signal bg-raised p-5 shadow-elevation-2 [backface-visibility:hidden] [transform:rotateY(180deg)]">
          <p className="text-sm text-ink-500">{text(data.front)}</p>
          <p className="mt-2 font-serif text-md text-ink-900">{text(data.back)}</p>
        </div>
      </div>
      <Button variant="ghost" size="sm" className="mt-1 pointer-events-none">
        {t.notebook.cards}
      </Button>
    </button>
  );
}
