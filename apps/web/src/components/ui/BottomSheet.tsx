'use client';

/**
 * The phone's answer to a menu or a small dialog: a sheet from the bottom.
 *
 * A dialog in every way that matters to someone not looking at it: it takes
 * focus when it opens and gives it back when it closes, Escape and the
 * backdrop close it, the page under it does not scroll, and it stops above
 * the home indicator. The drag handle is a visual cue only; closing never
 * depends on a gesture.
 */

import { useEffect, useId, useRef, type ReactNode } from 'react';

export function BottomSheet({
  open,
  onClose,
  title,
  closeLabel,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel: string;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const returnTo = useRef<Element | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    returnTo.current = document.activeElement;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.querySelector<HTMLElement>('button, [href]')?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKey);
      (returnTo.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end" data-bottom-sheet>
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
        className="relative max-h-[85dvh] w-full overflow-y-auto rounded-t-lg border-t border-line bg-surface px-5 pt-3 animate-fade-up"
        style={{ paddingBottom: 'calc(1.25rem + env(safe-area-inset-bottom))' }}
      >
        <div aria-hidden="true" className="mx-auto h-1 w-10 rounded-full bg-ink-200" />
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
