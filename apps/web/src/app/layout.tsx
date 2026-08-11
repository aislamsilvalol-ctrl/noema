import type { Metadata } from 'next';
import localFont from 'next/font/local';
// KaTeX bundles its own fonts; importing from the package keeps them resolvable.
import 'katex/dist/katex.min.css';
import '@/styles/globals.css';

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
  title: 'NOEMA — Learn anything. Remember everything.',
  description:
    'An open-source adaptive learning platform that turns your documents, notes and questions into a system that knows what you understand.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${display.variable} ${ui.variable} ${mono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
