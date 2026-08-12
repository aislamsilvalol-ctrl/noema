'use client';

/**
 * The mistake bank.
 *
 * Misconceptions first — not because they are older or more numerous, but because
 * a confident wrong answer is the one failure spaced repetition cannot catch by
 * itself: the learner has no sense of having got it wrong, so nothing prompts
 * them to look again.
 *
 * The list is not the point. Answering the same question again is, so each row
 * leads back into the question rather than sitting there as a tally of failures.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { QuestionCard } from '@/components/QuestionCard';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Mistake, type Question } from '@/lib/api';

export default function MistakesPage() {
  const router = useRouter();
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [drilling, setDrilling] = useState<Question[] | null>(null);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMistakes(await api.mistakes());
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'Could not load your mistakes.');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function practise(subset: Mistake[]) {
    setError(null);
    try {
      // Fetched one at a time on purpose: a mistake's question may have been
      // deleted since, and one missing question should cost that row rather than
      // the whole session.
      const questions: Question[] = [];
      for (const mistake of subset) {
        try {
          questions.push(await api.question(mistake.question_id));
        } catch {
          continue;
        }
      }
      if (questions.length === 0) {
        setError('Those questions are no longer available.');
        return;
      }
      setDrilling(questions);
      setIndex(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the drill.');
    }
  }

  const misconceptions = mistakes.filter((m) => m.is_misconception);
  const rest = mistakes.filter((m) => !m.is_misconception);

  if (drilling) {
    const current = drilling[index];
    return (
      <Shell>
        <header className="flex items-baseline justify-between">
          <h1 className="font-display text-2xl text-ink-900">Practising misses</h1>
          <button
            type="button"
            onClick={() => {
              setDrilling(null);
              void load();
            }}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            Stop
          </button>
        </header>

        {current ? (
          <div className="mt-12">
            <QuestionCard
              question={current}
              index={index}
              total={drilling.length}
              onGraded={() => undefined}
            />
            <div className="mx-auto mt-10 max-w-reading">
              <button
                type="button"
                onClick={() => {
                  if (index + 1 < drilling.length) setIndex(index + 1);
                  else {
                    setDrilling(null);
                    void load();
                  }
                }}
                className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
              >
                {index + 1 === drilling.length ? 'Finish →' : 'Next →'}
              </button>
            </div>
          </div>
        ) : null}
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="flex items-baseline justify-between">
        <h1 className="font-display text-2xl text-ink-900">Mistakes</h1>
        {mistakes.length > 0 && (
          <button
            type="button"
            onClick={() => void practise(mistakes.slice(0, 10))}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            Practise these
          </button>
        )}
      </header>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">Loading…</p>
      ) : mistakes.length === 0 ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">Nothing here.</h2>
          <p className="mt-2 text-base text-ink-600">
            Answer some questions and the ones you get wrong land here — with what
            you said, so you can see the shape of the error rather than just that
            there was one.
          </p>
        </div>
      ) : (
        <>
          {misconceptions.length > 0 && (
            <section className="mt-12 max-w-reading">
              <h2 className="text-xs uppercase tracking-wide text-critical">
                Confidently wrong
              </h2>
              <p className="mt-2 text-sm text-ink-600">
                You were sure and it was wrong. These come first because nothing else
                will prompt you to look at them again.
              </p>
              <ul className="mt-4 divide-y divide-line border-y border-line">
                {misconceptions.map((mistake) => (
                  <li key={mistake.id} className="py-3">
                    <p className="text-sm text-ink-800">{mistake.prompt}</p>
                    <button
                      type="button"
                      onClick={() => void practise([mistake])}
                      className="mt-1 text-xs text-accent"
                    >
                      Try it again →
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {rest.length > 0 && (
            <section className="mt-12 max-w-reading">
              <h2 className="text-xs uppercase tracking-wide text-ink-500">
                Everything else
              </h2>
              <ul className="mt-4 divide-y divide-line border-y border-line">
                {rest.map((mistake) => (
                  <li key={mistake.id} className="py-3">
                    <p className="text-sm text-ink-800">{mistake.prompt}</p>
                    <button
                      type="button"
                      onClick={() => void practise([mistake])}
                      className="mt-1 text-xs text-accent"
                    >
                      Try it again →
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </Shell>
  );
}
