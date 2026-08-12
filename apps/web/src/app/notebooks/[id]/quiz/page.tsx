'use client';

/**
 * A quiz over one notebook.
 *
 * Recall practice, not a test with a grade at the end: the score exists to tell
 * the mastery engine something, and the feedback exists to tell the learner
 * something. So the summary at the end counts what was missed and points at the
 * mistake bank rather than congratulating a percentage.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { QuestionCard } from '@/components/QuestionCard';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Answer, type Question } from '@/lib/api';

export default function QuizPage() {
  const params = useParams<{ id: string }>();
  const notebookId = params.id;
  const router = useRouter();

  const [questions, setQuestions] = useState<Question[]>([]);
  const [index, setIndex] = useState(0);
  const [graded, setGraded] = useState<Answer[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setQuestions(await api.questions(notebookId));
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not load questions.');
    } finally {
      setLoading(false);
    }
  }, [notebookId, router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      const fresh = await api.generateQuestions(notebookId);
      setQuestions(fresh);
      setIndex(0);
      setGraded([]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Questions could not be generated from this notebook.',
      );
    } finally {
      setGenerating(false);
    }
  }

  const current = questions[index];
  const answeredAll = questions.length > 0 && index >= questions.length;
  const wrong = graded.filter((a) => !a.is_correct).length;

  return (
    <Shell>
      <header className="flex items-baseline justify-between">
        <h1 className="font-display text-2xl text-ink-900">Quiz</h1>
        <Link
          href={`/notebooks/${notebookId}`}
          className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
        >
          Back to notebook
        </Link>
      </header>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">Loading…</p>
      ) : answeredAll ? (
        <div className="mt-16 max-w-reading">
          <h2 className="font-display text-xl text-ink-900">Done.</h2>
          <p className="mt-3 text-base text-ink-700">
            {wrong === 0
              ? `${graded.length} answered, none missed. Those concepts are scheduled further out now.`
              : `${graded.length} answered, ${wrong} missed. The ones you got wrong are in your mistakes, with what you said and why it was marked down.`}
          </p>
          <div className="mt-6 flex gap-3">
            {wrong > 0 && (
              <Link
                href="/mistakes"
                className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50"
              >
                Review the misses
              </Link>
            )}
            <button
              type="button"
              onClick={generate}
              disabled={generating}
              className="rounded-md border border-line px-4 py-2 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
            >
              {generating ? 'Writing questions…' : 'New questions'}
            </button>
          </div>
        </div>
      ) : questions.length === 0 ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">No questions yet.</h2>
          <p className="mt-2 text-base text-ink-600">
            Questions are written from what you put in this notebook, so upload a
            document or write a note first. Generated questions are drafts — they can
            be wrong, and answering them still teaches you nothing if the source was
            thin.
          </p>
          <button
            type="button"
            onClick={generate}
            disabled={generating}
            className="mt-6 rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 disabled:opacity-40"
          >
            {generating ? 'Writing questions…' : 'Generate questions'}
          </button>
        </div>
      ) : current ? (
        <div className="mt-12">
          <QuestionCard
            question={current}
            index={index}
            total={questions.length}
            onGraded={(answer) => setGraded((current) => [...current, answer])}
          />

          <div className="mx-auto mt-10 max-w-reading">
            <button
              type="button"
              onClick={() => setIndex((i) => i + 1)}
              className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
            >
              {index + 1 === questions.length ? 'Finish →' : 'Next question →'}
            </button>
          </div>
        </div>
      ) : null}
    </Shell>
  );
}
