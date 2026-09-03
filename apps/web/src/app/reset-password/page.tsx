'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Field } from '@/components/Field';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function ResetPasswordPage() {
  // useSearchParams() opts the tree that reads it out of static prerendering
  // unless it's isolated behind Suspense -- this page has no other dynamic
  // segment (unlike notebooks/[id]/exam) to force that automatically.
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const t = useT();
  const searchParams = useSearchParams();
  const token = searchParams.get('token');

  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  // `invalid` covers both an expired/already-used token from the API and a
  // link opened with no token in the URL at all -- the recovery is the same
  // either way: ask for a fresh one.
  const [invalid, setInvalid] = useState(!token);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!token) {
      setInvalid(true);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.resetPassword(token, newPassword);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) {
        setInvalid(true);
      } else {
        setError(err instanceof ApiError ? err.message : t.common.somethingWrong);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        {done ? (
          <>
            <h1 className="font-display text-2xl text-ink-900">{t.passwordReset.success}</h1>
            <Link
              href="/login"
              className="mt-6 inline-block rounded-md bg-ink-900 px-4 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
            >
              {t.passwordReset.signInNow}
            </Link>
          </>
        ) : invalid ? (
          <>
            <h1 className="font-display text-2xl text-ink-900">{t.passwordReset.invalidLink}</h1>
            <Link
              href="/forgot-password"
              className="mt-6 inline-block rounded-md bg-ink-900 px-4 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
            >
              {t.passwordReset.requestNewLink}
            </Link>
          </>
        ) : (
          <>
            <h1 className="font-display text-2xl text-ink-900">{t.passwordReset.resetTitle}</h1>

            <form onSubmit={submit} className="mt-8 space-y-4">
              <Field
                label={t.passwordReset.newPassword}
                type="password"
                value={newPassword}
                onChange={setNewPassword}
                autoComplete="new-password"
                required
                hint={t.passwordReset.passwordHint}
              />

              {error && (
                <p role="alert" className="text-sm text-critical">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-md bg-ink-900 px-4 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90 disabled:opacity-50"
              >
                {busy ? t.passwordReset.resetting : t.passwordReset.resetSubmit}
              </button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}
