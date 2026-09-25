'use client';

/**
 * Stopping for today: what the lesson left, in the engine's own state — what
 * you know, what is still shaky, where we are, what comes next — and what the
 * day added. The lesson stays open; tomorrow's Continue picks it up here.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Mino } from '@/components/mino/Mino';
import { SessionProgress } from '@/components/progress/Progression';
import { Button } from '@/components/ui/Button';
import { api, type JourneyRecap } from '@/lib/api';
import { useT } from '@/lib/i18n';

export function LessonRecap({
  journeyId,
  onKeepGoing,
}: {
  journeyId: string | null;
  onKeepGoing: () => void;
}) {
  const t = useT();
  const focus = t.professor.focus;
  const [recap, setRecap] = useState<JourneyRecap | null>(null);

  useEffect(() => {
    if (!journeyId) return;
    let cancelled = false;
    api
      .journeyRecap(journeyId)
      .then((value) => {
        if (!cancelled) setRecap(value);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [journeyId]);

  const rows: [string, string[]][] = recap
    ? [
        [focus.recapKnow, recap.know],
        [t.chat.summaryShaky, recap.shaky],
        [focus.recapNow, recap.now ? [recap.now] : []],
        [focus.recapNext, recap.next],
      ]
    : [];

  return (
    <section className="mt-10 border-t border-line pt-8" aria-labelledby="lesson-summary" data-lesson-summary>
      <div className="flex items-center gap-4">
        <Mino state="happy" size="sm" />
        <h2 id="lesson-summary" className="font-display text-2xl text-ink-900">
          {t.chat.summaryTitle}
        </h2>
      </div>
      {rows.length > 0 && (
        <dl className="mt-6 divide-y divide-line border-y border-line">
          {rows.map(([label, items]) => (
            <div key={label} className="grid gap-1 py-4 sm:grid-cols-[10rem_1fr] sm:gap-4">
              <dt className="text-sm text-ink-500">{label}</dt>
              <dd className="text-base text-ink-900">
                {items.length ? items.join(' · ') : focus.recapNothingYet}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <SessionProgress />
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Button variant="primary" size="lg" onClick={onKeepGoing}>
          {t.chat.summaryKeepGoing}
        </Button>
        <Link
          href="/today"
          className="inline-flex min-h-12 items-center justify-center px-4 text-base text-ink-700 underline-offset-4 hover:underline"
        >
          {t.chat.summaryHome}
        </Link>
      </div>
    </section>
  );
}
