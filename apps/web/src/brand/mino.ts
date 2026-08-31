/**
 * Mino, NOEMA's learning companion -- one substitution point.
 *
 * Every state resolves through this map instead of a literal path scattered
 * across components, so replacing placeholder art with the official
 * character (see `MINO_ASSETS.md` at the repo root) is a five-file swap in
 * `apps/web/public/brand/mino/`, not a grep-and-replace across the app.
 *
 * The files here today are deliberately abstract placeholders, not draft
 * character art -- see `MINO_ASSETS.md` before assuming otherwise.
 */

export type MinoState = 'hero' | 'reading' | 'thinking' | 'studying' | 'pointing' | 'celebrating';

export const MINO_ASSETS: Record<MinoState, string> = {
  hero: '/brand/mino/mino-hero.svg',
  reading: '/brand/mino/mino-reading.svg',
  thinking: '/brand/mino/mino-thinking.svg',
  studying: '/brand/mino/mino-studying.svg',
  pointing: '/brand/mino/mino-pointing.svg',
  celebrating: '/brand/mino/mino-celebrating.svg',
};
