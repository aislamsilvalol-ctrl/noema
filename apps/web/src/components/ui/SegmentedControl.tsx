'use client';

/**
 * One choice from a short row: depth 1/2/3, basic/cloze, 5/10/15 minutes.
 *
 * Radio semantics rather than a row of pressed buttons, so a screen reader
 * announces "Cloze, selected, 2 of 2" and arrow keys walk the options — one
 * tab stop for the group, the way a native radio group behaves. The selected
 * segment wears the primary token; it is the current value, not an action,
 * and the `role` is what tells the two apart.
 */

import { useRef, type KeyboardEvent, type ReactNode } from 'react';

type Size = 'sm' | 'md';

const SIZE: Record<Size, string> = {
  sm: 'px-2 py-1 text-xs',
  md: 'px-2.5 py-1 text-sm',
};

export interface SegmentedOption<T extends string | number> {
  value: T;
  label: ReactNode;
}

export function SegmentedControl<T extends string | number>({
  label,
  options,
  value,
  onChange,
  size = 'md',
  className = '',
}: {
  /** Accessible name for the group; the visible caption, if any, stays with the caller. */
  label: string;
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: Size;
  className?: string;
}) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = options.findIndex((option) => option.value === value);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const step =
      event.key === 'ArrowRight' || event.key === 'ArrowDown'
        ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
          ? -1
          : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = (index + step + options.length) % options.length;
    const option = options[next];
    if (!option) return;
    onChange(option.value);
    buttons.current[next]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`inline-flex rounded-md border border-line p-0.5 ${className}`}
    >
      {options.map((option, index) => {
        const selected = index === selectedIndex;
        // Roving tabindex: the selected segment is the group's one tab stop,
        // or the first one while nothing is selected yet.
        const tabStop = selected || (selectedIndex === -1 && index === 0);
        return (
          <button
            key={String(option.value)}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={tabStop ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`rounded-sm transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal ${
              SIZE[size]
            } ${selected ? 'bg-primary text-primary-fg' : 'text-ink-600 hover:text-ink-900'}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
