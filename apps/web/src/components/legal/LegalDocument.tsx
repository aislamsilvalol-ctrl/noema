'use client';

/**
 * The body of /privacy and /terms: one component, two documents.
 *
 * Client-rendered so the text follows the visitor's language the same way
 * every other page does (`useI18n`): the server paints English, the provider
 * applies the stored or detected locale on hydration. The page files stay
 * server components so they keep their `metadata`.
 *
 * Identity comes from `LegalConfig` and is never invented here. What the top
 * of the page says depends on `stage`:
 *
 * - early-access: a calm notice that there is no registered company yet and
 *   that its details will be published before general availability. Contact
 *   points at the two channels that do exist — the in-app "Report a problem"
 *   dialog and the public GitHub issues page.
 * - launched with a missing field: the red "configuration required" box and
 *   `[… to be defined]` placeholders, so a real launch cannot ship half-filled.
 */

import Link from 'next/link';
import { useI18n, type Locale } from '@/lib/i18n';
import { LEGAL_ISSUES_URL, legalConfigIsComplete, type LegalConfig } from '@/lib/legal-config';

const DATE_LOCALE: Record<Locale, string> = { en: 'en-US', pt: 'pt-BR', es: 'es' };
const CONFIG_FILE = 'apps/web/src/lib/legal-config.ts';

interface Props {
  kind: 'privacy' | 'terms';
  config: LegalConfig;
}

export function LegalDocument({ kind, config }: Props) {
  const { t, locale } = useI18n();
  const copy = t.legal;
  const doc = kind === 'privacy' ? copy.privacy : copy.terms;
  const complete = legalConfigIsComplete(config);
  const earlyAccess = config.stage === 'early-access';
  const updated = new Intl.DateTimeFormat(DATE_LOCALE[locale], {
    dateStyle: 'long',
    timeZone: 'UTC',
  }).format(new Date(config.lastUpdated));

  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Link href="/" className="font-display text-lg tracking-tight text-ink-900">
          NOEMA
        </Link>
      </header>

      <article className="prose-reading mx-auto px-6 pb-24 pt-8">
        <h1 className="font-display text-3xl text-ink-900">{doc.title}</h1>
        <p className="mt-2 text-sm text-ink-500">{copy.updated(updated)}</p>

        {earlyAccess && !complete && (
          <div className="my-8 rounded-md border border-line bg-ink-100 p-4">
            <p className="text-sm font-medium text-ink-900">{copy.earlyAccess.title}</p>
            <p className="mt-1 text-sm text-ink-700">{copy.earlyAccess.body}</p>
          </div>
        )}

        {!earlyAccess && !complete && (
          <div className="my-8 rounded-md border border-critical/40 bg-critical/5 p-4">
            <p className="text-sm font-medium text-critical">{copy.configRequired.title}</p>
            <p className="mt-1 text-sm text-ink-700">{copy.configRequired.body(CONFIG_FILE)}</p>
          </div>
        )}

        {kind === 'privacy' ? (
          <PrivacyBody config={config} earlyAccess={earlyAccess} />
        ) : (
          <TermsBody />
        )}

        <h2>{doc.contact.title}</h2>
        <p>
          {doc.contact.lead}{' '}
          {config.contactEmail ? (
            <>
              <a href={`mailto:${config.contactEmail}`} className="text-accent">
                {config.contactEmail}
              </a>
              .
            </>
          ) : earlyAccess ? (
            <>
              {copy.contact.inApp(t.feedback.open)} {copy.contact.or}{' '}
              <a href={LEGAL_ISSUES_URL} className="text-accent" rel="noopener noreferrer">
                {copy.contact.issues}
              </a>
              .
            </>
          ) : (
            <>{copy.placeholders.email}.</>
          )}
        </p>
      </article>
    </main>
  );
}

function PrivacyBody({ config, earlyAccess }: { config: LegalConfig; earlyAccess: boolean }) {
  const { t } = useI18n();
  const copy = t.legal;
  const doc = copy.privacy;

  return (
    <>
      <h2>{doc.who.title}</h2>
      {earlyAccess && !config.companyName ? (
        <p>{doc.who.earlyAccess}</p>
      ) : (
        <p>
          {doc.who.operating(config.companyName ?? copy.placeholders.company)}
          {config.address ? (
            <>
              , {doc.who.basedAt} {config.address}
              {config.city ? `, ${config.city}` : ''}
              {config.region ? ` - ${config.region}` : ''}
              {config.postalCode ? `, ${config.postalCode}` : ''}
              {config.country ? `, ${config.country}` : ''}
            </>
          ) : (
            ` ${copy.placeholders.address}`
          )}
          .
        </p>
      )}

      <h2>{doc.collect.title}</h2>
      {doc.collect.items.map((item) => (
        <p key={item.label}>
          <strong>{item.label}</strong> {item.body}
        </p>
      ))}

      <h2>{doc.flows.title}</h2>
      <p>{doc.flows.providers}</p>
      <p>{doc.flows.files}</p>

      <h2>{doc.deletion.title}</h2>
      <p>{doc.deletion.body}</p>
    </>
  );
}

function TermsBody() {
  const { t } = useI18n();
  const doc = t.legal.terms;

  return (
    <>
      <h2>{doc.what.title}</h2>
      <p>{doc.what.is}</p>
      <p>
        <strong>{doc.what.isNotLead}</strong> {doc.what.isNot}
      </p>

      <h2>{doc.account.title}</h2>
      <p>{doc.account.body}</p>

      <h2>{doc.billing.title}</h2>
      <p>{doc.billing.body}</p>

      <h2>{doc.acceptableUse.title}</h2>
      <p>{doc.acceptableUse.body}</p>

      <h2>{doc.content.title}</h2>
      <p>{doc.content.body}</p>

      <h2>{doc.noWarranty.title}</h2>
      <p>{doc.noWarranty.body}</p>
    </>
  );
}
