'use client';

/**
 * Start something new: one question, then the lesson.
 *
 * This used to be five steps (subject, level, purpose, mode, a preview), and
 * the answers were stitched into a sentence — "I want to learn X. I'm
 * starting from zero. It's out of curiosity." — that appeared in the chat as
 * if the learner had typed it. Now the learner's own words open the lesson,
 * and the Professor asks where they are himself, as a teacher would
 * (`Move.DIAGNOSE` in the API). Focus mode lives in the rail and Settings.
 */

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Mino } from '@/components/mino/Mino';
import { Shell } from '@/components/Shell';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useT } from '@/lib/i18n';
import { track } from '@/lib/analytics';
import { openingLine } from '@/lib/opening';
import { rememberPrefill, takePrefill } from '@/lib/prefill';

export default function NewLearningPage() {
  const router = useRouter();
  const t = useT();
  const copy = t.learnNew;

  const [subject, setSubject] = useState('');
  const [typing, setTyping] = useState(false);
  const [busy, setBusy] = useState(false);

  // A subject typed on the landing page or on Home lands here first, so
  // nobody types it twice.
  useEffect(() => {
    const carried = takePrefill();
    if (carried) setSubject(carried.text);
  }, []);

  const trimmed = subject.trim();

  function start() {
    if (!trimmed || busy) return;
    setBusy(true);
    track('onboarding_completed');
    track('learning_goal_created');
    rememberPrefill(openingLine(trimmed, copy.firstTurn), true);
    router.push('/chat?new=1');
  }

  return (
    <Shell>
      <div className="mx-auto max-w-reading pt-6 sm:pt-12">
        <div className="flex items-start gap-6">
          <Mino state={busy ? 'thinking' : typing ? 'listening' : 'curious'} size="lg" className="hidden sm:block" />
          <form
            className="min-w-0 flex-1"
            onSubmit={(event) => {
              event.preventDefault();
              start();
            }}
          >
            <label htmlFor="learn-subject" className="font-display text-2xl text-ink-900 sm:text-3xl">
              {copy.subjectQuestion}
            </label>
            <Input
              id="learn-subject"
              size="lg"
              value={subject}
              autoFocus
              autoComplete="off"
              enterKeyHint="go"
              onChange={(event) => {
                setSubject(event.target.value);
                setTyping(Boolean(event.target.value));
              }}
              onFocus={() => setTyping(true)}
              onBlur={() => setTyping(false)}
              placeholder={copy.subjectPlaceholder}
              className="mt-6 w-full"
            />
            <div className="mt-6">
              <Button type="submit" variant="primary" size="lg" disabled={!trimmed} busy={busy ? copy.starting : undefined}>
                {copy.start}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </Shell>
  );
}
