'use client';

/**
 * What Mino remembers about the learner, one course at a time, and a way to
 * forget any of it without deleting the account.
 *
 * Each line is something the tutor inferred — how the learner learns, how
 * they like to be talked to, what an earlier stretch of a lesson established,
 * a misconception still open. Forgetting is a DELETE the server answers with
 * 204; the list is re-read afterwards rather than trimmed by hand, so what is
 * shown is always what the server still holds. "Forget everything" needs a
 * second click, inline, not a browser dialog.
 */

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Input';
import { api, type Journey, type JourneyMemory } from '@/lib/api';
import { humanError } from '@/lib/errors';
import { useI18n, useT } from '@/lib/i18n';

export function MemorySection() {
  const t = useT();
  const { locale } = useI18n();
  const copy = t.settings.memory;
  const [journeys, setJourneys] = useState<Journey[] | null>(null);
  const [journeyId, setJourneyId] = useState<string | null>(null);
  const [memory, setMemory] = useState<JourneyMemory | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .journeys()
      .then((list) => {
        if (cancelled) return;
        setJourneys(list);
        setJourneyId(list[0]?.id ?? null);
      })
      .catch((err) => {
        if (!cancelled) setMessage({ ok: false, text: humanError(err, t, 'load') });
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const load = useCallback(async () => {
    if (!journeyId) return;
    try {
      setMemory(await api.journeyMemory(journeyId));
    } catch (err) {
      setMessage({ ok: false, text: humanError(err, t, 'load') });
    }
  }, [journeyId, t]);

  useEffect(() => {
    setMemory(null);
    setConfirming(false);
    void load();
  }, [load]);

  async function forget(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setMessage({ ok: true, text: copy.forgotten });
      await load();
    } catch (err) {
      setMessage({ ok: false, text: humanError(err, t, 'save') });
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  if (journeys && journeys.length === 0) {
    return (
      <div className="mt-10" data-memory-section>
        <h3 className="text-sm font-medium text-ink-900">{copy.title}</h3>
        <p className="mt-2 text-sm text-ink-600">{copy.noCourses}</p>
      </div>
    );
  }

  const date = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' });
  const nothing =
    memory &&
    memory.patterns.length === 0 &&
    memory.communication.length === 0 &&
    memory.summaries.length === 0 &&
    memory.misconceptions.length === 0;

  return (
    <div className="mt-10" data-memory-section>
      <h3 className="text-sm font-medium text-ink-900">{copy.title}</h3>
      <p className="mt-2 text-sm text-ink-600">{copy.lede}</p>

      {journeys && journeyId && (
        <label className="mt-4 block">
          <span className="text-sm text-ink-600">{copy.course}</span>
          <Select
            value={journeyId}
            onChange={(event) => setJourneyId(event.target.value)}
            className="mt-1.5 block w-full max-w-sm"
          >
            {journeys.map((journey) => (
              <option key={journey.id} value={journey.id}>
                {journey.subject || journey.objective}
              </option>
            ))}
          </Select>
        </label>
      )}

      {nothing && <p className="mt-4 text-sm text-ink-600">{copy.empty}</p>}

      {memory && !nothing && journeyId && (
        <>
          {memory.patterns.length > 0 && (
            <Group title={copy.patterns}>
              {memory.patterns.map((pattern, index) => (
                <Line
                  key={`${index}-${pattern}`}
                  text={pattern}
                  label={copy.forget}
                  disabled={busy}
                  onForget={() => forget(() => api.forgetPattern(journeyId, index))}
                />
              ))}
            </Group>
          )}

          {memory.communication.length > 0 && (
            // One adaptation cannot be forgotten alone: they are a single
            // reading of the learner, and "forget everything" drops it whole.
            <Group title={copy.communication}>
              {memory.communication.map((pref) => (
                <li key={pref.label} className="py-2 text-sm text-ink-800">
                  {copy.preferences[pref.label] ?? pref.label}
                  <span className="text-ink-500"> · </span>
                  {copy.preferences[pref.value] ?? pref.value}
                </li>
              ))}
            </Group>
          )}

          {memory.summaries.length > 0 && (
            <Group title={copy.summaries}>
              {memory.summaries.map((summary) => (
                <Line
                  key={summary.id}
                  text={summary.text || summary.next_step}
                  detail={[
                    date.format(new Date(summary.created_at)),
                    summary.text && summary.next_step ? `${copy.next}: ${summary.next_step}` : '',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  label={copy.forget}
                  disabled={busy}
                  onForget={() => forget(() => api.forgetSummary(journeyId, summary.id))}
                />
              ))}
            </Group>
          )}

          {memory.misconceptions.length > 0 && (
            <Group title={copy.misconceptions}>
              {memory.misconceptions.map((item) => (
                <Line
                  key={`${item.concept}-${item.text}`}
                  text={item.text}
                  detail={item.concept}
                  label={copy.forget}
                  disabled={busy}
                  onForget={() =>
                    forget(() => api.forgetMisconception(journeyId, item.concept, item.text))
                  }
                />
              ))}
            </Group>
          )}

          <div className="mt-6">
            {confirming ? (
              <div role="group" aria-label={copy.forgetAll}>
                <p className="text-sm text-ink-600">{copy.forgetAllConfirm}</p>
                <div className="mt-3 flex gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={busy}
                    onClick={() => forget(() => api.forgetJourneyMemory(journeyId))}
                  >
                    {copy.forgetAllYes}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
                    {t.common.cancel}
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => setConfirming(true)}>
                {copy.forgetAll}
              </Button>
            )}
          </div>
        </>
      )}

      {message && (
        <p
          role={message.ok ? 'status' : 'alert'}
          className={`mt-3 text-sm ${message.ok ? 'text-ink-700' : 'text-critical'}`}
        >
          {message.text}
        </p>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <h4 className="font-mono text-xs text-ink-500">{title}</h4>
      <ul className="mt-2 divide-y divide-line border-y border-line">{children}</ul>
    </div>
  );
}

function Line({
  text,
  detail,
  label,
  disabled,
  onForget,
}: {
  text: string;
  detail?: string;
  label: string;
  disabled: boolean;
  onForget: () => void;
}) {
  return (
    <li className="flex items-center justify-between gap-4 py-2">
      <span className="min-w-0">
        <span className="block text-sm text-ink-800">{text}</span>
        {detail && <span className="block text-xs text-ink-500">{detail}</span>}
      </span>
      <Button
        variant="ghost"
        size="sm"
        disabled={disabled}
        onClick={onForget}
        aria-label={`${label}: ${text}`}
      >
        {label}
      </Button>
    </li>
  );
}
