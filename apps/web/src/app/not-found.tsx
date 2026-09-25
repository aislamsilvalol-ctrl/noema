'use client';

/**
 * Next's not-found convention: every unmatched route lands here with a real
 * 404 status. The page is one of the brand's scenes, the same way the landing
 * closes: the horizon, the sky as the space for one line, one way back.
 *
 * Auth-aware like the landing's own CTA: a signed-out visitor goes home or
 * signs in; a signed-in one goes straight back to learning.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Landscape } from '@/components/landing/v5/Landscape';
import { Wordmark } from '@/components/brand/Wordmark';
import { ButtonLink } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import '@/styles/landing.css';

export default function NotFound() {
  const t = useT();
  // False while api.me() is in flight: the signed-out actions are the safe
  // default, and a signed-in visitor sees theirs a moment later.
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(() => {
        if (!cancelled) setSignedIn(true);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="landing-light scene scene-veil-top min-h-[100svh]">
      <Landscape scene="horizon" priority position="50% 78%" />

      <div className="content mx-auto flex min-h-[100svh] max-w-[1400px] flex-col px-6 md:px-10">
        <header className="py-5">
          <Link href="/" aria-label="NOEMA">
            <Wordmark size="md" className="text-current" />
          </Link>
        </header>

        <div className="pt-[12svh] md:pt-[14svh]">
          <p className="font-mono text-sm fg-faint">404</p>
          <h1 className="display-2 mt-4 max-w-[16ch]">{t.notFound.title}</h1>
          <p className="mt-5 max-w-[44ch] text-lg fg-muted">{t.notFound.body}</p>

          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            {signedIn ? (
              <ButtonLink href="/today" size="lg" className="btn-ember">
                {t.notFound.continueLearning}
              </ButtonLink>
            ) : (
              <>
                <ButtonLink href="/" size="lg" className="btn-ember">
                  {t.notFound.backHome}
                </ButtonLink>
                <Link href="/login" className="text-base underline-offset-4 hover:underline">
                  {t.notFound.signIn}
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
