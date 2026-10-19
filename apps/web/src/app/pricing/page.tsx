'use client';

/**
 * Plans, read from the API — never typed into a page. Three of them, Plus
 * recommended, monthly or yearly. What a plan buys is said in lessons and
 * modes, never in tokens or credits. When the plans cannot be loaded the page
 * says so rather than showing a table that cannot be bought from.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Wordmark } from '@/components/brand/Wordmark';
import { ButtonLink } from '@/components/ui/Button';
import { Loading } from '@/components/ui/Loading';
import { track } from '@/lib/analytics';
import { api, type BillingInterval, type PlanPrice } from '@/lib/api';
import { useI18n, type Locale } from '@/lib/i18n';

const CURRENCY: Record<Locale, string> = { pt: 'pt-BR', en: 'en-US', es: 'es' };
const RECOMMENDED = 'plus';

export default function PricingPage() {
  const { t, locale } = useI18n();
  const copy = t.landing5.pricing;
  const [plans, setPlans] = useState<PlanPrice[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [interval, setBillingInterval] = useState<BillingInterval>('month');

  useEffect(() => {
    track('pricing_viewed');
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .plans()
      .then((list) => {
        if (!cancelled) setPlans(list);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const money = (cents: number, fraction = false) =>
    new Intl.NumberFormat(CURRENCY[locale], {
      style: 'currency',
      currency: 'BRL',
      minimumFractionDigits: fraction ? 2 : 0,
      maximumFractionDigits: fraction ? 2 : 0,
    }).format(cents / 100);
  const hasAnnual = plans?.some((p) => p.annual_price_cents) ?? false;

  return (
    <main className="min-h-screen bg-surface">
      <header className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-5 md:px-10">
        <Wordmark size="md" href="/" className="text-ink-900" />
        <Link href="/login" className="text-sm text-ink-600 hover:text-ink-900">
          {t.landing6.nav.signIn}
        </Link>
      </header>
      <section className="mx-auto max-w-[1400px] px-4 py-16 sm:px-6 md:px-10 md:py-24">
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-accent">{copy.kicker}</p>
        <h1 className="mt-4 max-w-[20ch] font-display text-2xl text-ink-900 sm:text-3xl md:text-4xl">{copy.title}</h1>

        {hasAnnual && (
          <div role="group" aria-label={copy.annual} className="mt-10 inline-flex rounded-full border border-line p-1 text-sm">
            {(['month', 'year'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={interval === value}
                onClick={() => setBillingInterval(value)}
                className={`min-h-[44px] rounded-full px-5 transition-colors duration-fast ${
                  interval === value ? 'bg-ink-900 text-surface' : 'text-ink-600 hover:text-ink-900'
                }`}
              >
                {value === 'month' ? copy.monthly : copy.annual}
                {value === 'year' && <span className="ml-2 font-mono text-xs text-accent">{copy.annualSave}</span>}
              </button>
            ))}
          </div>
        )}

        {plans === null && !failed && <Loading mino className="mt-12" />}
        {failed && <p className="mt-12 text-base text-ink-600">{copy.unavailable}</p>}
        {plans && plans.length > 0 && (
          <ul className="mt-10 grid gap-6 md:grid-cols-3">
            {plans.map((plan) => {
              const name = copy.names[plan.plan] ?? plan.plan;
              const recommended = plan.plan === RECOMMENDED;
              const yearly = interval === 'year' && plan.annual_price_cents;
              const href =
                plan.monthly_price_cents === 0
                  ? '/login?mode=register'
                  : `/settings?plan=${plan.plan}&interval=${interval}#billing`;
              return (
                <li
                  key={plan.plan}
                  className={`flex flex-col rounded-lg border p-6 ${recommended ? 'border-accent' : 'border-line'}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="font-display text-2xl text-ink-900">{name}</h2>
                    {recommended && (
                      <span className="rounded-full bg-accent/10 px-3 py-1 font-mono text-xs text-accent">{copy.recommended}</span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-ink-600">{copy.taglines[plan.plan]}</p>
                  <p className="mt-6">
                    <span className="font-display text-3xl text-ink-900">
                      {plan.monthly_price_cents === 0
                        ? copy.free
                        : yearly
                          ? money(plan.annual_price_cents ?? 0)
                          : money(plan.monthly_price_cents, true)}
                    </span>
                    {plan.monthly_price_cents > 0 && (
                      <span className="text-sm text-ink-500">{yearly ? copy.perYear : copy.perMonth}</span>
                    )}
                  </p>
                  <p className="mt-1 min-h-[1.25rem] text-xs text-ink-500">
                    {yearly ? copy.annualEquals(money(Math.round((plan.annual_price_cents ?? 0) / 12), true)) : ''}
                  </p>
                  <ul className="mt-6 flex-1 space-y-2 text-sm text-ink-700">
                    {features(plan, copy.features).map((line) => (
                      <li key={line} className="flex gap-2">
                        <span aria-hidden="true" className="text-accent">
                          ✓
                        </span>
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                  <ButtonLink
                    href={href}
                    variant={recommended ? 'primary' : 'secondary'}
                    className="mt-8"
                    onClick={() => track('plan_selected', { plan: plan.plan, interval })}
                  >
                    {plan.monthly_price_cents === 0 ? copy.ctaFree : copy.ctaPaid(name)}
                  </ButtonLink>
                </li>
              );
            })}
          </ul>
        )}
        {plans && plans.length > 0 && <p className="mt-8 max-w-reading text-xs text-ink-500">{copy.modes}</p>}
      </section>
    </main>
  );
}

type FeatureCopy = ReturnType<typeof useI18n>['t']['landing5']['pricing']['features'];

/** What a plan buys, from the numbers the API sent. */
function features(plan: PlanPrice, copy: FeatureCopy): string[] {
  const lines: string[] = [];
  if (plan.monthly_price_cents === 0) {
    if (plan.weekly_lessons) lines.push(copy.weeklyLessons(plan.weekly_lessons));
    lines.push(copy.freeFull);
  } else {
    lines.push(copy.fullLessons(roundLessons(plan.full_lessons)), copy.thenStandard);
  }
  lines.push(copy.review, copy.focus);
  lines.push(plan.max_journeys ? copy.journeys(plan.max_journeys) : copy.unlimitedJourneys);
  if (plan.monthly_documents) lines.push(copy.documents(plan.monthly_documents));
  return lines;
}

/** "About 40", not "about 40.5": the count is an estimate and reads as one. */
function roundLessons(n: number): number {
  return n >= 50 ? Math.round(n / 25) * 25 : Math.round(n / 5) * 5;
}
