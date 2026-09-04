'use client';

/**
 * "O que você quer aprender?" — the landing page's one interaction.
 *
 * A visitor types a subject and the page answers with the shape of a lesson:
 * a short, clearly-labelled *illustration* of how Noema would organise it,
 * never presented as the product's real output. The real path is generated
 * for a signed-in learner, so the button under the illustration starts that —
 * the subject is carried into the Professor so nobody types it twice.
 *
 * The examples rotate in the placeholder, slowly; they stop the moment the
 * visitor types, and never under reduced motion. Mino reacts through the
 * `onState` callback (listening while typing, thinking on submit) so the
 * character belongs to the interaction rather than decorating it.
 */

import { useEffect, useState } from 'react';
import { Button, ButtonLink } from '@/components/ui/Button';
import type { MinoState } from '@/components/mino/Mino';
import { track } from '@/lib/analytics';
import { useT } from '@/lib/i18n';
import { rememberPrefill } from '@/lib/prefill';

export { PREFILL_KEY } from '@/lib/prefill';

const ROTATE_MS = 2600;

export function HeroAsk({
  signedIn,
  onState,
}: {
  signedIn: boolean;
  onState: (state: MinoState) => void;
}) {
  const t = useT();
  const [subject, setSubject] = useState('');
  const [shown, setShown] = useState<string | null>(null);
  const [example, setExample] = useState(0);

  const examples = t.landing.askExamples;

  useEffect(() => {
    if (subject) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const timer = window.setInterval(
      () => setExample((i) => (i + 1) % examples.length),
      ROTATE_MS,
    );
    return () => window.clearInterval(timer);
  }, [subject, examples.length]);

  function show(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = subject.trim();
    if (!trimmed) return;
    track('cta_clicked', { location: 'hero_ask_illustration' });
    onState('thinking');
    setShown(trimmed);
  }

  function remember() {
    rememberPrefill(shown ?? subject);
    track('cta_clicked', { location: 'hero_ask_start' });
  }

  const steps = t.landing.demoSteps(shown ?? '');

  return (
    <div className="mt-10 max-w-lg">
      <form onSubmit={show}>
        <label htmlFor="hero-ask" className="text-xs uppercase tracking-wide text-ink-500">
          {t.landing.askLabel}
        </label>
        <div className="mt-2 flex gap-2">
          <input
            id="hero-ask"
            value={subject}
            onChange={(event) => {
              setSubject(event.target.value);
              setShown(null);
              onState(event.target.value ? 'listening' : 'curious');
            }}
            onFocus={() => onState('listening')}
            onBlur={() => !subject && onState('curious')}
            placeholder={examples[example]}
            autoComplete="off"
            className="min-w-0 flex-1 rounded-md border border-line bg-raised px-4 py-3 text-base text-ink-900 outline-none transition-colors duration-fast focus:border-signal placeholder:text-ink-400"
          />
          <Button type="submit" variant="primary" size="lg" disabled={!subject.trim()}>
            {t.landing.askCta}
          </Button>
        </div>
      </form>

      {shown && (
        <div className="mt-6 animate-fade-up rounded-lg border border-line bg-raised p-5 shadow-elevation-1">
          <p className="text-xs uppercase tracking-wide text-ink-500">{t.landing.demoTitle}</p>
          <h2 className="mt-1 font-display text-xl text-ink-900">{shown}</h2>
          <ol className="mt-4 space-y-2">
            {steps.map((step, index) => (
              <li key={step} className="flex gap-3 text-base text-ink-700">
                <span className="font-mono text-xs text-signal">{index + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs text-ink-400">{t.landing.demoNote}</p>
          <ButtonLink
            href={signedIn ? '/learn/new' : '/login'}
            variant="primary"
            className="mt-5"
            onClick={remember}
          >
            {t.landing.demoStart(shown)}
          </ButtonLink>
        </div>
      )}
    </div>
  );
}
