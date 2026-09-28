'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { AuthFrame } from '@/components/auth/AuthFrame';
import { Button, ButtonLink } from '@/components/ui/Button';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function VerifyEmailPage() {
  // useSearchParams() opts the tree out of static prerendering unless it is
  // behind Suspense -- same arrangement as /reset-password.
  return (
    <Suspense fallback={null}>
      <VerifyEmail />
    </Suspense>
  );
}

type Outcome = 'verifying' | 'confirmed' | 'expired' | 'invalid';
type Resend = 'idle' | 'sending' | 'sent' | 'tooSoon' | 'signIn' | 'failed';

function VerifyEmail() {
  const t = useT();
  const copy = t.emailVerification;
  const token = useSearchParams().get('token');

  const [outcome, setOutcome] = useState<Outcome>(token ? 'verifying' : 'invalid');
  const [resend, setResend] = useState<Resend>('idle');
  // The token is single use, so the request must be too: a second effect
  // run (React's development double-mount) would consume it and report the
  // link it just confirmed as invalid.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    (async () => {
      try {
        await api.verifyEmail(token);
        setOutcome('confirmed');
      } catch (err) {
        setOutcome(
          err instanceof ApiError && err.problem.type.endsWith('/link-expired')
            ? 'expired'
            : 'invalid',
        );
      }
    })();
  }, [token]);

  async function requestNew() {
    setResend('sending');
    try {
      await api.resendVerification();
      setResend('sent');
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) setResend('signIn');
      else if (err instanceof ApiError && err.problem.status === 429) setResend('tooSoon');
      else setResend('failed');
    }
  }

  const title =
    outcome === 'confirmed'
      ? copy.successTitle
      : outcome === 'expired'
        ? copy.expiredTitle
        : outcome === 'invalid'
          ? copy.invalidTitle
          : copy.verifying;

  return (
    <AuthFrame aside={t.login.aside}>
      <div>
        <h1 className="font-display text-2xl text-ink-900">{title}</h1>

        {outcome === 'confirmed' && (
          <>
            <p className="mt-4 text-sm text-ink-600">{copy.successBody}</p>
            <ButtonLink href="/today" variant="primary" className="mt-6">
              {copy.continue}
            </ButtonLink>
          </>
        )}

        {(outcome === 'expired' || outcome === 'invalid') && (
          <>
            <p className="mt-4 text-sm text-ink-600">
              {outcome === 'expired' ? copy.expiredBody : copy.invalidBody}
            </p>
            {resend === 'sent' || resend === 'tooSoon' || resend === 'failed' ? (
              <p role="status" className="mt-6 text-sm text-ink-600">
                {resend === 'sent' ? copy.sent : resend === 'tooSoon' ? copy.tooSoon : copy.failed}
              </p>
            ) : resend === 'signIn' ? (
              <>
                <p role="status" className="mt-6 text-sm text-ink-600">
                  {copy.signInFirst}
                </p>
                <ButtonLink href="/login" variant="primary" className="mt-4">
                  {copy.signIn}
                </ButtonLink>
              </>
            ) : (
              <Button
                type="button"
                variant="primary"
                className="mt-6"
                onClick={requestNew}
                busy={resend === 'sending' ? copy.sending : undefined}
              >
                {copy.requestNew}
              </Button>
            )}
          </>
        )}

        <Link
          href="/login"
          className="mt-8 inline-block text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
        >
          {t.passwordReset.backToLogin}
        </Link>
      </div>
    </AuthFrame>
  );
}
