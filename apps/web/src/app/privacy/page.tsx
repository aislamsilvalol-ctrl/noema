import type { Metadata } from 'next';
import { LegalDocument } from '@/components/legal/LegalDocument';
import { legalConfig } from '@/lib/legal-config';

// English, like every other server-rendered string on the site: the HTML is
// `lang="en"` and the visitor's language applies on hydration.
export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'What Noema collects, why, and where it goes.',
  alternates: { canonical: '/privacy' },
};

/**
 * Real, product-specific content -- what this codebase actually does, not a
 * generic template. The text lives in the locale dictionaries (`legal.privacy`
 * in src/locales/*.ts) so the three languages are kept in step by the
 * compiler; the body is rendered by `LegalDocument`, which follows the
 * visitor's language like the rest of the site. Company identity comes from
 * `legalConfig`, deliberately `null` until a real value is filled in -- see
 * that file's own docstring for why nothing here invents one.
 */
export default function PrivacyPage() {
  return <LegalDocument kind="privacy" config={legalConfig} />;
}
