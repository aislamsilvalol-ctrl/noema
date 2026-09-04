'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Field } from '@/components/Field';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { track } from '@/lib/analytics';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function LoginPage() {
  const router = useRouter();
  const t = useT();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Whether this deployment accepts new accounts at all. A single-user or
  // invite-only instance does not, and offering "Create one" there is a button
  // that is visible, clickable, and guaranteed to fail with a 403 — which is
  // exactly what `/meta` exists to prevent, and this page was not asking.
  //
  // Starts null rather than true: assuming signups work and hiding the link a
  // moment later is the same broken promise, just briefer.
  const [signupsAllowed, setSignupsAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .meta()
      .then((meta) => setSignupsAllowed(meta.allow_signups))
      // If we cannot tell, say nothing rather than guess. The sign-in form is
      // unaffected either way, and it is the one that matters here.
      .catch(() => setSignupsAllowed(null));
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // A new account goes straight to "what do you want to learn"; a
      // returning one to Home, which answers "where was I".
      if (mode === 'login') {
        await api.login(email, password);
        router.push('/today');
      } else {
        await api.register(email, password, displayName || email.split('@')[0] || 'Learner');
        track('signup_completed');
        router.push('/learn/new');
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.somethingWrong);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <h1 className="font-display text-2xl text-ink-900">
          {mode === 'login' ? t.login.welcomeBack : t.login.startLearning}
        </h1>
        <p className="mt-2 text-sm text-ink-500">
          {mode === 'login' ? t.login.signInLede : t.login.registerLede}
        </p>

        <form onSubmit={submit} className="mt-8 space-y-4">
          {mode === 'register' && (
            <Field
              label={t.login.name}
              value={displayName}
              onChange={setDisplayName}
              autoComplete="name"
            />
          )}
          <Field
            label={t.login.email}
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
            required
          />
          <Field
            label={t.login.password}
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            hint={mode === 'register' ? t.login.passwordHint : undefined}
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
            {busy ? t.login.working : mode === 'login' ? t.login.signIn : t.login.createAccount}
          </button>

          {mode === 'login' && (
            <Link
              href="/forgot-password"
              className="block text-center text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
            >
              {t.login.forgotPassword}
            </Link>
          )}
        </form>

        <button
          type="button"
          onClick={() => {
            const next = mode === 'login' ? 'register' : 'login';
            if (next === 'register') track('signup_started');
            setMode(next);
            setError(null);
          }}
          hidden={signupsAllowed === false && mode === 'login'}
          className="mt-6 text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
        >
          {mode === 'login' ? t.login.noAccount : t.login.haveAccount}
        </button>

        {signupsAllowed === false && mode === 'login' && (
          // Said plainly. "Create one" simply vanishing looks like a bug, and
          // someone who cannot sign in needs to know whether to keep trying the
          // password or to go and ask for an account.
          <p className="mt-6 text-sm text-ink-500">{t.login.signupsClosed}</p>
        )}

        <div className="mt-10">
          <LanguageSwitcher />
        </div>
      </div>
    </main>
  );
}
