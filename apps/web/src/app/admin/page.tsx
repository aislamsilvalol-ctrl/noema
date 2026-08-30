'use client';

import { useCallback, useEffect, useState } from 'react';
import { Shell } from '@/components/Shell';
import {
  ApiError,
  api,
  downloadUsersReport,
  type AdminIntelligence,
  type AdminUser,
  type Plan,
  type PlanReport,
  type SimulatorIn,
  type SimulatorOut,
} from '@/lib/api';
import { useT } from '@/lib/i18n';

/**
 * Admin-only: real usage/cost data (AI Intelligence) and a what-if Economics
 * Simulator. Not linked from the primary nav on purpose — reachable only by
 * URL, matching the backend's own minimal gate (`deps.AdminUser`, an email
 * allowlist, no role system) rather than advertising an admin surface to
 * every signed-in account.
 */
export default function AdminPage() {
  const t = useT();
  const [data, setData] = useState<AdminIntelligence | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.adminIntelligence());
    } catch (err) {
      if (err instanceof ApiError && err.problem.status === 403) {
        setForbidden(true);
        return;
      }
      setLoadError(err instanceof Error ? err.message : t.admin.loadError);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (forbidden) {
    return (
      <Shell>
        <h1 className="font-display text-2xl text-ink-900">{t.admin.accessDeniedTitle}</h1>
        <p className="mt-2 text-sm text-ink-500">{t.admin.accessDeniedBody}</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="font-display text-2xl text-ink-900">{t.admin.title}</h1>

      {loadError && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {loadError}
        </p>
      )}

      {data && <IntelligenceSection data={data} />}

      <div className="mt-16">
        <UsersSection />
      </div>

      <div className="mt-16">
        <ReportsSection />
      </div>

      <div className="mt-16">
        <EconomicsSimulatorSection />
      </div>
    </Shell>
  );
}

const PLANS: Plan[] = ['free', 'student', 'pro', 'max'];

function UsersSection() {
  const t = useT();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState('');
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [planErrors, setPlanErrors] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async (query: string) => {
    try {
      const page = await api.adminUsers(query || undefined);
      setUsers(page.items);
      setNextCursor(page.next_cursor);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : t.admin.couldNotLoadUsers);
    } finally {
      setLoaded(true);
    }
  }, [t]);

  useEffect(() => {
    void load(search);
    // Only on mount -- a search re-query is triggered explicitly by the form
    // below, not on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadMore() {
    if (!nextCursor) return;
    try {
      const page = await api.adminUsers(search || undefined, nextCursor);
      setUsers((current) => [...current, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : t.admin.couldNotLoadUsers);
    }
  }

  async function changePlan(userId: string, plan: Plan) {
    setPlanErrors((current) => {
      const next = { ...current };
      delete next[userId];
      return next;
    });
    try {
      const updated = await api.adminSetPlan(userId, plan);
      setUsers((current) => current.map((u) => (u.id === userId ? updated : u)));
    } catch (err) {
      setPlanErrors((current) => ({
        ...current,
        [userId]: err instanceof Error ? err.message : t.admin.couldNotChangePlan,
      }));
    }
  }

  return (
    <section>
      <h2 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.usersTitle}</h2>
      <p className="mt-2 max-w-reading text-sm text-ink-600">{t.admin.usersNote}</p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void load(search);
        }}
        className="mt-4"
      >
        <label className="block max-w-sm">
          <span className="sr-only">{t.admin.searchUsers}</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t.admin.searchUsers}
            className="w-full rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 transition-colors duration-state focus:border-accent"
          />
        </label>
      </form>

      {loadError && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {loadError}
        </p>
      )}

      {loaded && users.length === 0 && !loadError && (
        <p className="mt-6 text-sm text-ink-500">{t.admin.noUsersFound}</p>
      )}

      {users.length > 0 && (
        <div className="mt-6 space-y-3">
          {users.map((u) => (
            <div
              key={u.id}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3 text-sm"
            >
              <div>
                <p className="text-ink-900">{u.email}</p>
                <p className="mt-0.5 text-xs text-ink-500">
                  {u.display_name} · {t.admin.signedUp}{' '}
                  {new Date(u.created_at).toLocaleDateString()}
                </p>
                <p className="mt-0.5 font-mono text-xs text-ink-600">
                  {t.admin.usageThisMonth}: {u.used_units_this_period} / {u.limit_units}
                </p>
              </div>
              <div className="text-right">
                <label className="block">
                  <span className="sr-only">{t.admin.changePlan}</span>
                  <select
                    value={u.plan}
                    onChange={(event) => void changePlan(u.id, event.target.value as Plan)}
                    className="rounded-md border border-line bg-raised px-2 py-1 text-xs text-ink-900"
                  >
                    {PLANS.map((plan) => (
                      <option key={plan} value={plan}>
                        {plan}
                      </option>
                    ))}
                  </select>
                </label>
                {planErrors[u.id] && (
                  <p role="alert" className="mt-1 text-xs text-critical">
                    {planErrors[u.id]}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {nextCursor && (
        <button
          type="button"
          onClick={() => void loadMore()}
          className="mt-4 text-sm text-ink-600 underline-offset-2 hover:underline"
        >
          {t.admin.loadMore}
        </button>
      )}
    </section>
  );
}

function ReportsSection() {
  const t = useT();
  const [rows, setRows] = useState<PlanReport[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminProfitReport()
      .then(setRows)
      .catch((err) => setLoadError(err instanceof Error ? err.message : t.admin.profitLoadError));
  }, [t]);

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      await downloadUsersReport();
    } catch (err) {
      setExportError(err instanceof Error ? err.message : t.admin.couldNotExport);
    } finally {
      setExporting(false);
    }
  }

  return (
    <section>
      <h2 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.profitTitle}</h2>
      <p className="mt-2 max-w-reading text-sm text-ink-600">{t.admin.profitNote}</p>

      {loadError && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {loadError}
        </p>
      )}

      {rows && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-500">
                <th className="pb-2 pr-4">{t.admin.plan}</th>
                <th className="pb-2 pr-4">{t.admin.userCount}</th>
                <th className="pb-2 pr-4">{t.admin.realCost}</th>
                <th className="pb-2 pr-4">{t.admin.projectedRevenue}</th>
                <th className="pb-2">{t.admin.projectedMargin}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.plan} className="border-b border-line">
                  <td className="py-2 pr-4">{row.plan}</td>
                  <td className="py-2 pr-4 font-mono">{row.user_count}</td>
                  <td className="py-2 pr-4 font-mono">{cents(row.real_cost_cents)}</td>
                  <td className="py-2 pr-4 font-mono">
                    {cents(row.projected_revenue_if_billed_cents)}
                  </td>
                  <td className="py-2 font-mono">
                    {cents(row.projected_margin_if_billed_cents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-6">
        <button
          type="button"
          onClick={() => void exportCsv()}
          disabled={exporting}
          className="rounded-md border border-line px-4 py-2 text-sm font-medium text-ink-700 transition-colors duration-state hover:border-ink-400 disabled:opacity-50"
        >
          {exporting ? t.admin.exporting : t.admin.exportUsersCsv}
        </button>
        {exportError && (
          <p role="alert" className="mt-2 text-sm text-critical">
            {exportError}
          </p>
        )}
      </div>
    </section>
  );
}

function cents(value: number): string {
  return (value / 100).toLocaleString(undefined, {
    style: 'currency',
    currency: 'BRL',
  });
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function IntelligenceSection({ data }: { data: AdminIntelligence }) {
  const t = useT();
  return (
    <section className="mt-8">
      <h2 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.today}</h2>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
        <Stat label={t.admin.requestsToday} value={String(data.requests_today)} />
        <Stat label={t.admin.tokensToday} value={data.tokens_today.toLocaleString()} />
        <Stat label={t.admin.spendToday} value={cents(data.spend_today_cents)} />
        <Stat label={t.admin.spendThisMonth} value={cents(data.spend_this_month_cents)} />
        <Stat label={t.admin.errorRate} value={percent(data.error_rate)} />
      </dl>

      {Object.keys(data.tier_mix).length > 0 && (
        <div className="mt-8">
          <h3 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.tierMix}</h3>
          <dl className="mt-2 space-y-1 text-sm">
            {Object.entries(data.tier_mix).map(([tier, share]) => (
              <div key={tier} className="flex justify-between">
                <dt className="text-ink-600">{tier}</dt>
                <dd className="font-mono">{percent(share)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {data.top_users.length > 0 && (
        <div className="mt-8">
          <h3 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.topUsers}</h3>
          <dl className="mt-2 space-y-1 text-sm">
            {data.top_users.map((u) => (
              <div key={u.user_id} className="flex justify-between">
                <dt className="text-ink-600">{u.email}</dt>
                <dd className="font-mono">{cents(u.spend_cents)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      <div className="mt-8 max-w-reading border-l-2 border-line pl-4 text-xs text-ink-500">
        <p className="font-medium uppercase tracking-wide">{t.admin.notYetTracked}</p>
        <p className="mt-1">
          {t.admin.notYetTrackedBody} {data.not_yet_tracked.join(', ')}
        </p>
      </div>
    </section>
  );
}

const DEFAULT_INPUTS: SimulatorIn = {
  subscribers: 1000,
  messages_per_day: 3,
  avg_input_tokens: 800,
  avg_output_tokens: 400,
  tier_mix: { economy: 0.6, standard: 0.35, premium: 0.05 },
  active_days_per_month: 20,
  plan_price_cents: 5990,
  payment_fee_percent: 3.99,
  payment_fee_fixed_cents: 39,
  billing_fee_percent: 0.7,
  tax_percent: 0,
};

function EconomicsSimulatorSection() {
  const t = useT();
  const [inputs, setInputs] = useState<SimulatorIn>(DEFAULT_INPUTS);
  const [result, setResult] = useState<SimulatorOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setTierShare(tier: 'economy' | 'standard' | 'premium', value: number) {
    setInputs((current) => ({
      ...current,
      tier_mix: { ...current.tier_mix, [tier]: value },
    }));
  }

  async function run(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await api.adminSimulate(inputs));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.admin.couldNotSimulate);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.economicsTitle}</h2>
      <p className="mt-2 max-w-reading text-sm text-ink-600">{t.admin.economicsNote}</p>

      <form onSubmit={run} className="mt-6 grid max-w-2xl grid-cols-2 gap-4">
        <NumberField
          label={t.admin.subscribers}
          value={inputs.subscribers}
          onChange={(v) => setInputs((c) => ({ ...c, subscribers: v }))}
        />
        <NumberField
          label={t.admin.messagesPerDay}
          value={inputs.messages_per_day}
          onChange={(v) => setInputs((c) => ({ ...c, messages_per_day: v }))}
        />
        <NumberField
          label={t.admin.avgInputTokens}
          value={inputs.avg_input_tokens}
          onChange={(v) => setInputs((c) => ({ ...c, avg_input_tokens: v }))}
        />
        <NumberField
          label={t.admin.avgOutputTokens}
          value={inputs.avg_output_tokens}
          onChange={(v) => setInputs((c) => ({ ...c, avg_output_tokens: v }))}
        />
        <NumberField
          label={t.admin.activeDaysPerMonth}
          value={inputs.active_days_per_month}
          onChange={(v) => setInputs((c) => ({ ...c, active_days_per_month: v }))}
        />
        <NumberField
          label={t.admin.planPrice}
          value={inputs.plan_price_cents / 100}
          onChange={(v) => setInputs((c) => ({ ...c, plan_price_cents: v * 100 }))}
        />
        <NumberField
          label={t.admin.tierMixEconomy}
          value={inputs.tier_mix.economy ?? 0}
          step={0.01}
          onChange={(v) => setTierShare('economy', v)}
        />
        <NumberField
          label={t.admin.tierMixStandard}
          value={inputs.tier_mix.standard ?? 0}
          step={0.01}
          onChange={(v) => setTierShare('standard', v)}
        />
        <NumberField
          label={t.admin.tierMixPremium}
          value={inputs.tier_mix.premium ?? 0}
          step={0.01}
          onChange={(v) => setTierShare('premium', v)}
        />
        <NumberField
          label={t.admin.paymentFeePercent}
          value={inputs.payment_fee_percent ?? 0}
          step={0.01}
          onChange={(v) => setInputs((c) => ({ ...c, payment_fee_percent: v }))}
        />
        <NumberField
          label={t.admin.paymentFeeFixed}
          value={(inputs.payment_fee_fixed_cents ?? 0) / 100}
          step={0.01}
          onChange={(v) => setInputs((c) => ({ ...c, payment_fee_fixed_cents: v * 100 }))}
        />
        <NumberField
          label={t.admin.billingFeePercent}
          value={inputs.billing_fee_percent ?? 0}
          step={0.01}
          onChange={(v) => setInputs((c) => ({ ...c, billing_fee_percent: v }))}
        />
        <NumberField
          label={t.admin.taxPercent}
          value={inputs.tax_percent ?? 0}
          step={0.01}
          onChange={(v) => setInputs((c) => ({ ...c, tax_percent: v }))}
        />

        <div className="col-span-2 mt-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-ink-900 px-4 py-2.5 text-sm font-medium text-ink-50 transition-opacity duration-state hover:opacity-90 disabled:opacity-50"
          >
            {busy ? t.admin.simulating : t.admin.runSimulation}
          </button>
        </div>
      </form>

      {error && (
        <p role="alert" className="mt-4 text-sm text-critical">
          {error}
        </p>
      )}

      {result && (
        <dl className="mt-8 max-w-md space-y-2 text-sm">
          <h3 className="text-xs uppercase tracking-wide text-ink-500">{t.admin.results}</h3>
          <Row label={t.admin.aiCostPerUser} value={cents(result.ai_cost_per_user_cents)} />
          <Row label={t.admin.aiCostTotal} value={cents(result.ai_cost_total_cents)} />
          <Row label={t.admin.paymentFees} value={cents(result.payment_fees_cents)} />
          <Row label={t.admin.grossRevenue} value={cents(result.gross_revenue_cents)} />
          <Row label={t.admin.netRevenue} value={cents(result.net_revenue_cents)} />
          <Row label={t.admin.grossMargin} value={`${result.gross_margin_percent.toFixed(1)}%`} />
          <Row label={t.admin.estimatedMrr} value={cents(result.estimated_mrr_cents)} />
        </dl>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="font-mono text-lg text-ink-900">{value}</dd>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-line pb-2">
      <dt className="text-ink-600">{label}</dt>
      <dd className="font-mono text-ink-900">{value}</dd>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1.5 w-full rounded-md border border-line bg-raised px-3 py-2 text-base text-ink-900 transition-colors duration-state focus:border-accent"
      />
    </label>
  );
}
