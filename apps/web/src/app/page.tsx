'use client';

// The landing is the character system's first home: see
// components/landing/v3/LandingV3.tsx and NOEMA_LANDING_V3.md. Client-rendered
// because the copy follows the visitor's language and the demo streams.

import { LandingV3 } from '@/components/landing/v3/LandingV3';

export default function LandingPage() {
  return <LandingV3 />;
}
