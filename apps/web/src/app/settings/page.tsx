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
  type Plan,
  type PlanPrice,
  type Provider,
  type User,
} from '@/lib/api';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

export default function SettingsPage() {
  const router = useRouter();
  const t = useT();
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
  const [plans, setPlans] = useState<PlanPrice[]>([]);
  const [billingBusy, setBillingBusy] = useState<Plan | 'portal' | null>(null);
  const [billingError, setBillingError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [providerList, credentialList, user, deployment, planList] = await Promise.all([
        api.providers(),
        api.credentials(),
        api.me(),
        api.meta(),
        api.plans(),
      ]);
      setProviders(providerList);
      setCredentials(credentialList);
      setAccount(user);
      setMeta(deployment);
      setPlans(planList);
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
      setError(err instanceof Error ? err.message : t.settings.couldNotSaveKey);
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
      setDangerError(err instanceof Error ? err.message : t.settings.exportFailed);
    } finally {
      setExporting(false);
    }
  }

  async function removeCredential(credentialId: string) {
    setError(null);
    try {
      await api.deleteCredential(credentialId);
      setCredentials((current) => current.filter((c) => c.id !== credentialId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.settings.couldNotDeleteKey);
    }
  }

  async function subscribe(plan: Plan) {
    setBillingError(null);
    setBillingBusy(plan);
    try {
      const session = await api.checkout(plan);
      // Backend + Stripe's webhook are the only real source of truth for a
      // plan change (noema/services/billing.py's own docstring) -- this tab
      // never sets `account.plan` itself, it only ever redirects to Stripe's
      // own hosted checkout and lets the webhook do the real work later.
      window.location.href = session.url;
    } catch (err) {
      setBillingError(err instanceof Error ? err.message : t.settings.couldNotStartCheckout);
      setBillingBusy(null);
    }
  }

  async function manageBilling() {
    setBillingError(null);
    setBillingBusy('portal');
    try {
      const session = await api.billingPortal();
      window.location.href = session.url;
    } catch (err) {
      setBillingError(err instanceof Error ? err.message : t.settings.couldNotOpenPortal);
      setBillingBusy(null);
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
      setDangerError(err instanceof Error ? err.message : t.settings.notDeleted);
    }
  }

  return (
    <Shell>
      <h1 className="font-display text-2xl text-ink-900">{t.settings.title}</h1>

      {meta?.local && (
        <p className="mt-6 max-w-reading border-l-2 border-line pl-4 text-sm text-ink-600">
          {t.settings.localModeNote1}
          <span className="text-ink-900">{t.settings.localMode}</span>
          {t.settings.localModeNote2}
        </p>
      )}

      <section className="mt-10 max-w-reading">
        <h2 className="text-lg text-ink-900">{t.settings.providers}</h2>
        <p className="mt-2 text-sm text-ink-600">
          {meta?.local
            ? t.settings.providersLocalLede(meta.default_provider)
            : t.settings.providersLede}
        </p>

        <ul className="mt-6 divide-y divide-line border-y border-line">
          {providers.map((p) => (
            <li key={p.name} className="flex items-center justify-between py-3">
              <span className="text-sm text-ink-800">
                {p.name}
                {p.is_default && <span className="ml-2 text-xs text-ink-400">{t.settings.default}</span>}
              </span>
              <span className={`text-xs ${p.configured ? 'text-positive' : 'text-ink-400'}`}>
                {p.configured ? t.settings.configured : t.settings.noKey}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* Hidden rather than disabled in local mode: there is no key to add, because
          there is nothing to authenticate against. */}
      <section className={`mt-12 max-w-reading ${meta?.local ? 'hidden' : ''}`}>
        <h2 className="text-lg text-ink-900">{t.settings.addKey}</h2>

        <form onSubmit={addKey} className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-ink-500">{t.settings.provider}</span>
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
            <span className="text-xs uppercase tracking-wide text-ink-500">{t.settings.apiKey}</span>
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
            {busy ? t.settings.verifying : t.common.save}
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
                  onClick={() => void removeCredential(credential.id)}
                  className="text-xs text-ink-500 transition-colors duration-state hover:text-critical"
                >
                  {t.common.delete}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-12 max-w-reading">
        <h2 className="text-lg text-ink-900">{t.common.language}</h2>
        <p className="mt-2 text-sm text-ink-600">{t.settings.languageLede}</p>
        <div className="mt-4">
          <LanguageSwitcher />
        </div>
      </section>

      {/* Local mode has no account server-side to bill -- "no account, no
          upload, no telemetry" is the deployment's own point. */}
      {!meta?.local && (
        <section className="mt-12 max-w-reading">
          <h2 className="text-lg text-ink-900">{t.settings.billing}</h2>
          <p className="mt-2 text-sm text-ink-600">
            {t.settings.currentPlan(planLabel(account?.plan, t))}
          </p>

          <ul className="mt-6 divide-y divide-line border-y border-line">
            {plans
              .filter((p) => p.plan !== 'free')
              .map((p) => (
                <li key={p.plan} className="flex items-center justify-between py-4">
                  <span className="text-sm text-ink-800">
                    {planLabel(p.plan, t)}
                    <span className="ml-2 text-xs text-ink-400">
                      {cents(p.monthly_price_cents)}/{t.settings.perMonth}
                    </span>
                  </span>
                  {account?.plan === p.plan ? (
                    <span className="text-xs text-positive">{t.settings.yourPlan}</span>
                  ) : account && account.plan !== 'free' ? (
                    // Already on a different paid plan: a second checkout would
                    // start a second Stripe subscription, not switch this one.
                    // The portal below is the real way to change plans.
                    <span className="text-xs text-ink-400">{t.settings.usePortalToSwitch}</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void subscribe(p.plan)}
                      disabled={billingBusy !== null}
                      className="rounded-md border border-line px-3 py-1.5 text-xs text-ink-800 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
                    >
                      {billingBusy === p.plan ? t.settings.redirecting : t.settings.subscribe}
                    </button>
                  )}
                </li>
              ))}
          </ul>

          {account && account.plan !== 'free' && (
            <button
              type="button"
              onClick={() => void manageBilling()}
              disabled={billingBusy !== null}
              className="mt-4 text-xs text-ink-500 transition-colors duration-state hover:text-ink-900 disabled:opacity-50"
            >
              {billingBusy === 'portal' ? t.settings.redirecting : t.settings.manageSubscription}
            </button>
          )}

          {billingError && (
            <p role="alert" className="mt-3 text-sm text-critical">
              {billingError}
            </p>
          )}
        </section>
      )}

      <section className="mt-16 max-w-reading">
        <h2 className="text-lg text-ink-900">{t.settings.yourData}</h2>
        <p className="mt-2 text-sm text-ink-600">
          {t.settings.yourDataLede}
        </p>

        <button
          type="button"
          onClick={exportEverything}
          disabled={exporting}
          className="mt-4 rounded-md border border-line px-4 py-2 text-sm text-ink-800 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
        >
          {exporting ? t.settings.preparing : t.settings.exportEverything}
        </button>

        <div className="mt-10 rounded-lg border border-line p-5">
          <h3 className="text-sm font-medium text-ink-900">{t.settings.deleteAccount}</h3>
          <p className="mt-2 text-sm text-ink-600">
            {t.settings.deleteLede}
          </p>

          <label className="mt-4 block">
            <span className="text-xs uppercase tracking-wide text-ink-500">
              {t.settings.typeEmail}
            </span>
            <input
              type="text"
              value={confirmDelete}
              onChange={(event) => setConfirmDelete(event.target.value)}
              autoComplete="off"
              placeholder={account?.email ?? 'you@example.com'}
              className="mt-1.5 block w-full max-w-sm rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900"
            />
          </label>

          <button
            type="button"
            onClick={deleteAccount}
            disabled={!account || confirmDelete.trim().toLowerCase() !== account.email}
            className="mt-4 rounded-md border border-critical px-4 py-2 text-sm text-critical transition-colors duration-state hover:bg-critical hover:text-ink-50 disabled:opacity-40"
          >
            {t.settings.deleteMyAccount}
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

function cents(value: number): string {
  return (value / 100).toLocaleString(undefined, {
    style: 'currency',
    currency: 'BRL',
  });
}

function planLabel(plan: Plan | undefined, t: Dict): string {
  switch (plan) {
    case 'student':
      return t.settings.planStudent;
    case 'pro':
      return t.settings.planPro;
    case 'max':
      return t.settings.planMax;
    default:
      return t.settings.planFree;
  }
}
