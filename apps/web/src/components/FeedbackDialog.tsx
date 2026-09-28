'use client';

/**
 * "Report a problem": the one channel that is not a thumbs-up. Four kinds,
 * a textarea, send. The page the reporter is on goes along with it; the
 * browser string the server reads for itself.
 *
 * A sheet on a phone, a small dialog on a desk — BottomSheet does both. The
 * caller may hand in a kind and an opening line (the error page does, with
 * its reference); closing puts the form back to that.
 */

import { useState, type FormEvent } from 'react';
import { ApiError, api, type FeedbackKind } from '@/lib/api';
import { BottomSheet } from '@/components/ui/BottomSheet';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Input';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { useT } from '@/lib/i18n';

const KINDS: readonly FeedbackKind[] = ['bug', 'confusion', 'ai_quality', 'idea'];

export function FeedbackDialog({
  open,
  onClose,
  kind: initialKind = 'bug',
  message: initialMessage = '',
}: {
  open: boolean;
  onClose: () => void;
  kind?: FeedbackKind;
  message?: string;
}) {
  const t = useT();
  const [kind, setKind] = useState<FeedbackKind>(initialKind);
  const [message, setMessage] = useState(initialMessage);
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle');
  const [error, setError] = useState<string | null>(null);

  function close() {
    onClose();
    setKind(initialKind);
    setMessage(initialMessage);
    setState('idle');
    setError(null);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text || state === 'sending') return;
    setState('sending');
    setError(null);
    try {
      await api.sendFeedback({
        kind,
        message: text,
        page: window.location.pathname.slice(0, 300),
      });
      setState('sent');
    } catch (err) {
      setState('idle');
      setError(
        err instanceof ApiError && err.problem.status === 429
          ? t.feedback.tooMany
          : t.feedback.failed,
      );
    }
  }

  return (
    <BottomSheet
      open={open}
      onClose={close}
      title={t.feedback.title}
      closeLabel={t.common.close}
      layout="dialog"
    >
      {state === 'sent' ? (
        <div>
          <p className="text-md text-ink-900">{t.feedback.thanksTitle}</p>
          <p className="mt-1 text-sm text-ink-600">{t.feedback.thanksBody}</p>
          <Button size="sm" className="mt-5" onClick={close}>
            {t.common.close}
          </Button>
        </div>
      ) : (
        <form onSubmit={send} className="space-y-4">
          <div>
            <p className="text-sm text-ink-600">{t.feedback.kindLabel}</p>
            <SegmentedControl
              label={t.feedback.kindLabel}
              options={KINDS.map((value) => ({ value, label: t.feedback.kinds[value] }))}
              value={kind}
              onChange={setKind}
              className="mt-2 flex-wrap"
            />
          </div>
          <label className="block">
            <span className="text-sm text-ink-600">{t.feedback.messageLabel}</span>
            <Textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={t.feedback.placeholder}
              rows={5}
              maxLength={4000}
              required
              className="mt-2 w-full"
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-critical">
              {error}
            </p>
          )}
          <div className="flex items-center justify-end gap-3">
            <Button variant="ghost" onClick={close}>
              {t.common.cancel}
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!message.trim()}
              busy={state === 'sending' ? t.feedback.sending : undefined}
            >
              {t.common.send}
            </Button>
          </div>
        </form>
      )}
    </BottomSheet>
  );
}
