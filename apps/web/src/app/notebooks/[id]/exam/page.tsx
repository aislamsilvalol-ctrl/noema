'use client';

/**
 * Exam mode.
 *
 * The tutor panel is gone, nothing is marked until the paper is handed in, and
 * every question is on one page so you can skip and come back. A timer runs, but
 * running out does not throw the work away — it hands in what is there and says
 * it was late.
 *
 * The result is a list of concepts, weakest first. A percentage is a feeling; a
 * list of concepts is a plan.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { QuestionInput, type Response } from '@/components/QuestionInput';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Exam, type Question } from '@/lib/api';
import { useT } from '@/lib/i18n';

function remaining(exam: Exam): number {
  const ends = new Date(exam.started_at).getTime() + exam.minutes * 60_000;
  return Math.max(0, Math.round((ends - Date.now()) / 1000));
}

function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function ExamPage() {
  const params = useParams<{ id: string }>();
  const notebookId = params.id;
  const router = useRouter();
  const t = useT();

  const [exam, setExam] = useState<Exam | null>(null);
  const [answers, setAnswers] = useState<Record<string, Response>>({});
  const [left, setLeft] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async (current: Exam, given: Record<string, Response>) => {
      setBusy(true);
      setError(null);
      try {
        setExam(await api.submitExam(current.id, given));
      } catch (err) {
        setError(err instanceof Error ? err.message : t.exam.notAccepted);
      } finally {
        setBusy(false);
      }
    },
    [t],
  );

  // One timer, and it hands the paper in rather than discarding it. A clock that
  // destroys work teaches people to distrust the clock.
  useEffect(() => {
    if (!exam || exam.submitted_at) return;
    setLeft(remaining(exam));

    const timer = setInterval(() => {
      const seconds = remaining(exam);
      setLeft(seconds);
      if (seconds === 0) {
        clearInterval(timer);
        void submit(exam, answers);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [exam, answers, submit]);

  async function start(questions: number, minutes: number) {
    setBusy(true);
    setError(null);
    try {
      setExam(await api.startExam(notebookId, questions, minutes));
      setAnswers({});
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : t.exam.couldNotStart);
    } finally {
      setBusy(false);
    }
  }

  function answer(question: Question, response: Response) {
    setAnswers((current) => ({ ...current, [question.id]: response }));
  }

  const done = exam?.submitted_at != null;
  const concepts = exam?.results.concepts ?? [];

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.exam.title}</h1>
        {exam && !done ? (
          <span
            className={`font-mono text-sm ${left < 60 ? 'text-critical' : 'text-ink-500'}`}
          >
            {clock(left)}
          </span>
        ) : (
          <Link
            href={`/notebooks/${notebookId}`}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {t.common.backToNotebook}
          </Link>
        )}
      </header>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {!exam ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">{t.exam.sitLede}</h2>
          <p className="mt-2 text-base text-ink-600">
            {t.exam.sitBody}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void start(10, 15)}
              disabled={busy}
              className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 disabled:opacity-40"
            >
              {t.exam.tenQuestions}
            </button>
            <button
              type="button"
              onClick={() => void start(20, 30)}
              disabled={busy}
              className="rounded-md border border-line px-4 py-2 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
            >
              {t.exam.twentyQuestions}
            </button>
          </div>
        </div>
      ) : done ? (
        <div className="mt-12 max-w-reading">
          <p className="font-display text-4xl text-ink-900">
            {Math.round((exam.score ?? 0) * 100)}%
          </p>
          {exam.overtime && (
            <p className="mt-2 text-sm text-ink-500">
              {t.exam.overtime}
            </p>
          )}

          <h2 className="mt-10 text-xs uppercase tracking-wide text-ink-500">
            {t.exam.whereItWent}
          </h2>
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {concepts.map((concept) => (
              <li
                key={concept.concept_id ?? concept.name}
                className="flex items-baseline justify-between py-3"
              >
                <span className="text-sm text-ink-800">{concept.name}</span>
                <span
                  className={`font-mono text-sm ${
                    concept.score < 0.5 ? 'text-critical' : 'text-ink-600'
                  }`}
                >
                  {concept.correct}/{concept.total}
                </span>
              </li>
            ))}
          </ul>

          <p className="mt-6 text-base text-ink-700">
            {t.exam.aftermath}
          </p>
          <div className="mt-6 flex gap-3">
            <Link
              href="/mistakes"
              className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50"
            >
              {t.exam.reviewMisses}
            </Link>
            <Link
              href="/progress"
              className="rounded-md border border-line px-4 py-2 text-sm text-ink-700"
            >
              {t.exam.seeMastery}
            </Link>
          </div>
        </div>
      ) : (
        <div className="mt-10 max-w-reading">
          <p className="text-sm text-ink-500">
            {t.exam.answered(Object.keys(answers).length, exam.questions.length)}
          </p>

          <ol className="mt-8 space-y-10">
            {exam.questions.map((question, i) => (
              <li key={question.id}>
                <p className="text-xs text-ink-400">{i + 1}</p>
                <h2 className="mt-2 font-display text-lg leading-snug text-ink-900">
                  {question.prompt}
                </h2>

                <QuestionInput
                  question={question}
                  value={answers[question.id]}
                  onChange={(response) => answer(question, response)}
                />
              </li>
            ))}
          </ol>

          <button
            type="button"
            onClick={() => void submit(exam, answers)}
            disabled={busy}
            className="mt-12 rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 disabled:opacity-40"
          >
            {busy ? t.exam.marking : t.exam.handIn}
          </button>
          <p className="mt-2 text-xs text-ink-400">
            {t.exam.unansweredWrong}
          </p>
        </div>
      )}
    </Shell>
  );
}
