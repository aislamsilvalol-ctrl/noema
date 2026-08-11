import type { Metadata } from 'next';
import { Inter, JetBrains_Mono, Newsreader } from 'next/font/google';
import '@/styles/globals.css';

/**
 * Typography carries the identity, so the faces are self-hosted through next/font
 * rather than fetched from a third party: no render-blocking request, no external
 * origin to allow in the CSP, and no layout shift when the serif arrives.
 */
const display = Newsreader({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-display-loaded',
  display: 'swap',
});

const ui = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-ui-loaded',
  display: 'swap',
});

const mono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400'],
  variable: '--font-mono-loaded',
  display: 'swap',
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
