import type { Config } from 'tailwindcss';

/**
 * The design system from `docs/design-system.md`, expressed as tokens.
 *
 * Colours resolve through CSS variables so light and dark are one set of classes.
 * The type scale is closed on purpose — nine sizes, no others — because an open
 * scale is how interfaces stop looking like one thing.
 */
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: 'var(--ink-50)',
          100: 'var(--ink-100)',
          200: 'var(--ink-200)',
          300: 'var(--ink-300)',
          400: 'var(--ink-400)',
          500: 'var(--ink-500)',
          600: 'var(--ink-600)',
          700: 'var(--ink-700)',
          800: 'var(--ink-800)',
          900: 'var(--ink-900)',
        },
        surface: 'var(--surface)',
        raised: 'var(--surface-raised)',
        line: 'var(--line)',
        accent: 'var(--accent)',
        'accent-soft': 'var(--accent-soft)',
        secondary: 'var(--secondary)',
        'secondary-soft': 'var(--secondary-soft)',
        positive: 'var(--positive)',
        caution: 'var(--caution)',
        critical: 'var(--critical)',
      },
      fontFamily: {
        display: ['var(--font-display)', 'Georgia', 'serif'],
        sans: ['var(--font-ui)', 'system-ui', 'sans-serif'],
        serif: ['var(--font-reading)', 'Georgia', 'serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1.5' }],
        sm: ['0.8125rem', { lineHeight: '1.5' }],
        base: ['0.9375rem', { lineHeight: '1.55' }],
        md: ['1.0625rem', { lineHeight: '1.65' }],
        lg: ['1.25rem', { lineHeight: '1.4' }],
        xl: ['1.5rem', { lineHeight: '1.3' }],
        '2xl': ['2rem', { lineHeight: '1.2' }],
        '3xl': ['3rem', { lineHeight: '1.08', letterSpacing: '-0.02em' }],
        '4xl': ['4rem', { lineHeight: '1.05', letterSpacing: '-0.03em' }],
      },
      maxWidth: {
        reading: '68ch',
      },
      transitionTimingFunction: {
        noema: 'cubic-bezier(0.2, 0, 0, 1)',
      },
      transitionDuration: {
        state: '120ms',
        enter: '200ms',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        'fade-up': 'fade-up 200ms cubic-bezier(0.2, 0, 0, 1)',
      },
    },
  },
  plugins: [],
};

export default config;
