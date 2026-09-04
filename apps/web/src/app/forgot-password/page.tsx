'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Field } from '@/components/Field';
import { AuthFrame } from '@/components/auth/AuthFrame';
import { Button } from '@/components/ui/Button';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function ForgotPasswordPage() {
  const t = useT();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.forgotPassword(email);
      // Always the same success state, whether or not the email has an
      // account -- the backend already gives an identical response either
      // way (POST /auth/forgot-password always 204s), and showing a
      // different UI state here would undo that at the one layer left that
      // could.
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.somethingWrong);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame aside={t.login.aside}>
      <div>
        {sent ? (
          <>
            <h1 className="font-display text-2xl text-ink-900">{t.passwordReset.forgotTitle}</h1>
            <p className="mt-4 text-sm text-ink-600">{t.passwordReset.sent}</p>
            <Link
              href="/login"
              className="mt-6 inline-block text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
            >
              {t.passwordReset.backToLogin}
            </Link>
          </>
        ) : (
          <>
            <h1 className="font-display text-2xl text-ink-900">{t.passwordReset.forgotTitle}</h1>
            <p className="mt-2 text-sm text-ink-500">{t.passwordReset.forgotLede}</p>

            <form onSubmit={submit} className="mt-8 space-y-4">
              <Field
                label={t.passwordReset.email}
                type="email"
                value={email}
                onChange={setEmail}
                autoComplete="email"
                required
              />

              {error && (
                <p role="alert" className="text-sm text-critical">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="w-full"
                busy={busy ? t.passwordReset.sending : undefined}
              >
                {t.passwordReset.sendLink}
              </Button>
            </form>

            <Link
              href="/login"
              className="mt-6 inline-block text-sm text-ink-500 transition-colors duration-fast hover:text-ink-900"
            >
              {t.passwordReset.backToLogin}
            </Link>
          </>
        )}
      </div>
    </AuthFrame>
  );
}
