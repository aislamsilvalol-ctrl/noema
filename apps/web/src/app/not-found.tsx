'use client';

/**
 * Next's own not-found convention: reached automatically for any unmatched
 * route, and returns a real HTTP 404 status by construction -- this replaces
 * only the framework's default (unbranded) page, not its status-code
 * behaviour.
 *
 * Auth-aware, the same way the landing page's own CTA already is
 * (`app/page.tsx`): a signed-out visitor gets "Back to home"/"Sign in"; a
 * signed-in one gets "Continue learning" straight to /chat, never asked to
 * sign in again for a page that doesn't exist.
 */

import { useEffect, useState } from 'react';
import { Mino } from '@/components/mino/Mino';
import { ButtonLink } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';

export default function NotFound() {
  const t = useT();
  // Same reasoning as app/page.tsx's own signedIn state: false is the safe,
  // honest default while api.me() is in flight, and the only case it's
  // wrong (a real signed-in visitor) self-corrects a moment later.
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(() => {
        if (!cancelled) setSignedIn(true);
      })
      .catch(() => {
        // Not signed in, or the check failed -- either way the signed-out
        // CTA is the safe default already in state.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <Mino state="confused" size="lg" className="md:h-56 md:w-56" />

      <h1 className="mt-8 font-display text-2xl text-ink-900 md:text-3xl">
        {t.notFound.title}
      </h1>
      <p className="mt-3 max-w-reading text-base text-ink-600">{t.notFound.body}</p>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        {signedIn ? (
          <ButtonLink href="/chat" variant="primary">
            {t.notFound.continueLearning}
          </ButtonLink>
        ) : (
          <>
            <ButtonLink href="/" variant="primary">
              {t.notFound.backHome}
            </ButtonLink>
            <ButtonLink href="/login" variant="secondary">
              {t.notFound.signIn}
            </ButtonLink>
          </>
        )}
      </div>
    </main>
  );
}
