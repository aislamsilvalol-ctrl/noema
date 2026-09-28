'use client';

/**
 * The phone's answer to a menu or a small dialog: a sheet from the bottom.
 *
 * A dialog in every way that matters to someone not looking at it: it takes
 * focus when it opens and gives it back when it closes, Escape and the
 * backdrop close it, the page under it does not scroll, and it stops above
 * the home indicator. The drag handle is a visual cue only; closing never
 * depends on a gesture.
 *
 * `layout="dialog"` keeps the sheet on phones and centres a small dialog
 * above `md`, where a panel pinned to the bottom of a wide screen is the
 * wrong shape. Same focus, same keys, same backdrop.
 */

import { useEffect, useId, useRef, type ReactNode } from 'react';

export function BottomSheet({
  open,
  onClose,
  title,
  closeLabel,
  layout = 'sheet',
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel: string;
  layout?: 'sheet' | 'dialog';
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const returnTo = useRef<Element | null>(null);
  const titleId = useId();

  // The latest `onClose`, read at key time. Callers pass inline arrows, and
  // the effect below must not re-run (and move focus back to the first
  // button, mid-typing) every time the parent renders a new one.
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    returnTo.current = document.activeElement;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.querySelector<HTMLElement>('button, [href]')?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') close.current();
    }
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKey);
      (returnTo.current as HTMLElement | null)?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  const dialog = layout === 'dialog';

  return (
    <div
      className={`fixed inset-0 z-50 flex items-end ${dialog ? 'md:items-center md:justify-center md:px-4' : ''}`}
      data-bottom-sheet
    >
      <button
        type="button"
        aria-label={closeLabel}
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 bg-ink-900/30"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative max-h-[85dvh] w-full overflow-y-auto rounded-t-lg border-t border-line bg-surface px-5 pt-3 animate-fade-up ${
          dialog ? 'md:max-w-md md:rounded-lg md:border md:shadow-elevation-2' : ''
        }`}
        style={{ paddingBottom: 'calc(1.25rem + env(safe-area-inset-bottom))' }}
      >
        <div
          aria-hidden="true"
          className={`mx-auto h-1 w-10 rounded-full bg-ink-200 ${dialog ? 'md:hidden' : ''}`}
        />
        <div className="mt-4 flex items-center justify-between gap-4">
          <h2 id={titleId} className="text-md text-ink-900">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 px-2 text-sm text-ink-500 hover:text-ink-900"
          >
            {closeLabel}
          </button>
        </div>
        <div className="mt-3">{children}</div>
      </div>
    </div>
  );
}
