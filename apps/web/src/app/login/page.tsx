'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiError, api } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
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
      if (mode === 'login') {
        await api.login(email, password);
      } else {
        await api.register(email, password, displayName || email.split('@')[0] || 'Learner');
      }
      router.push('/today');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <h1 className="font-display text-2xl text-ink-900">
          {mode === 'login' ? 'Welcome back.' : 'Start learning.'}
        </h1>
        <p className="mt-2 text-sm text-ink-500">
          {mode === 'login'
            ? 'Sign in to pick up where you left off.'
            : 'Your material stays yours. Export or delete it at any time.'}
        </p>

        <form onSubmit={submit} className="mt-8 space-y-4">
          {mode === 'register' && (
            <Field
              label="Name"
              value={displayName}
              onChange={setDisplayName}
              autoComplete="name"
            />
          )}
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
            required
          />
          <Field
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            hint={mode === 'register' ? 'At least 12 characters. Length beats symbols.' : undefined}
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
            {busy ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setError(null);
          }}
          hidden={signupsAllowed === false && mode === 'login'}
          className="mt-6 text-sm text-ink-500 transition-colors duration-state hover:text-ink-900"
        >
          {mode === 'login' ? 'No account yet? Create one' : 'Already have an account? Sign in'}
        </button>

        {signupsAllowed === false && mode === 'login' && (
          // Said plainly. "Create one" simply vanishing looks like a bug, and
          // someone who cannot sign in needs to know whether to keep trying the
          // password or to go and ask for an account.
          <p className="mt-6 text-sm text-ink-500">
            This instance is not open for new accounts. Ask whoever runs it for
            one, or run your own — NOEMA is open source.
          </p>
        )}
      </div>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  hint,
  ...rest
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  hint?: string;
  required?: boolean;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</span>
      <input
        {...rest}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-md border border-line bg-raised px-3 py-2 text-base text-ink-900 transition-colors duration-state focus:border-accent"
      />
      {hint && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
    </label>
  );
}
