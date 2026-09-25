'use client';

/**
 * Reached only when the root layout itself throws, so there is no
 * I18nProvider, no font loader, nothing the normal tree provides: this page
 * renders its own <html>/<body> and depends on as little as possible. The
 * language comes from the browser, and the tokens from the stylesheet alone
 * (data-design keeps the button cobalt, as everywhere else).
 */

import '@/styles/globals.css';

const COPY = {
  en: {
    title: 'NOEMA could not load.',
    body: 'Something failed before the page could start. What you already submitted is saved.',
    retry: 'Try again',
    home: 'Back to home',
    reference: 'Reference',
  },
  pt: {
    title: 'O NOEMA não conseguiu carregar.',
    body: 'Algo falhou antes de a página começar. O que você já enviou está salvo.',
    retry: 'Tentar de novo',
    home: 'Voltar para o início',
    reference: 'Referência',
  },
  es: {
    title: 'NOEMA no pudo cargar.',
    body: 'Algo falló antes de que la página empezara. Lo que ya enviaste está guardado.',
    retry: 'Intentar de nuevo',
    home: 'Volver al inicio',
    reference: 'Referencia',
  },
} as const;

function language(): keyof typeof COPY {
  const tag = typeof navigator === 'undefined' ? 'en' : navigator.language.slice(0, 2);
  return tag === 'pt' || tag === 'es' ? tag : 'en';
}

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const lang = language();
  const t = COPY[lang];

  return (
    <html lang={lang} data-design="v2">
      <body className="bg-surface text-ink-900">
        <main className="mx-auto flex min-h-[100svh] max-w-[1400px] flex-col justify-center px-6 pb-[12svh] md:px-10">
          <p className="font-wordmark text-lg tracking-wide">NOEMA</p>
          <h1 className="mt-10 max-w-[20ch] font-display text-2xl font-medium md:text-3xl">{t.title}</h1>
          <p className="mt-4 max-w-[46ch] text-md text-ink-600">{t.body}</p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <button
              type="button"
              onClick={reset}
              className="h-12 rounded-md bg-primary px-5 text-base font-medium text-primary-fg transition-colors duration-state hover:bg-primary-hover"
            >
              {t.retry}
            </button>
            {/* A plain <a>: the root layout just threw, so a full reload is
                the one route back that does not depend on what broke. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a href="/" className="text-base text-ink-700 underline-offset-4 hover:underline">
              {t.home}
            </a>
          </div>
          {error.digest && (
            <p className="mt-12 font-mono text-xs text-ink-500">
              {t.reference} {error.digest}
            </p>
          )}
        </main>
      </body>
    </html>
  );
}
