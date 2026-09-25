'use client';

/**
 * Plans, read from the API — never typed into a page. When the billing
 * service is not configured the page says so rather than showing a table
 * that cannot be bought from.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Wordmark } from '@/components/brand/Wordmark';
import { ButtonLink } from '@/components/ui/Button';
import { Loading } from '@/components/ui/Loading';
import { api, type PlanPrice } from '@/lib/api';
import { useI18n, type Locale } from '@/lib/i18n';

const CURRENCY: Record<Locale, string> = { pt: 'pt-BR', en: 'en-US', es: 'es' };

export default function PricingPage() {
  const { t, locale } = useI18n();
  const copy = t.landing5.pricing;
  const [plans, setPlans] = useState<PlanPrice[] | null>(null);
  const [failed, setFailed] = useState(false);

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

  const money = new Intl.NumberFormat(CURRENCY[locale], { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });

  return (
    <main className="min-h-screen bg-surface">
      <header className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-5 md:px-10">
        <Wordmark size="md" href="/" className="text-ink-900" />
        <Link href="/login" className="text-sm text-ink-600 hover:text-ink-900">
          {t.landing6.nav.signIn}
        </Link>
      </header>
      <section className="mx-auto max-w-[1400px] px-6 py-16 md:px-10 md:py-24">
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-accent">{copy.kicker}</p>
        <h1 className="mt-4 max-w-[20ch] font-display text-2xl text-ink-900 sm:text-3xl md:text-4xl">{copy.title}</h1>
        {plans === null && !failed && <Loading mino className="mt-12" />}
        {failed && <p className="mt-12 text-base text-ink-600">{copy.unavailable}</p>}
        {plans && plans.length > 0 && (
          <dl className="mt-14 grid gap-10 md:grid-cols-4 md:gap-8">
            {plans.map((plan) => (
              <div key={plan.plan} className="border-t border-line pt-5">
                <dt className="font-display text-2xl text-ink-900">{copy.names[plan.plan] ?? plan.plan}</dt>
                <dd className="mt-2">
                  <span className="font-display text-3xl text-ink-900">
                    {plan.monthly_price_cents === 0 ? copy.free : money.format(plan.monthly_price_cents / 100)}
                  </span>
                  {plan.monthly_price_cents > 0 && <span className="text-sm text-ink-500">{copy.perMonth}</span>}
                </dd>
                <dd className="mt-3 text-sm text-ink-600">{copy.units(plan.monthly_ai_units)}</dd>
              </div>
            ))}
          </dl>
        )}
        {plans && plans.length > 0 && (
          <>
            <p className="mt-6 text-xs text-ink-500">{copy.unitsHint}</p>
            <ButtonLink href="/login?mode=register" variant="primary" className="mt-10">
              {copy.cta}
            </ButtonLink>
          </>
        )}
      </section>
    </main>
  );
}
