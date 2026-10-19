'use client';

// The landing (v7): six scenes, the product in the second — see
// components/landing/v7/LandingV7.tsx and docs/landing-v7.md. The previous page
// (v6) stays in the tree: rolling back is swapping the import below.
// Client-rendered because the copy follows the visitor's language and the
// tutor demo streams.

import { LandingV7 } from '@/components/landing/v7/LandingV7';

export default function LandingPage() {
  return <LandingV7 />;
}
