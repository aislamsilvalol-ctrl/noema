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
        // Design V2 (NOEMA_V2_DESIGN_SYSTEM.md §2.2). These resolve to the V1
        // accent when the v2 token layer is not active, so a migrated component
        // renders sensibly on either side of the flag.
        primary: 'var(--primary, var(--accent))',
        'primary-fg': 'var(--primary-fg, var(--ink-50))',
        'primary-hover': 'var(--primary-hover, var(--accent))',
        signal: 'var(--signal, var(--accent))',
        sunken: 'var(--surface-sunken, var(--ink-100))',
        orange: {
          50: 'var(--noema-orange-50)',
          100: 'var(--noema-orange-100)',
          200: 'var(--noema-orange-200)',
          300: 'var(--noema-orange-300)',
          400: 'var(--noema-orange-400)',
          500: 'var(--noema-orange-500)',
          600: 'var(--noema-orange-600)',
          700: 'var(--noema-orange-700)',
          800: 'var(--noema-orange-800)',
          900: 'var(--noema-orange-900)',
        },
      },
      borderRadius: {
        // Three sizes and full. Nothing else — see the design system §4.
        sm: 'var(--radius-sm, 6px)',
        md: 'var(--radius-md, 10px)',
        lg: 'var(--radius-lg, 16px)',
      },
      boxShadow: {
        'elevation-1': 'var(--elevation-1, 0 1px 2px rgb(28 25 23 / 0.06))',
        'elevation-2': 'var(--elevation-2, 0 8px 24px rgb(28 25 23 / 0.08))',
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
        // Small amplitude, reserved for Mino's reactions and the flashcard
        // settle. Not for buttons, not for panels.
        spring: 'cubic-bezier(0.34, 1.3, 0.64, 1)',
      },
      transitionDuration: {
        state: '120ms',
        enter: '200ms',
        // V2 motion tokens (design system §5); `state`/`enter` stay as aliases.
        fast: '120ms',
        normal: '200ms',
        slow: '320ms',
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
