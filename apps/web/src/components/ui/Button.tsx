/**
 * The button, styled once.
 *
 * Four intents and the rule that goes with them: `primary` is orange and there
 * is one per screen. `secondary` is the neutral outline for the next-most
 * likely action, `ghost` for the rest, `destructive` for the one that deletes.
 * If two things on a screen are `primary`, one of them is wrong.
 *
 * Tokens resolve to V2 values under `data-design="v2"` and to the V1 accent
 * otherwise (see tailwind.config.ts), so this renders sensibly on both sides
 * of the flag. `busy` swaps the label rather than adding a spinner: the
 * button says what it is doing, and it never changes width mid-press because
 * both labels sit in the same box.
 */

import Link from 'next/link';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'destructive';
type Size = 'sm' | 'md' | 'lg';

const VARIANT: Record<Variant, string> = {
  primary:
    'bg-primary text-primary-fg hover:bg-primary-hover disabled:hover:bg-primary shadow-elevation-1',
  secondary:
    'border border-line bg-transparent text-ink-800 hover:border-ink-400 hover:text-ink-900',
  ghost: 'bg-transparent text-ink-600 hover:text-ink-900',
  destructive:
    'border border-critical bg-transparent text-critical hover:bg-critical hover:text-ink-50',
};

const SIZE: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-5 text-base',
};

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap ' +
  'transition-[background-color,color,border-color,transform] duration-fast ease-noema ' +
  'active:translate-y-px disabled:opacity-50 disabled:active:translate-y-0 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal focus-visible:ring-offset-2';

interface Common {
  variant?: Variant;
  size?: Size;
  /** Shown instead of `children` while true; also sets `aria-busy`. */
  busy?: ReactNode;
  className?: string;
  children: ReactNode;
}

type ButtonProps = Common & Omit<ComponentPropsWithoutRef<'button'>, 'children' | 'className'>;
type LinkProps = Common & { href: string } & Omit<
    ComponentPropsWithoutRef<typeof Link>,
    'children' | 'className' | 'href'
  >;

function classes(variant: Variant, size: Size, className: string): string {
  return `${BASE} ${VARIANT[variant]} ${SIZE[size]} ${className}`;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  busy,
  className = '',
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  const isBusy = busy !== undefined && busy !== false && busy !== null;
  return (
    <button
      type={type}
      aria-busy={isBusy || undefined}
      disabled={disabled || isBusy}
      className={classes(variant, size, className)}
      {...rest}
    >
      {/* Both labels occupy the grid cell; only one is visible, so the width
          is the wider of the two and nothing shifts when `busy` flips. */}
      <span className="grid">
        <span className={`col-start-1 row-start-1 ${isBusy ? 'invisible' : ''}`}>{children}</span>
        {busy !== undefined && busy !== false && busy !== null && (
          <span className={`col-start-1 row-start-1 ${isBusy ? '' : 'invisible'}`}>{busy}</span>
        )}
      </span>
    </button>
  );
}

/** The same hierarchy for navigation: a link that looks like an action. */
export function ButtonLink({
  variant = 'secondary',
  size = 'md',
  className = '',
  children,
  ...rest
}: LinkProps) {
  return (
    <Link className={classes(variant, size, className)} {...rest}>
      {children}
    </Link>
  );
}
