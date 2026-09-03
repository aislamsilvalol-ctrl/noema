import type { Metadata } from 'next';
import localFont from 'next/font/local';
import Script from 'next/script';
// KaTeX bundles its own fonts; importing from the package keeps them resolvable.
import 'katex/dist/katex.min.css';
import '@/styles/globals.css';
import { I18nProvider } from '@/lib/i18n';
import { THEME_BOOT_SCRIPT, ThemeProvider } from '@/lib/theme';
import { siteConfig } from '@/lib/site-config';

// Design V2 is a token layer keyed off <html data-design="v2"> (see the end of
// globals.css), switched by a build-time flag so V1 and V2 can be compared
// from the same code. When V2 is validated the flag, the attribute and the V1
// tokens all go — two designs are not maintained.
const DESIGN_V2 = process.env.NEXT_PUBLIC_DESIGN_V2 === '1';

/**
 * Typography carries the identity, so the faces are vendored into the repo and
 * loaded from disk.
 *
 * `next/font/google` downloads at build time, which makes every build depend on
 * fonts.gstatic.com being reachable — it broke CI once, and it would break any
 * air-gapped build of a project whose main promise is that it runs entirely on
 * your machine. These are the latin subsets of the variable faces; see
 * src/fonts/OFL.txt for their licence.
 */
const display = localFont({
  src: '../fonts/newsreader.woff2',
  weight: '400 500',
  variable: '--font-display-loaded',
  display: 'swap',
  fallback: ['Georgia', 'serif'],
});

const ui = localFont({
  src: '../fonts/inter.woff2',
  weight: '400 600',
  variable: '--font-ui-loaded',
  display: 'swap',
  fallback: ['system-ui', 'sans-serif'],
});

const mono = localFont({
  src: '../fonts/jetbrains-mono.woff2',
  weight: '400',
  variable: '--font-mono-loaded',
  display: 'swap',
  fallback: ['ui-monospace', 'monospace'],
});

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.baseUrl),
  title: {
    default: `${siteConfig.name} — ${siteConfig.tagline}`,
    // A page below the root that sets its own plain `title` (e.g. "Entrar")
    // renders as "Entrar — NOEMA" -- one place decides the suffix, instead
    // of every page repeating "NOEMA" in its own title string (the brief's
    // own explicit "don't repeat 'Noema' on every page" instruction).
    template: `%s — ${siteConfig.name}`,
  },
  description: siteConfig.description,
  alternates: { canonical: '/' },
  openGraph: {
    title: `${siteConfig.name} — ${siteConfig.tagline}`,
    description: siteConfig.description,
    url: siteConfig.baseUrl,
    siteName: siteConfig.name,
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: `${siteConfig.name} — ${siteConfig.tagline}`,
    description: siteConfig.description,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-design={DESIGN_V2 ? 'v2' : undefined}
      className={`${display.variable} ${ui.variable} ${mono.variable}`}
    >
      <head>
        {/* Sets data-theme from storage before the first paint. Without this a
            dark-mode visitor gets one white frame while React hydrates — the
            exact flash the theme switch is designed never to produce. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        {/* Plausible: no cookies, no personal data, so no consent banner is
            needed for it under the usual GDPR/LGPD reading of "essential vs.
            tracking" cookies -- there simply are none here to consent to.
            Production-only (`isProduction` checks the real Railway
            environment name), so local dev and any preview/staging deploy
            never appear in the real numbers. */}
        {siteConfig.isProduction && (
          <Script
            defer
            data-domain={siteConfig.domain}
            src="https://plausible.io/js/script.js"
            strategy="afterInteractive"
          />
        )}
        {/* The server always renders English (`lang="en"` above matches); the
            provider applies the stored or detected locale on hydration. */}
        <ThemeProvider>
          <I18nProvider>{children}</I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
