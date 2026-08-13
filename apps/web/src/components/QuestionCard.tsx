'use client';

/**
 * One question, answered and graded.
 *
 * The inputs live in `QuestionInput`, shared with the exam, so the answer to
 * "how do you answer an ordering question" has one implementation.
 *
 * Confidence is asked *after* the answer and before the verdict. Before the
 * answer it changes the answer; after the verdict it is a memory of how you feel
 * now, not how sure you were. That gap is the whole point: a confident wrong
 * answer is the failure spaced repetition never catches on its own.
 */

import { useEffect, useRef, useState } from 'react';
import { QuestionInput, isAnswered, type Response } from '@/components/QuestionInput';
import { api, type Answer, type Question } from '@/lib/api';

const CONFIDENCE = ['Guess', 'Unsure', 'Somewhat', 'Confident', 'Certain'];

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
  const [response, setResponse] = useState<Response | undefined>(undefined);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    setStage('answering');
    setResponse(undefined);
    setAnswer(null);
    setError(null);
    startedAt.current = Date.now();
  }, [question.id]);

  const ready = isAnswered(question, response);

  async function submit(confidence?: number) {
    if (!response) return;

    try {
      const graded = await api.answer(
        question.id,
        response,
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

      <QuestionInput
        question={question}
        value={response}
        onChange={setResponse}
        disabled={stage !== 'answering'}
      />

      {stage === 'answering' && (
        <button
          type="button"
          onClick={() => setStage('confidence')}
          disabled={!ready}
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
