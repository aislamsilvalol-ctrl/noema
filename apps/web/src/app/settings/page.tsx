'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shell } from '@/components/Shell';
import {
  ApiError,
  api,
  downloadExport,
  type Credential,
  type Meta,
  type Provider,
  type User,
} from '@/lib/api';

export default function SettingsPage() {
  const router = useRouter();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [account, setAccount] = useState<User | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [provider, setProvider] = useState('anthropic');
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState('');
  const [dangerError, setDangerError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [providerList, credentialList, user, deployment] = await Promise.all([
        api.providers(),
        api.credentials(),
        api.me(),
        api.meta(),
      ]);
      setProviders(providerList);
      setCredentials(credentialList);
      setAccount(user);
      setMeta(deployment);
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

  async function exportEverything() {
    setExporting(true);
    setDangerError(null);
    try {
      await downloadExport();
    } catch (err) {
      setDangerError(err instanceof Error ? err.message : 'The export failed.');
    } finally {
      setExporting(false);
    }
  }

  async function deleteAccount() {
    setDangerError(null);
    try {
      await api.deleteAccount();
      // The session is already gone server-side; a hard navigation clears everything
      // this tab is still holding in memory.
      window.location.href = '/login';
    } catch (err) {
      setDangerError(err instanceof Error ? err.message : 'The account was not deleted.');
    }
  }

  return (
    <Shell>
      <h1 className="font-display text-2xl text-ink-900">Settings</h1>

      {meta?.local && (
        <p className="mt-6 max-w-reading border-l-2 border-line pl-4 text-sm text-ink-600">
          This deployment runs in <span className="text-ink-900">local mode</span>. Models run
          on this machine, and the containers holding your material have no route to the
          internet — so hosted providers are not offered here rather than failing when you
          click them.
        </p>
      )}

      <section className="mt-10 max-w-reading">
        <h2 className="text-lg text-ink-900">AI providers</h2>
        <p className="mt-2 text-sm text-ink-600">
          {meta?.local
            ? `Answering and embedding run locally through ${meta.default_provider}. Nothing is sent anywhere.`
            : 'Keys are encrypted before they are stored and are never returned by the API — only the last four characters. Delete one and it is gone.'}
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

      {/* Hidden rather than disabled in local mode: there is no key to add, because
          there is nothing to authenticate against. */}
      <section className={`mt-12 max-w-reading ${meta?.local ? 'hidden' : ''}`}>
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

      <section className="mt-16 max-w-reading">
        <h2 className="text-lg text-ink-900">Your data</h2>
        <p className="mt-2 text-sm text-ink-600">
          The export is a zip: your notes as Markdown, your uploads exactly as you gave them
          to us, and everything derived — concepts, cards, mastery — as JSON. None of it
          needs NOEMA to open.
        </p>

        <button
          type="button"
          onClick={exportEverything}
          disabled={exporting}
          className="mt-4 rounded-md border border-line px-4 py-2 text-sm text-ink-800 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
        >
          {exporting ? 'Preparing…' : 'Export everything'}
        </button>

        <div className="mt-10 rounded-lg border border-line p-5">
          <h3 className="text-sm font-medium text-ink-900">Delete this account</h3>
          <p className="mt-2 text-sm text-ink-600">
            You are signed out immediately and the account stops working. Everything —
            notes, uploads, cards, review history — is permanently deleted after 30 days.
            Export first; after that there is nothing to recover.
          </p>

          <label className="mt-4 block">
            <span className="text-xs uppercase tracking-wide text-ink-500">
              Type your email to confirm
            </span>
            <input
              type="text"
              value={confirmDelete}
              onChange={(event) => setConfirmDelete(event.target.value)}
              autoComplete="off"
              placeholder={account?.email ?? 'you@example.com'}
              className="mt-1.5 w-full max-w-sm rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900"
            />
          </label>

          <button
            type="button"
            onClick={deleteAccount}
            disabled={!account || confirmDelete.trim().toLowerCase() !== account.email}
            className="mt-4 rounded-md border border-critical px-4 py-2 text-sm text-critical transition-colors duration-state hover:bg-critical hover:text-ink-50 disabled:opacity-40"
          >
            Delete my account
          </button>
        </div>

        {dangerError && (
          <p role="alert" className="mt-3 text-sm text-critical">
            {dangerError}
          </p>
        )}
      </section>
    </Shell>
  );
}
