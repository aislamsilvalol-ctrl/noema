'use client';

/**
 * Feynman mode: explain it, and find out what you were missing.
 *
 * The concept list is ordered by mastery, weakest first, because the point of
 * explaining is to find the holes — and the holes are where the number is low.
 * Nothing here shows the source text before you write: an explanation written
 * with the material open is a transcription.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Shell } from '@/components/Shell';
import { Mino } from '@/components/mino/Mino';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Input';
import { Loading } from '@/components/ui/Loading';
import { Notice } from '@/components/ui/Notice';
import { ApiError, api, type Explanation, type Mastery } from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';

/** Only the list-shaped findings; `next_step` is a sentence and is shown apart. */
type FindingKey = 'gaps' | 'oversimplifications' | 'assumed' | 'contradictions';

const FINDING_KEYS: FindingKey[] = [
  'gaps',
  'oversimplifications',
  'assumed',
  'contradictions',
];

export default function ExplainPage() {
  const router = useRouter();
  const t = useT();
  const [concepts, setConcepts] = useState<Mastery[]>([]);
  const [loading, setLoading] = useState(true);
  const [chosen, setChosen] = useState<Mastery | null>(null);
  const [text, setText] = useState('');
  const [result, setResult] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await api.mastery();
      setConcepts([...rows].sort((a, b) => a.mastery - b.mastery));
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(humanError(err, t, 'load'));
    } finally {
      setLoading(false);
    }
  }, [router, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit() {
    if (!chosen || !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.explain(chosen.concept_id, text));
    } catch (err) {
      setError(humanError(err, t, 'ai'));
    } finally {
      setBusy(false);
    }
  }

  const findings = result
    ? FINDING_KEYS.map((key) => ({
        key,
        label: t.explain.findings[key],
        items: result.findings[key] ?? [],
      })).filter((f) => f.items.length > 0)
    : [];

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.explain.title}</h1>
        {chosen && (
          <button
            type="button"
            onClick={() => {
              setChosen(null);
              setText('');
              setResult(null);
              void load();
            }}
            className="text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
          >
            {t.common.pickAnother}
          </button>
        )}
      </header>

      {error && (
        <p role="alert" className="mt-6 max-w-reading text-sm text-critical">
          {error}
        </p>
      )}

      {!chosen ? (
        <div className="mt-10 max-w-reading">
          <p className="text-base text-ink-600">
            {t.explain.lede}
          </p>

          {loading ? (
            <Loading mino className="mt-8" />
          ) : concepts.length === 0 ? (
            // Nothing to explain until something has been learned: the
            // way forward is the first lesson, not this screen.
            <Notice
              kind="empty"
              title={t.explain.emptyTitle}
              body={t.explain.emptyBody}
              action={{ label: t.explain.emptyAction, href: '/learn/new' }}
              mino={<Mino state="curious" size="lg" />}
              className="mt-8"
            />
          ) : (
            <ul className="mt-8 divide-y divide-line border-y border-line">
              {concepts.map((concept) => (
                <li key={concept.concept_id}>
                  <button
                    type="button"
                    onClick={() => setChosen(concept)}
                    className="flex w-full items-baseline justify-between py-3 text-left"
                  >
                    <span className="text-sm text-ink-800">
                      {concept.concept_name}
                    </span>
                    <span className="font-mono text-xs text-ink-400">
                      {Math.round(concept.mastery)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="mt-10 max-w-reading">
          <h2 className="font-display text-xl text-ink-900">
            {chosen.concept_name}
          </h2>

          {!result ? (
            <>
              <Textarea
                size="lg"
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={12}
                autoFocus
                placeholder={t.explain.placeholder}
                aria-label={t.explain.textareaLabel}
                className="mt-6 w-full leading-relaxed"
              />
              <div className="mt-4 flex items-center gap-4">
                <Button
                  variant="primary"
                  onClick={submit}
                  disabled={text.trim().length < 40}
                  busy={busy ? t.explain.readingIt : undefined}
                >
                  {t.explain.check}
                </Button>
                <span className="text-xs text-ink-400">
                  {/* A one-line "explanation" cannot be evaluated, and saying so
                      up front beats a verdict of zero. */}
                  {text.trim().length < 40 ? t.explain.writeMore : t.explain.nothingShown}
                </span>
              </div>
            </>
          ) : (
            <div className="mt-8">
              <p className="text-sm text-ink-600">
                {t.explain.understood(Math.round(result.score * 100))}
              </p>

              {findings.length === 0 ? (
                <p className="mt-6 text-base text-ink-700">
                  {t.explain.nothingMissing}
                </p>
              ) : (
                findings.map((finding) => (
                  <section key={finding.key} className="mt-8">
                    <h3 className="font-mono text-xs text-ink-500">
                      {finding.label}
                    </h3>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-base text-ink-700">
                      {finding.items.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                ))
              )}

              {result.findings.next_step && (
                <p className="mt-10 border-l-2 border-line pl-4 text-base text-ink-900">
                  {result.findings.next_step}
                </p>
              )}

              <p className="mt-8 text-sm text-ink-500">
                {t.explain.counted(chosen.concept_name)}{' '}
                <Link href="/progress" className="text-accent">
                  {t.common.seeMastery}
                </Link>
              </p>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}
