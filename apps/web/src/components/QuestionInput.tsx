'use client';

/**
 * The input for one question, per type.
 *
 * Pulled out of `QuestionCard` because the exam renders the same inputs on one
 * long page, and two copies of "how do you answer an ordering question" would
 * drift apart within a week.
 *
 * Ordering uses move-up/move-down rather than drag and drop. Dragging is nicer
 * with a mouse and unusable with a keyboard or a screen reader, and the answer to
 * "which order do these go in" should not depend on fine motor control.
 */

import type { Question } from '@/lib/api';
import { useT } from '@/lib/i18n';

export type Response = Record<string, unknown>;

export function QuestionInput({
  question,
  value,
  onChange,
  disabled = false,
}: {
  question: Question;
  value: Response | undefined;
  onChange: (response: Response) => void;
  disabled?: boolean;
}) {
  const t = useT();
  const payload = question.payload;

  if (question.type === 'mcq' || question.type === 'true_false') {
    const options =
      question.type === 'mcq'
        ? (payload.options ?? [])
        : [t.question.trueLabel, t.question.falseLabel];
    return (
      <ul className="mt-6 space-y-2">
        {options.map((option, index) => {
          const chosen =
            question.type === 'mcq'
              ? value?.choice === index
              : value?.answer === (index === 0);
          return (
            <li key={option}>
              <button
                type="button"
                disabled={disabled}
                onClick={() =>
                  onChange(
                    question.type === 'mcq'
                      ? { choice: index }
                      : { answer: index === 0 },
                  )
                }
                className={`w-full rounded-md border px-4 py-2.5 text-left text-sm transition-colors duration-state disabled:opacity-70 ${
                  chosen
                    ? 'border-ink-900 text-ink-900'
                    : 'border-line text-ink-700 hover:border-ink-400'
                }`}
              >
                {option}
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  if (question.type === 'fill_blank') {
    return (
      <input
        type="text"
        value={String(value?.text ?? '')}
        disabled={disabled}
        onChange={(event) => onChange({ text: event.target.value })}
        placeholder={t.question.missingWord}
        autoComplete="off"
        className="mt-6 block w-full max-w-sm rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 disabled:opacity-70"
      />
    );
  }

  if (question.type === 'ordering') {
    // The server sends them shuffled; the learner's arrangement is the answer.
    const current = (value?.order as string[] | undefined) ?? payload.items ?? [];

    function move(index: number, direction: -1 | 1) {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) return;
      [next[index], next[target]] = [next[target]!, next[index]!];
      onChange({ order: next });
    }

    return (
      <ol className="mt-6 space-y-2">
        {current.map((item, index) => (
          <li
            key={item}
            className="flex items-center justify-between rounded-md border border-line px-4 py-2.5"
          >
            <span className="text-sm text-ink-800">
              <span className="mr-3 font-mono text-xs text-ink-400">{index + 1}</span>
              {item}
            </span>
            <span className="flex gap-1">
              <button
                type="button"
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                aria-label={t.question.moveUp(item)}
                className="px-2 text-sm text-ink-500 transition-colors duration-state hover:text-ink-900 disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                disabled={disabled || index === current.length - 1}
                onClick={() => move(index, 1)}
                aria-label={t.question.moveDown(item)}
                className="px-2 text-sm text-ink-500 transition-colors duration-state hover:text-ink-900 disabled:opacity-30"
              >
                ↓
              </button>
            </span>
          </li>
        ))}
      </ol>
    );
  }

  if (question.type === 'matching') {
    const left = payload.left ?? [];
    const right = payload.right ?? [];
    const pairs = (value?.pairs as Record<string, string> | undefined) ?? {};

    return (
      <ul className="mt-6 space-y-3">
        {left.map((key) => (
          <li key={key} className="flex flex-wrap items-center gap-3">
            <span className="min-w-40 text-sm text-ink-800">{key}</span>
            <select
              value={pairs[key] ?? ''}
              disabled={disabled}
              onChange={(event) =>
                onChange({ pairs: { ...pairs, [key]: event.target.value } })
              }
              className="rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 disabled:opacity-70"
            >
              <option value="">—</option>
              {right.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
    );
  }

  // open and code
  return (
    <textarea
      value={String(value?.text ?? '')}
      disabled={disabled}
      onChange={(event) => onChange({ text: event.target.value })}
      rows={6}
      placeholder={t.question.ownWords}
      className="mt-6 w-full rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 disabled:opacity-70"
    />
  );
}

/** Whether there is enough of an answer to submit. */
export function isAnswered(question: Question, value: Response | undefined): boolean {
  if (!value) return false;
  if (question.type === 'mcq') return typeof value.choice === 'number';
  if (question.type === 'true_false') return typeof value.answer === 'boolean';
  if (question.type === 'ordering') return Array.isArray(value.order);
  if (question.type === 'matching') {
    const pairs = value.pairs as Record<string, string> | undefined;
    const left = question.payload.left ?? [];
    return Boolean(pairs) && left.every((key) => pairs?.[key]);
  }
  return String(value.text ?? '').trim().length > 0;
}
