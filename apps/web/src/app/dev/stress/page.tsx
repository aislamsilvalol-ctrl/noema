import { notFound } from 'next/navigation';
import { StressSheet } from './StressSheet';

/**
 * Text stress sheet: buttons and choices under long Portuguese, English and
 * Spanish labels, at phone widths. Development only; shot by
 * scripts/visual/stress.json so a label that escapes its box is seen before
 * it ships.
 */
export default function StressPage() {
  if (process.env.NODE_ENV === 'production') notFound();
  return <StressSheet />;
}
