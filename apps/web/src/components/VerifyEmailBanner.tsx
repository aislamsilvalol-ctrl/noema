'use client';

import { useEffect, useState } from 'react';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';

/**
 * One line at the top of the shell while the account has not opened the
 * link sent to its address. Nothing is gated on it, so it stays quiet: a
 * sentence, "Resend", and a way to close it for the session. Closed or
 * confirmed, it asks nothing more of the API until the next session.
 */

const DISMISSED = 'noema.verify-email.dismissed';
const CONFIRMED = 'noema.verify-email.confirmed';

type Resend = 'idle' | 'sending' | 'sent' | 'tooSoon' | 'failed';

function remembered(key: string): boolean {
  try {
    return window.sessionStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function remember(key: string) {
  try {
    window.sessionStorage.setItem(key, '1');
  } catch {
    // storage blocked: the choice still applies to this page
  }
}

export function VerifyEmailBanner() {
  const t = useT();
  const [show, setShow] = useState(false);
  const [resend, setResend] = useState<Resend>('idle');

  useEffect(() => {
    if (remembered(DISMISSED) || remembered(CONFIRMED)) return;
    let cancelled = false;
    (async () => {
      try {
        // Nothing to ask while links cannot be delivered (test mail sender).
        const meta = await api.meta();
        if (cancelled || !meta.email_verification) return;
        const user = await api.me();
        if (cancelled) return;
        if (user.email_verified) {
          remember(CONFIRMED);
          return;
        }
        setShow(true);
      } catch {
        // not signed in, or offline: nothing to say
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!show) return null;

  async function send() {
    setResend('sending');
    try {
      await api.resendVerification();
      setResend('sent');
    } catch (err) {
      setResend(err instanceof ApiError && err.problem.status === 429 ? 'tooSoon' : 'failed');
    }
  }

  function dismiss() {
    remember(DISMISSED);
    setShow(false);
  }

  const copy = t.emailVerification;
  const note =
    resend === 'sent'
      ? copy.sent
      : resend === 'tooSoon'
        ? copy.tooSoon
        : resend === 'failed'
          ? copy.failed
          : null;

  return (
    <div
      role="status"
      data-verify-email-banner
      className="mb-8 flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-line pb-3 text-sm text-ink-600"
    >
      <span className="text-ink-900">{copy.bannerTitle}</span>
      {note ? (
        <span>{note}</span>
      ) : (
        <button
          type="button"
          onClick={send}
          disabled={resend === 'sending'}
          className="underline-offset-2 transition-colors duration-state hover:text-ink-900 hover:underline disabled:opacity-60"
        >
          {resend === 'sending' ? copy.sending : copy.resend}
        </button>
      )}
      <button
        type="button"
        onClick={dismiss}
        aria-label={copy.dismiss}
        className="ml-auto px-1 text-ink-400 transition-colors duration-state hover:text-ink-900"
      >
        ×
      </button>
    </div>
  );
}
