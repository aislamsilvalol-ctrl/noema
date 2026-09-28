import type { Metadata } from 'next';
import { LegalDocument } from '@/components/legal/LegalDocument';
import { legalConfig } from '@/lib/legal-config';

// English, like every other server-rendered string on the site: the HTML is
// `lang="en"` and the visitor's language applies on hydration.
export const metadata: Metadata = {
  title: 'Terms of Use',
  description: 'The rules for using Noema.',
  alternates: { canonical: '/terms' },
};

// Text in `legal.terms` of src/locales/*.ts; identity from `legalConfig`.
// See src/app/privacy/page.tsx for the reasoning, which is the same here.
export default function TermsPage() {
  return <LegalDocument kind="terms" config={legalConfig} />;
}
