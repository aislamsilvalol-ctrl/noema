'use client';

/**
 * Socratic mode: questioned until you say it yourself.
 *
 * Unlike the tutor panel, this one ends. The dialogue is held in the page and
 * sent back each turn — a half-finished conversation is not worth a table — and
 * when the tutor decides the learner got there, the exchange is recorded and the
 * concept's mastery moves.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Mastery, type SocraticTurn } from '@/lib/api';
import { useT } from '@/lib/i18n';

type Entry = { role: 'tutor' | 'learner'; content: string };

export default function SocraticPage() {
  const router = useRouter();
  const t = useT();
  const [concepts, setConcepts] = useState<Mastery[]>([]);
  const [chosen, setChosen] = useState<Mastery | null>(null);
  const [transcript, setTranscript] = useState<Entry[]>([]);
  const [reply, setReply] = useState('');
  const [verdict, setVerdict] = useState<SocraticTurn | null>(null);
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
      setError(err instanceof Error ? err.message : t.socratic.couldNotLoad);
    }
  }, [router, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function advance(concept: Mastery, next: Entry[]) {
    setBusy(true);
    setError(null);
    try {
      const turn = await api.socratic(concept.concept_id, next);
      if (turn.question) {
        setTranscript([...next, { role: 'tutor', content: turn.question }]);
      } else {
        setTranscript(next);
        setVerdict(turn);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t.socratic.couldNotContinue);
    } finally {
      setBusy(false);
    }
  }

  function start(concept: Mastery) {
    setChosen(concept);
    setTranscript([]);
    setVerdict(null);
    void advance(concept, []);
  }

  function answer() {
    if (!chosen || !reply.trim()) return;
    const next: Entry[] = [...transcript, { role: 'learner', content: reply.trim() }];
    setReply('');
    void advance(chosen, next);
  }

  return (
    <Shell>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="font-display text-2xl text-ink-900">{t.socratic.title}</h1>
        {chosen && (
          <button
            type="button"
            onClick={() => {
              setChosen(null);
              setTranscript([]);
              setVerdict(null);
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
            {t.socratic.lede}
          </p>

          {concepts.length === 0 ? (
            <p className="mt-8 text-base text-ink-600">
              {t.socratic.noConcepts}
            </p>
          ) : (
            <ul className="mt-8 divide-y divide-line border-y border-line">
              {concepts.map((concept) => (
                <li key={concept.concept_id}>
                  <button
                    type="button"
                    onClick={() => start(concept)}
                    className="flex w-full items-baseline justify-between py-3 text-left"
                  >
                    <span className="text-sm text-ink-800">{concept.concept_name}</span>
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
          <h2 className="font-display text-xl text-ink-900">{chosen.concept_name}</h2>

          <ol className="mt-8 space-y-6">
            {transcript.map((entry, i) => (
              <li key={`${i}-${entry.content.slice(0, 12)}`}>
                <p className="text-xs uppercase tracking-wide text-ink-400">
                  {entry.role === 'tutor' ? 'NOEMA' : t.socratic.you}
                </p>
                <p
                  className={`mt-1 text-base ${
                    entry.role === 'tutor' ? 'text-ink-900' : 'text-ink-700'
                  }`}
                >
                  {entry.content}
                </p>
              </li>
            ))}
          </ol>

          {busy && <p className="mt-6 text-sm text-ink-500">{t.socratic.thinking}</p>}

          {verdict ? (
            <div className="mt-10 border-t border-line pt-6">
              <p className="text-base text-ink-900">{verdict.assessment}</p>
              <p className="mt-2 text-sm text-ink-500">
                {verdict.reached
                  ? t.socratic.gotThere
                  : verdict.exhausted
                    ? t.socratic.exhausted
                    : t.socratic.recorded}{' '}
                <Link href="/progress" className="text-accent">
                  {t.common.seeMastery}
                </Link>
              </p>
            </div>
          ) : (
            !busy &&
            transcript.length > 0 && (
              <div className="mt-8">
                <textarea
                  value={reply}
                  onChange={(event) => setReply(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault();
                      answer();
                    }
                  }}
                  rows={3}
                  autoFocus
                  placeholder={t.socratic.replyPlaceholder}
                  className="w-full rounded-md border border-line bg-raised px-3 py-2 text-base text-ink-900"
                />
                <div className="mt-3 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={answer}
                    disabled={!reply.trim()}
                    className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 disabled:opacity-40"
                  >
                    {t.socratic.answer}
                  </button>
                  <span className="text-xs text-ink-400">{t.common.enterToSend}</span>
                </div>
              </div>
            )
          )}
        </div>
      )}
    </Shell>
  );
}
