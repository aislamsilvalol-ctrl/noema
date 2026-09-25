/**
 * The text field, styled once — and the textarea and select that share its
 * box, so a form reads as one surface instead of three near-copies of the
 * same class string.
 *
 * Three sizes, matching `Button`: `sm` sits inline next to a small button,
 * `md` is the form default, `lg` is the one field a screen is about (the
 * subject on learn/new, the explanation on explain). Width, margin and font
 * family stay with the caller via `className`; the field never decides how
 * much of the row it owns.
 *
 * Focus is the same ring the button shows, so the keyboard lands somewhere
 * visible whatever it lands on. `ref` arrives as a plain prop under React 19
 * and the spread forwards it, as in Button.
 */

import type { ComponentProps } from 'react';

type Size = 'sm' | 'md' | 'lg';

const SIZE: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-3 py-2 text-sm',
  lg: 'px-4 py-3 text-base',
};

const BASE =
  'rounded-md border border-line bg-raised text-ink-900 placeholder:text-ink-400 ' +
  'outline-none transition-colors duration-fast focus:border-primary ' +
  'focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 ' +
  'disabled:opacity-50';

interface Common {
  size?: Size;
  className?: string;
}

/** The class string alone, for the rare element that has to stay native. */
export function fieldClasses(size: Size = 'md', className = ''): string {
  return `${BASE} ${SIZE[size]} ${className}`;
}

// `size` is also a native attribute on <input> and <select> (a character
// count, a row count); ours wins, so the native one is dropped from the type.
type InputProps = Common & Omit<ComponentProps<'input'>, 'className' | 'size'>;
type TextareaProps = Common & Omit<ComponentProps<'textarea'>, 'className'>;
type SelectProps = Common & Omit<ComponentProps<'select'>, 'className' | 'size'>;

export function Input({ size = 'md', className = '', ...rest }: InputProps) {
  return <input className={fieldClasses(size, className)} {...rest} />;
}

export function Textarea({ size = 'md', className = '', ...rest }: TextareaProps) {
  return <textarea className={fieldClasses(size, className)} {...rest} />;
}

export function Select({ size = 'md', className = '', children, ...rest }: SelectProps) {
  return (
    <select className={fieldClasses(size, className)} {...rest}>
      {children}
    </select>
  );
}
