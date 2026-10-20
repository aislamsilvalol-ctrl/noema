'use client';

import Link from 'next/link';
import { useT } from '@/lib/i18n';

/** The way from Home's trail to the full map on Progress. */
export function MapLink() {
  const t = useT();
  return (
    <Link href="/progress" className="text-sm text-accent underline-offset-4 hover:underline">
      {t.home.trail.map} →
    </Link>
  );
}
