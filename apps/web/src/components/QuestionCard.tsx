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
import { Mino } from '@/components/mino/Mino';
import { QuestionInput, isAnswered, type Response } from '@/components/QuestionInput';
import { Button } from '@/components/ui/Button';
import { api, type Answer, type Question } from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

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
  const t = useT();
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
      setError(humanError(err, t, 'save'));
      setStage('answering');
    }
  }

  return (
    <div className="mx-auto max-w-reading">
      <div className="flex items-center gap-3">
        <Mino
          state={answer ? (answer.is_correct ? 'celebrating' : 'focused') : 'reviewing'}
          size="sm"
        />
        <p className="text-xs text-ink-500">
          {t.question.positionOf(index + 1, total, question.difficulty)}
        </p>
      </div>

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
        <Button
          variant="primary"
          className="mt-6"
          onClick={() => setStage('confidence')}
          disabled={!ready}
        >
          {t.question.answerCta}
        </Button>
      )}

      {stage === 'confidence' && (
        <div className="mt-8">
          <p className="text-sm text-ink-600">{t.question.howConfident}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {t.question.confidence.map((label, i) => (
              <Button key={label} variant="secondary" size="sm" onClick={() => void submit(i + 1)}>
                {label}
              </Button>
            ))}
            <Button variant="ghost" size="sm" onClick={() => void submit()}>
              {t.common.skip}
            </Button>
          </div>
        </div>
      )}

      {answer && (
        <div
          className={`mt-8 border-l-2 pl-4 ${answer.is_correct ? 'border-positive' : 'border-critical'}`}
        >
          <p
            className={`text-sm font-medium ${answer.is_correct ? 'text-positive' : 'text-critical'}`}
          >
            {answer.is_correct ? t.question.correct : t.question.notQuite}
            <span className="ml-2 text-ink-400">
              {Math.round(answer.score * 100)}%
              {answer.grader === 'self' && t.question.gradedByYou}
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
                  {t.question.whatWasMissing}
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
