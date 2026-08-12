'use client';

/**
 * One question, answered and graded.
 *
 * The three shapes the generator actually produces get a real input: multiple
 * choice, true/false, and open. Anything else says so plainly instead of
 * rendering a box that cannot be graded — a question you can answer but nobody
 * scores is worse than one that admits it is not ready.
 *
 * Confidence is asked *after* the answer and before the verdict. Before the
 * answer it changes the answer; after the verdict it is a memory of how you feel
 * now, not how sure you were. That gap is the whole point: a confident wrong
 * answer is the failure spaced repetition never catches on its own.
 */

import { useEffect, useRef, useState } from 'react';
import { api, type Answer, type Question } from '@/lib/api';

const CONFIDENCE = ['Guess', 'Unsure', 'Somewhat', 'Confident', 'Certain'];

const UNSUPPORTED: Record<string, string> = {
  fill_blank: 'Fill in the blank',
  matching: 'Matching',
  ordering: 'Ordering',
  code: 'Code',
};

type Stage = 'answering' | 'confidence' | 'graded';

export function QuestionCard({
  question,
  index,
  total,
  onGraded,
}: {
  question: Question;
  index: number;
  total: number;
  onGraded: (answer: Answer) => void;
}) {
  const [stage, setStage] = useState<Stage>('answering');
  const [choice, setChoice] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    setStage('answering');
    setChoice(null);
    setText('');
    setAnswer(null);
    setError(null);
    startedAt.current = Date.now();
  }, [question.id]);

  const options = question.payload.options ?? [];
  const unsupported = UNSUPPORTED[question.type];

  function response(): Record<string, unknown> | null {
    if (question.type === 'mcq') return choice === null ? null : { choice };
    if (question.type === 'true_false')
      return choice === null ? null : { answer: choice === 0 };
    return text.trim() ? { text: text.trim() } : null;
  }

  async function submit(confidence?: number) {
    const body = response();
    if (!body) return;

    try {
      const graded = await api.answer(
        question.id,
        body,
        confidence,
        Date.now() - startedAt.current,
      );
      setAnswer(graded);
      setStage('graded');
      onGraded(graded);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That answer was not recorded.');
      setStage('answering');
    }
  }

  return (
    <div className="mx-auto max-w-reading">
      <p className="text-xs text-ink-400">
        {index + 1} of {total} · {question.difficulty}
      </p>

      <h2 className="mt-6 font-display text-xl leading-snug text-ink-900">
        {question.prompt}
      </h2>

      {unsupported ? (
        <p className="mt-8 border-l-2 border-line pl-4 text-sm text-ink-600">
          {unsupported} questions are generated but cannot be answered here yet, so
          this one is skipped rather than graded by a form that does not know how.
        </p>
      ) : (
        <>
          {(question.type === 'mcq' || question.type === 'true_false') && (
            <ul className="mt-8 space-y-2">
              {(question.type === 'mcq' ? options : ['True', 'False']).map(
                (option, i) => (
                  <li key={option}>
                    <button
                      type="button"
                      disabled={stage !== 'answering'}
                      onClick={() => setChoice(i)}
                      className={`w-full rounded-md border px-4 py-3 text-left text-sm transition-colors duration-state disabled:opacity-70 ${
                        choice === i
                          ? 'border-ink-900 text-ink-900'
                          : 'border-line text-ink-700 hover:border-ink-400'
                      }`}
                    >
                      {option}
                    </button>
                  </li>
                ),
              )}
            </ul>
          )}

          {(question.type === 'open' || question.type === 'code') && (
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              disabled={stage !== 'answering'}
              rows={6}
              placeholder="Answer in your own words."
              className="mt-8 w-full rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 disabled:opacity-70"
            />
          )}

          {stage === 'answering' && (
            <button
              type="button"
              onClick={() => setStage('confidence')}
              disabled={!response()}
              className="mt-6 rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 disabled:opacity-40"
            >
              Answer
            </button>
          )}

          {stage === 'confidence' && (
            <div className="mt-8">
              <p className="text-sm text-ink-600">How confident are you?</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {CONFIDENCE.map((label, i) => (
                  <button
                    key={label}
                    type="button"
                    onClick={() => void submit(i + 1)}
                    className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
                  >
                    {label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => void submit()}
                  className="px-2 py-1.5 text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
                >
                  Skip
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {answer && (
        <div className="mt-8 border-t border-line pt-6">
          <p
            className={`text-sm ${answer.is_correct ? 'text-positive' : 'text-critical'}`}
          >
            {answer.is_correct ? 'Correct' : 'Not quite'}
            <span className="ml-2 text-ink-400">
              {Math.round(answer.score * 100)}%
              {answer.grader === 'self' && ' · graded by you, no model configured'}
            </span>
          </p>

          {answer.feedback?.explanation && (
            <p className="mt-3 text-base text-ink-700">{answer.feedback.explanation}</p>
          )}
          {answer.feedback?.summary && (
            <p className="mt-3 text-base text-ink-700">{answer.feedback.summary}</p>
          )}
          {Array.isArray(answer.feedback?.missing) &&
            answer.feedback.missing.length > 0 && (
              <div className="mt-4">
                <p className="text-xs uppercase tracking-wide text-ink-500">
                  What was missing
                </p>
                <ul className="mt-2 list-disc pl-5 text-sm text-ink-700">
                  {answer.feedback.missing.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
        </div>
      )}

      {error && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
