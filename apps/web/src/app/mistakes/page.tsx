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
import { ProgressTabs } from '@/components/progress/ProgressTabs';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Mistake, type Question } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function MistakesPage() {
  const router = useRouter();
  const t = useT();
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [drilling, setDrilling] = useState<Question[] | null>(null);
  const [belief, setBelief] = useState<string | null>(null);
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
      setError(err instanceof Error ? err.message : t.mistakes.couldNotLoad);
    } finally {
      setLoading(false);
    }
  }, [router, t]);

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
        setError(t.mistakes.noLongerAvailable);
        return;
      }
      setDrilling(questions);
      setIndex(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.mistakes.couldNotStartDrill);
    }
  }

  async function drill(mistake: Mistake) {
    // Not the same question again: someone holding a coherent wrong model
    // answers it the same way. These are written to disagree with that model.
    setError(null);
    try {
      const written = await api.drills(mistake.id);
      if (written.questions.length === 0) {
        setError(written.belief || t.mistakes.slipNotBelief);
        return;
      }
      setBelief(written.belief);
      setDrilling(written.questions);
      setIndex(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.mistakes.couldNotWriteDrills);
    }
  }

  const misconceptions = mistakes.filter((m) => m.is_misconception);
  const rest = mistakes.filter((m) => !m.is_misconception);

  if (drilling) {
    const current = drilling[index];
    return (
      <Shell>
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="font-display text-2xl text-ink-900">{t.mistakes.practising}</h1>
          <button
            type="button"
            onClick={() => {
              setDrilling(null);
              setBelief(null);
              void load();
            }}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {t.common.stop}
          </button>
        </header>

        {belief && (
          <p className="mt-6 max-w-reading border-l-2 border-critical pl-4 text-base text-ink-700">
            {t.mistakes.youBelieve(belief)}
          </p>
        )}

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
                {index + 1 === drilling.length ? t.common.finish : t.common.next}
              </button>
            </div>
          </div>
        ) : null}
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.mistakes.title}</h1>
        {mistakes.length > 0 && (
          <button
            type="button"
            onClick={() => void practise(mistakes.slice(0, 10))}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-700 transition-colors duration-state hover:border-ink-400"
          >
            {t.mistakes.practiseThese}
          </button>
        )}
      </header>
      <ProgressTabs />

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">{t.common.loading}</p>
      ) : mistakes.length === 0 ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">{t.mistakes.emptyTitle}</h2>
          <p className="mt-2 text-base text-ink-600">
            {t.mistakes.emptyBody}
          </p>
        </div>
      ) : (
        <>
          {misconceptions.length > 0 && (
            <section className="mt-12 max-w-reading">
              <h2 className="text-xs uppercase tracking-wide text-critical">
                {t.mistakes.confidentlyWrong}
              </h2>
              <p className="mt-2 text-sm text-ink-600">
                {t.mistakes.confidentlyWrongLede}
              </p>
              <ul className="mt-4 divide-y divide-line border-y border-line">
                {misconceptions.map((mistake) => (
                  <li key={mistake.id} className="py-3">
                    <p className="text-sm text-ink-800">{mistake.prompt}</p>
                    <span className="mt-1 flex gap-4">
                      <button
                        type="button"
                        onClick={() => void practise([mistake])}
                        className="text-xs text-ink-500 transition-colors duration-state hover:text-ink-900"
                      >
                        {t.mistakes.tryAgain}
                      </button>
                      <button
                        type="button"
                        onClick={() => void drill(mistake)}
                        className="text-xs text-accent"
                      >
                        {t.mistakes.breakBelief}
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {rest.length > 0 && (
            <section className="mt-12 max-w-reading">
              <h2 className="text-xs uppercase tracking-wide text-ink-500">
                {t.mistakes.everythingElse}
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
                      {t.mistakes.tryAgain}
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
