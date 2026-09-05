'use client';

/**
 * A checkpoint or micro-assessment, answered inside the lesson.
 *
 * The paper arrives without its answers (the server strips them); the
 * learner answers every question — an option, true/false, a short answer, an
 * ordering, a paragraph — and hands it in once. Grading comes back per
 * question and per concept; the correction itself is Mino's next turn, asked
 * for by the hook when the paper is submitted. No timer: a checkpoint is a
 * look at what stayed, not a race.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import type { AssessmentView } from '@/lib/api';
import { useT } from '@/lib/i18n';

type Question = AssessmentView['questions'][number];
type Result = {
  index: number;
  concept: string;
  score: number;
  correct: boolean;
  feedback: string;
  explanation: string;
  expected: unknown;
};

export function ExamView({
  assessment,
  onSubmit,
}: {
  assessment: AssessmentView;
  onSubmit: (responses: unknown[]) => Promise<unknown>;
}) {
  const t = useT();
  const [responses, setResponses] = useState<Record<number, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitted = assessment.status === 'submitted';
  const results = (assessment.results as { questions?: Result[]; weak?: string[] } | undefined) ?? {};
  const byIndex = new Map((results.questions ?? []).map((r) => [r.index, r]));

  function set(index: number, value: unknown) {
    setResponses((current) => ({ ...current, [index]: value }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(assessment.questions.map((q) => responses[q.index] ?? null));
    } catch {
      setError(t.professor.exam.couldNotSubmit);
    } finally {
      setBusy(false);
    }
  }

  const answered = assessment.questions.filter((q) => responses[q.index] !== undefined).length;

  return (
    <section
      aria-label={assessment.title}
      className="my-3 rounded-lg border border-signal bg-raised p-5 shadow-elevation-2"
      data-lesson-exam
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-signal">
          {assessment.kind === 'checkpoint' ? t.professor.exam.checkpoint : t.professor.exam.micro}
        </p>
        {submitted && assessment.score !== null && assessment.score !== undefined && (
          <p className="font-mono text-xs text-ink-600">
            {t.professor.exam.score(Math.round(assessment.score * 100))}
          </p>
        )}
      </div>
      <h3 className="mt-1 font-display text-lg text-ink-900">{assessment.title}</h3>

      <ol className="mt-5 space-y-6">
        {assessment.questions.map((question, number) => {
          const result = byIndex.get(question.index);
          return (
            <li key={question.index} className="border-l-2 border-line pl-4">
              <p className="text-xs text-ink-400">
                {number + 1} · {question.concept}
              </p>
              <p className="mt-1 text-base text-ink-900">{question.prompt}</p>
              <div className="mt-3">
                <Answer
                  question={question}
                  value={responses[question.index]}
                  onChange={(value) => set(question.index, value)}
                  disabled={submitted}
                />
              </div>
              {result && (
                <div className={`mt-3 border-l-2 pl-3 ${result.correct ? 'border-positive' : 'border-critical'}`}>
                  <p className={`text-sm font-medium ${result.correct ? 'text-positive' : 'text-critical'}`}>
                    {result.correct ? t.question.correct : t.question.notQuite}
                  </p>
                  {!result.correct && result.expected !== null && result.expected !== undefined && (
                    <p className="mt-1 text-sm text-ink-700">
                      {t.professor.exam.expected}:{' '}
                      {Array.isArray(result.expected) ? result.expected.join(' → ') : String(result.expected)}
                    </p>
                  )}
                  {result.explanation && <p className="mt-1 text-sm text-ink-600">{result.explanation}</p>}
                  {result.feedback && <p className="mt-1 text-sm text-ink-600">{result.feedback}</p>}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {!submitted && (
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <Button
            variant="primary"
            onClick={() => void submit()}
            busy={busy ? t.professor.exam.submitting : undefined}
            disabled={answered === 0}
          >
            {t.professor.exam.submit}
          </Button>
          <span className="text-xs text-ink-400">
            {t.professor.exam.answered(answered, assessment.questions.length)}
          </span>
          {error && (
            <span role="alert" className="text-sm text-critical">
              {error}
            </span>
          )}
        </div>
      )}
      {submitted && results.weak && results.weak.length > 0 && (
        <p className="mt-5 text-sm text-ink-600">{t.professor.exam.weak(results.weak)}</p>
      )}
    </section>
  );
}

function Answer({
  question,
  value,
  onChange,
  disabled,
}: {
  question: Question;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled: boolean;
}) {
  const t = useT();
  const optionTone = (selected: boolean) =>
    selected ? 'border-signal text-ink-900' : 'border-line text-ink-800 hover:border-ink-400';

  if (question.type === 'mcq') {
    return (
      <ul className="space-y-2" role="group" aria-label={question.prompt}>
        {(question.options ?? []).map((option, index) => (
          <li key={option}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(index)}
              aria-pressed={value === index}
              className={`w-full rounded-md border bg-raised px-4 py-2.5 text-left text-sm transition-colors duration-fast disabled:opacity-80 ${optionTone(value === index)}`}
            >
              {option}
            </button>
          </li>
        ))}
      </ul>
    );
  }
  if (question.type === 'true_false') {
    return (
      <div className="flex gap-2" role="group" aria-label={question.prompt}>
        {[true, false].map((choice) => (
          <button
            key={String(choice)}
            type="button"
            disabled={disabled}
            onClick={() => onChange(choice)}
            aria-pressed={value === choice}
            className={`rounded-md border bg-raised px-4 py-2 text-sm transition-colors duration-fast disabled:opacity-80 ${optionTone(value === choice)}`}
          >
            {choice ? t.question.trueLabel : t.question.falseLabel}
          </button>
        ))}
      </div>
    );
  }
  if (question.type === 'ordering') {
    const items = (value as string[] | undefined) ?? question.items ?? [];
    const move = (from: number, to: number) => {
      if (to < 0 || to >= items.length) return;
      const next = [...items];
      const [item] = next.splice(from, 1);
      if (item !== undefined) next.splice(to, 0, item);
      onChange(next);
    };
    return (
      <ol className="space-y-1.5">
        {items.map((item, index) => (
          <li key={item} className="flex items-center gap-2 rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-800">
            <span className="w-4 font-mono text-xs text-ink-400">{index + 1}</span>
            <span className="flex-1">{item}</span>
            {!disabled && (
              <>
                <button type="button" onClick={() => move(index, index - 1)} aria-label={t.question.moveUp(item)} className="px-1 text-ink-500 hover:text-ink-900">↑</button>
                <button type="button" onClick={() => move(index, index + 1)} aria-label={t.question.moveDown(item)} className="px-1 text-ink-500 hover:text-ink-900">↓</button>
              </>
            )}
          </li>
        ))}
      </ol>
    );
  }
  // short · fill_blank · open
  const long = question.type === 'open';
  return (
    <textarea
      value={typeof value === 'string' ? value : ''}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      rows={long ? 4 : 1}
      placeholder={long ? t.question.ownWords : t.question.missingWord}
      aria-label={question.prompt}
      className="w-full resize-none rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 outline-none transition-colors duration-fast focus:border-signal placeholder:text-ink-400 disabled:opacity-80"
    />
  );
}
