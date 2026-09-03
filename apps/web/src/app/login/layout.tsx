import type { Metadata } from 'next';

/**
 * `login/page.tsx` is a client component and can't export `metadata` itself
 * -- this sibling server layout carries it instead. `noindex` because
 * neither a login nor a signup form has anything worth a search result
 * (brief item 101), matching the same route already listed in
 * `robots.ts`'s disallow set.
 */
export const metadata: Metadata = {
  title: 'Entrar',
  robots: { index: false, follow: false },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
