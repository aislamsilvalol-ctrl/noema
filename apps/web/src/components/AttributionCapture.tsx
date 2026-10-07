'use client';

import { useEffect } from 'react';
import { captureAttribution } from '@/lib/analytics';

/** Keeps the landing URL's UTM tags for the signup (see `lib/analytics.ts`). */
export function AttributionCapture() {
  useEffect(() => {
    captureAttribution();
  }, []);
  return null;
}
