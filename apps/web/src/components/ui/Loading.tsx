'use client';

/**
 * A loading state with the product's own face on it.
 *
 * Not a spinner: one line of text, and — where the wait is the screen's
 * whole content, not a row in a list — a small Mino thinking. `role="status"`
 * so assistive technology hears it once; the figure is decorative.
 * Loaders stay quick and quiet: no animation beyond the character's own.
 */

import { Mino } from '@/components/mino/Mino';
import { useT } from '@/lib/i18n';

export function Loading({
  label,
  mino = false,
  className = '',
}: {
  /** Defaults to the common "Loading…" line. */
  label?: string;
  /** Show the small thinking figure (screen-level waits only). */
  mino?: boolean;
  className?: string;
}) {
  const t = useT();
  return (
    <p role="status" className={`flex items-center gap-3 text-sm text-ink-500 ${className}`}>
      {mino && <Mino state="thinking" size="sm" />}
      <span>{label ?? t.common.loading}</span>
    </p>
  );
}
