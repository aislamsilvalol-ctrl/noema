'use client';

/**
 * Create a learning — the first-run moment the audit found missing (§3.3).
 *
 * One open question, at most two follow-ups (each skippable), the shape of a
 * path shown before anything starts, and one action. Nothing here is a
 * "setup wizard": the answers become the first thing the learner says to the
 * Professor, in their own words, and that sentence is what the teaching
 * session records as its goal.
 *
 * Backend: a subject and a notebook are created with the endpoints that
 * already exist, so the learning shows up on Home and the session has a
 * notebook to belong to. A dated goal is deliberately not created — the
 * goals screen refuses to plan without a deadline and pace, and this flow
 * does not ask for either. The persisted journey object the audit calls for
 * will replace the subject+notebook pair when it lands; the flow stays.
 */

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Mino, type MinoState } from '@/components/mino/Mino';
import { Shell } from '@/components/Shell';
import { Button } from '@/components/ui/Button';
import { ApiError, api } from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useT } from '@/lib/i18n';
import { rememberPrefill, takePrefill } from '@/lib/prefill';

type Level = 'zero' | 'some' | 'deepen';
type Purpose = 'curiosity' | 'exam' | 'life';
type Step = 'subject' | 'level' | 'purpose' | 'path';

const LEVELS: Level[] = ['zero', 'some', 'deepen'];
const PURPOSES: Purpose[] = ['curiosity', 'exam', 'life'];
const STEPS: Step[] = ['subject', 'level', 'purpose', 'path'];

// Titles have a server-side limit; a goal typed as a paragraph still needs
// a name that fits on a list.
function titleFrom(goal: string): string {
  const oneLine = goal.replace(/\s+/g, ' ').trim();
  return oneLine.length > 120 ? `${oneLine.slice(0, 119)}…` : oneLine;
}

export default function NewLearningPage() {
  const router = useRouter();
  const t = useT();
  const copy = t.learnNew;

  const [step, setStep] = useState<Step>('subject');
  const [subject, setSubject] = useState('');
  const [level, setLevel] = useState<Level | null>(null);
  const [purpose, setPurpose] = useState<Purpose | null>(null);
  const [typing, setTyping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A subject typed on the landing page lands here first, so nobody types
  // it twice; the hero only ever leaves the text, never an autosend.
  useEffect(() => {
    const carried = takePrefill();
    if (carried) setSubject(carried.text);
  }, []);

  const trimmed = subject.trim();
  const index = STEPS.indexOf(step);

  function next() {
    if (step === 'subject' && !trimmed) return;
    setError(null);
    setStep(STEPS[index + 1] ?? 'path');
  }

  function back() {
    setError(null);
    setStep(STEPS[index - 1] ?? 'subject');
  }

  async function start() {
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      const workspaces = await api.workspaces();
      const workspace =
        workspaces.items[0] ?? (await api.createWorkspace(copy.defaultWorkspace));
      const title = titleFrom(trimmed);
      const created = await api.createSubject(workspace.id, title);
      const notebook = await api.createNotebook(created.id, title);
      rememberPrefill(copy.firstTurn(trimmed, level, purpose), true);
      router.push(`/notebooks/${notebook.id}/professor`);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        router.push('/login');
        return;
      }
      setError(humanError(err, t, 'save'));
      setBusy(false);
    }
  }

  const mino: MinoState = busy
    ? 'thinking'
    : step === 'path'
      ? 'teaching'
      : typing
        ? 'listening'
        : 'curious';

  const steps = t.landing.demoSteps(trimmed);

  return (
    <Shell>
      <div className="mx-auto max-w-reading">
        <p className="text-xs uppercase tracking-wide text-ink-500">
          {copy.stepOf(index + 1, STEPS.length)}
        </p>

        <div className="mt-6 flex items-start gap-6">
          <Mino state={mino} size="lg" className="hidden sm:block" />
          <div className="min-w-0 flex-1">
            {step === 'subject' && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  next();
                }}
              >
                <label htmlFor="learn-subject" className="font-display text-2xl text-ink-900">
                  {copy.subjectQuestion}
                </label>
                <p className="mt-2 text-base text-ink-600">{copy.subjectLede}</p>
                <input
                  id="learn-subject"
                  value={subject}
                  autoFocus
                  autoComplete="off"
                  onChange={(event) => {
                    setSubject(event.target.value);
                    setTyping(Boolean(event.target.value));
                  }}
                  onFocus={() => setTyping(true)}
                  onBlur={() => setTyping(false)}
                  placeholder={copy.subjectPlaceholder}
                  className="mt-6 w-full rounded-md border border-line bg-raised px-4 py-3 text-base text-ink-900 outline-none transition-colors duration-fast focus:border-signal placeholder:text-ink-400"
                />
                <div className="mt-6 flex items-center gap-3">
                  <Button type="submit" variant="primary" disabled={!trimmed}>
                    {copy.next}
                  </Button>
                </div>
              </form>
            )}

            {step === 'level' && (
              <Choice
                question={copy.levelQuestion}
                options={LEVELS.map((id) => ({ id, label: copy.levels[id] }))}
                value={level}
                onPick={(id) => {
                  setLevel(id);
                  next();
                }}
                onSkip={next}
                onBack={back}
                skip={copy.skip}
                backLabel={copy.back}
              />
            )}

            {step === 'purpose' && (
              <Choice
                question={copy.purposeQuestion}
                options={PURPOSES.map((id) => ({ id, label: copy.purposes[id] }))}
                value={purpose}
                onPick={(id) => {
                  setPurpose(id);
                  next();
                }}
                onSkip={next}
                onBack={back}
                skip={copy.skip}
                backLabel={copy.back}
              />
            )}

            {step === 'path' && (
              <div>
                <h1 className="font-display text-2xl text-ink-900">{copy.pathTitle(trimmed)}</h1>
                <p className="mt-2 text-base text-ink-600">{copy.pathLede}</p>
                <ol className="mt-6 space-y-3">
                  {steps.map((line, position) => (
                    <li key={line} className="flex gap-3 text-base text-ink-700">
                      <span className="font-mono text-xs text-signal">{position + 1}</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ol>
                <p className="mt-4 text-xs text-ink-400">{t.landing.demoNote}</p>

                {error && (
                  <p role="alert" className="mt-4 text-sm text-critical">
                    {error}
                  </p>
                )}

                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <Button variant="primary" size="lg" onClick={() => void start()} busy={busy ? copy.starting : undefined}>
                    {copy.start(trimmed)}
                  </Button>
                  <Button variant="ghost" onClick={back} disabled={busy}>
                    {copy.back}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Choice<T extends string>({
  question,
  options,
  value,
  onPick,
  onSkip,
  onBack,
  skip,
  backLabel,
}: {
  question: string;
  options: { id: T; label: string }[];
  value: T | null;
  onPick: (id: T) => void;
  onSkip: () => void;
  onBack: () => void;
  skip: string;
  backLabel: string;
}) {
  return (
    <div>
      <h1 className="font-display text-2xl text-ink-900">{question}</h1>
      <div role="group" aria-label={question} className="mt-6 flex flex-col gap-2">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onPick(option.id)}
            aria-pressed={value === option.id}
            className={`rounded-md border px-4 py-3 text-left text-base transition-colors duration-fast ${
              value === option.id
                ? 'border-signal bg-raised text-ink-900'
                : 'border-line bg-raised text-ink-800 hover:border-ink-400'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="mt-6 flex items-center gap-3">
        <Button variant="secondary" onClick={onSkip}>
          {skip}
        </Button>
        <Button variant="ghost" onClick={onBack}>
          {backLabel}
        </Button>
      </div>
    </div>
  );
}
