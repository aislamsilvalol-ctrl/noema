'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shell } from '@/components/Shell';
import { ApiError, api, type Credential, type Provider } from '@/lib/api';

export default function SettingsPage() {
  const router = useRouter();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [provider, setProvider] = useState('anthropic');
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [providerList, credentialList] = await Promise.all([
        api.providers(),
        api.credentials(),
      ]);
      setProviders(providerList);
      setCredentials(credentialList);
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) router.push('/login');
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function addKey(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.addCredential(provider, 'default', apiKey);
      setCredentials((current) => [...current, created]);
      // The key is gone from memory the moment it is sent; only last4 comes back.
      setApiKey('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that key.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <h1 className="font-display text-2xl text-ink-900">Settings</h1>

      <section className="mt-10 max-w-reading">
        <h2 className="text-lg text-ink-900">AI providers</h2>
        <p className="mt-2 text-sm text-ink-600">
          Keys are encrypted before they are stored and are never returned by the API — only
          the last four characters. Delete one and it is gone.
        </p>

        <ul className="mt-6 divide-y divide-line border-y border-line">
          {providers.map((p) => (
            <li key={p.name} className="flex items-center justify-between py-3">
              <span className="text-sm text-ink-800">
                {p.name}
                {p.is_default && <span className="ml-2 text-xs text-ink-400">default</span>}
              </span>
              <span className={`text-xs ${p.configured ? 'text-positive' : 'text-ink-400'}`}>
                {p.configured ? 'configured' : 'no key'}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-12 max-w-reading">
        <h2 className="text-lg text-ink-900">Add a key</h2>

        <form onSubmit={addKey} className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-ink-500">Provider</span>
            <select
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
              className="mt-1.5 block rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900"
            >
              {providers
                .filter((p) => p.name !== 'ollama' && p.name !== 'mock')
                .map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
            </select>
          </label>

          <label className="block flex-1">
            <span className="text-xs uppercase tracking-wide text-ink-500">API key</span>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              autoComplete="off"
              className="mt-1.5 w-full rounded-md border border-line bg-raised px-3 py-2 font-mono text-sm text-ink-900"
            />
          </label>

          <button
            type="submit"
            disabled={busy || !apiKey}
            className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-ink-50 disabled:opacity-50"
          >
            {busy ? 'Verifying…' : 'Save'}
          </button>
        </form>

        {error && (
          <p role="alert" className="mt-3 text-sm text-critical">
            {error}
          </p>
        )}

        {credentials.length > 0 && (
          <ul className="mt-8 divide-y divide-line border-y border-line">
            {credentials.map((credential) => (
              <li key={credential.id} className="flex items-center justify-between py-3">
                <span className="text-sm text-ink-800">
                  {credential.provider}
                  <span className="ml-2 font-mono text-xs text-ink-400">
                    ····{credential.last4}
                  </span>
                  {credential.verification_error && (
                    <span className="ml-2 text-xs text-critical">
                      {credential.verification_error}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  onClick={async () => {
                    await api.deleteCredential(credential.id);
                    setCredentials((current) =>
                      current.filter((c) => c.id !== credential.id),
                    );
                  }}
                  className="text-xs text-ink-500 transition-colors duration-state hover:text-critical"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Shell>
  );
}
