/**
 * Mino, NOEMA's learning companion -- the official renders, one map.
 *
 * The files are Blender renders of the character (see
 * MINO_CHARACTER_SPEC.md, "Official renders"), on transparent ground,
 * 800 px. Components go through `<Mino3D pose="…">`, never a literal path,
 * so a re-render is a file swap in `apps/web/public/brand/mino/3d/`.
 *
 * The live, stateful character is the rig (`components/mino`); these are
 * the still figures for the places that want fidelity over motion.
 */

export type MinoRenderPose = 'idle' | 'wave' | 'think' | 'point';

export const MINO_RENDERS: Record<MinoRenderPose, string> = {
  idle: '/brand/mino/3d/mino-idle.png',
  wave: '/brand/mino/3d/mino-wave.png',
  think: '/brand/mino/3d/mino-think.png',
  point: '/brand/mino/3d/mino-point.png',
};

/** The renders' intrinsic size: every still is the same frame. */
export const MINO_RENDER_SIZE = { width: 640, height: 800 } as const;

/** Widths the compressed posters exist at (`mino-<pose>-<w>.avif|webp`). */
export const MINO_POSTER_WIDTHS = [320, 640] as const;

/** A `srcSet` for one pose in one format; the PNG stays as the fallback `src`. */
export function minoPosterSet(pose: MinoRenderPose, format: 'avif' | 'webp'): string {
  return MINO_POSTER_WIDTHS.map((w) => `/brand/mino/3d/mino-${pose}-${w}.${format} ${w}w`).join(', ');
}
