/**
 * The NOEMA wordmark — locked.
 *
 * There is no logo file. The shipped identity is the word NOEMA set in the
 * product's display face, Newsreader (`src/fonts/newsreader.woff2`, loaded
 * in `app/layout.tsx` as `--font-display`), in capitals, with the tracking
 * the app has always used. This component is the only place it is drawn, so
 * it cannot drift: no other font, no icon, no effects, no re-lettering.
 * Size and colour are the only things a call site may choose.
 */

import Link from 'next/link';

const SIZE = {
  sm: 'text-base',
  md: 'text-lg',
  lg: 'text-2xl',
} as const;

export function Wordmark({
  size = 'md',
  href,
  className = '',
}: {
  size?: keyof typeof SIZE;
  /** Wrap in a link (the rail, the landing header). */
  href?: string;
  className?: string;
}) {
  const classes = `font-display ${SIZE[size]} tracking-wide ${className}`;
  const mark = (
    <span className={classes} translate="no">
      NOEMA
    </span>
  );
  if (href) {
    return (
      <Link href={href} aria-label="NOEMA" className="inline-block">
        {mark}
      </Link>
    );
  }
  return mark;
}
