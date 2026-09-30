'use client';

// The landing as a film in eight pinned scenes — see
// components/landing/v6/LandingV6.tsx and docs/brand-os.md. The previous page
// (v5) stays in the tree: rolling back is swapping the import below.
// Client-rendered because the copy follows the visitor's language and the
// tutor demo streams.

import { LandingV6 } from '@/components/landing/v6/LandingV6';

export default function LandingPage() {
  return <LandingV6 />;
}
