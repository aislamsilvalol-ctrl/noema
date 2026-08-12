'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Shell } from '@/components/Shell';
import { ApiError, api, type SessionPlan } from '@/lib/api';

const BUDGETS = [10, 20, 30, 45, 60];

const BLOCK_LABELS: Record<string, string> = {
  warmup: 'Warm up',
  repair: 'Repair',
  practice: 'Practice',
  cooldown: 'Wind down',
};

const KIND_LABELS: Record<string, string> = {
  card_review: 'review',
  card_learn: 'new card',
  question: 'question',
  misconception_drill: 'misconception',
  prereq_repair: 'prerequisite',
  read: 'reading',
};

export default function TodayPage() {
  const router = useRouter();
  const [minutes, setMinutes] = useState(30);
  const [plan, setPlan] = useState<SessionPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (budget: number) => {
      setLoading(true);
      try {
        setPlan(await api.plan(budget));
        setError(null);
      } catch (err) {
        if (err instanceof ApiError && err.isUnauthorized) {
          router.push('/login');
          return;
        }
        setError(err instanceof Error ? err.message : 'Could not build a plan.');
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    void load(minutes);
  }, [load, minutes]);

  const empty = plan !== null && plan.blocks.length === 0;

  return (
    <Shell>
      <header>
        <h1 className="font-display text-2xl text-ink-900">Today</h1>
        {plan && (
          // The engine's reasoning, not a summary of it. If this sentence is not
          // useful, the problem is upstream in the engine.
          <p className="mt-2 max-w-reading font-serif text-md text-ink-700">
            {plan.rationale}
          </p>
        )}
      </header>

      <div className="mt-6 flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-ink-500">I have</span>
        {BUDGETS.map((budget) => (
          <button
            key={budget}
            type="button"
            onClick={() => setMinutes(budget)}
            className={`rounded-md px-2.5 py-1 text-sm transition-colors duration-state ${
              budget === minutes
                ? 'bg-ink-900 text-ink-50'
                : 'text-ink-600 hover:text-ink-900'
            }`}
          >
            {budget}m
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="mt-6 text-sm text-critical">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-10 text-sm text-ink-500">Planning…</p>
      ) : empty ? (
        <div className="mt-16 max-w-reading">
          <h2 className="text-lg text-ink-900">Nothing to do right now.</h2>
          <p className="mt-2 text-base text-ink-600">
            Nothing is due and nothing is weak enough to drill. Studying anyway would
            not help you remember longer — add material, or come back when something
            is due.
          </p>
        </div>
      ) : (
        plan && (
          <>
            <ol className="mt-10 max-w-reading space-y-8">
              {plan.blocks.map((block, index) => (
                <li key={`${block.kind}-${index}`} className="border-t border-line pt-4">
                  <div className="flex items-baseline justify-between">
                    <h2 className="text-md text-ink-900">
                      {BLOCK_LABELS[block.kind] ?? block.kind}
                    </h2>
                    <span className="font-mono text-xs text-ink-400">
                      {block.minutes < 1 ? '<1' : Math.round(block.minutes)} min
                    </span>
                  </div>

                  {/* Why this block is here, in the engine's own words. */}
                  <p className="mt-1 text-sm text-ink-600">{block.why}</p>

                  <p className="mt-2 text-xs text-ink-400">
                    {summarise(block.items.map((item) => item.kind))}
                    {block.items.some((i) => i.concept_name) && (
                      <>
                        {' · '}
                        {[
                          ...new Set(
                            block.items.map((i) => i.concept_name).filter(Boolean),
                          ),
                        ]
                          .slice(0, 3)
                          .join(', ')}
                      </>
                    )}
                  </p>
                </li>
              ))}
            </ol>

            <div className="mt-10 flex items-center gap-4">
              <button
                type="button"
                onClick={() => router.push('/review')}
                className="rounded-md bg-ink-900 px-5 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
              >
                Start session
              </button>
              <span className="text-sm text-ink-500">
                about {Math.round(plan.estimated_minutes)} minutes
              </span>
            </div>
          </>
        )
      )}
    </Shell>
  );
}

/** "8 reviews, 2 questions" — counts by kind, in the order they appear. */
function summarise(kinds: string[]): string {
  const counts = new Map<string, number>();
  for (const kind of kinds) counts.set(kind, (counts.get(kind) ?? 0) + 1);

  return [...counts.entries()]
    .map(([kind, count]) => {
      const label = KIND_LABELS[kind] ?? kind;
      return `${count} ${label}${count === 1 ? '' : 's'}`;
    })
    .join(', ');
}
