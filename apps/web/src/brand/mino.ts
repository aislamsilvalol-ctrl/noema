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
