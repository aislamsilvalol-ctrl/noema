import { notFound } from 'next/navigation';
import { MinoSheet } from './MinoSheet';

/**
 * The character sheet: every state of Mino, live, on one page.
 *
 * Development only. It is how a pose is checked before it ships and the
 * reference the state library in MINO_CHARACTER_SPEC.md points at. In a
 * production build the route does not exist.
 */
export default function MinoSheetPage() {
  if (process.env.NODE_ENV === 'production') notFound();
  return <MinoSheet />;
}
