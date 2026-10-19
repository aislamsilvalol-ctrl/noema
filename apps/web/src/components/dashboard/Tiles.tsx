'use client';

/**
 * The image tiles: a crop of one of NOEMA's places, a title and one line of
 * context. `LearningTile` is something to pick up again (horizontal, small);
 * `ExploreTile` is something new (editorial, the text set on the plate).
 * The same subject always lands in the same place (`plateFor`).
 */

import Link from 'next/link';
import type { CSSProperties } from 'react';
import { Landscape, useReveal } from './Landscape';
import type { Plate } from './homeState';

export function LearningTile({
  href,
  plate,
  kicker,
  title,
  context,
  onClick,
  index = 0,
}: {
  href: string;
  plate: Plate;
  kicker: string;
  title: string;
  context: string | null;
  onClick?: () => void;
  index?: number;
}) {
  const [ref, shown] = useReveal<HTMLAnchorElement>();
  return (
    <Link
      ref={ref}
      href={href}
      onClick={onClick}
      data-shown={shown}
      style={{ '--dash-delay': `${index * 60}ms` } as CSSProperties}
      className="dash-reveal dash-tile group flex w-[82vw] max-w-[22rem] shrink-0 snap-start items-stretch overflow-hidden rounded-md border border-line bg-raised transition-[border-color,transform] duration-fast hover:border-ink-300 sm:w-auto sm:max-w-none"
      data-resume-tile
    >
      <span className="relative w-24 shrink-0 overflow-hidden md:w-28">
        <Landscape plate={plate} sizes="112px" className="absolute inset-0 block h-full w-full [&_img]:h-full [&_img]:w-full [&_img]:object-cover" />
      </span>
      <span className="min-w-0 flex-1 px-4 py-4">
        <span className="block truncate font-mono text-xs uppercase tracking-[0.1em] text-ink-500">{kicker}</span>
        <span className="mt-1 block truncate text-md text-ink-900 group-hover:text-accent">{title}</span>
        {context && <span className="mt-0.5 block truncate text-sm text-ink-500">{context}</span>}
      </span>
    </Link>
  );
}

export function ExploreTile({
  href,
  plate,
  kicker,
  title,
  context,
  large = false,
  onClick,
  index = 0,
}: {
  href: string;
  plate: Plate;
  kicker: string;
  title: string;
  context: string;
  large?: boolean;
  onClick?: () => void;
  index?: number;
}) {
  const [ref, shown] = useReveal<HTMLAnchorElement>();
  return (
    <Link
      ref={ref}
      href={href}
      onClick={onClick}
      data-shown={shown}
      style={{ '--dash-delay': `${index * 70}ms` } as CSSProperties}
      className={`dash-reveal dash-tile group relative flex w-[82vw] max-w-[24rem] shrink-0 snap-start flex-col justify-end overflow-hidden rounded-md bg-dash-deep text-dash-bone md:w-auto md:max-w-none ${
        large ? 'min-h-[300px] md:col-span-2 md:row-span-2 md:min-h-[420px]' : 'min-h-[300px] md:min-h-[200px]'
      }`}
      data-explore-tile
    >
      <Landscape
        plate={plate}
        sizes={large ? '(min-width: 768px) 60vw, 82vw' : '(min-width: 768px) 30vw, 82vw'}
        className="absolute inset-0 block [&_img]:h-full [&_img]:w-full [&_img]:object-cover"
      />
      <span
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-t from-dash-night/90 via-dash-night/35 to-transparent"
      />
      <span className={`relative block p-5 ${large ? 'md:p-8' : ''}`}>
        <span className="block font-mono text-xs uppercase tracking-[0.12em] text-dash-alpenglow">{kicker}</span>
        <span className={`mt-2 block font-display leading-tight text-dash-bone ${large ? 'text-2xl md:text-3xl' : 'text-xl'}`}>
          {title}
        </span>
        <span className="mt-1 block text-sm text-dash-bone/75">{context}</span>
      </span>
    </Link>
  );
}
