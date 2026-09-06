# Mino asset guide

Mino is NOEMA's learning companion. Two forms ship:

- **The renders** — `apps/web/public/brand/mino/3d/*.png`, 800 px,
  transparent. Blender renders of the official model (how it was built:
  `MINO_CHARACTER_SPEC.md`, "Official renders"). Shown by
  `apps/web/src/components/mino/Mino3D.tsx` through the map in
  `apps/web/src/brand/mino.ts`. Used where fidelity matters more than
  motion: the landing hero and close.
- **The live rig** — `apps/web/src/components/mino/rig/MinoRig.tsx`, one
  SVG in layers driven by the state machine. Used everywhere the character
  reacts: the Professor screens, reviews, empty states, the message avatar.
  Drawn to the renders' silhouette.

## Poses

| File | Pose | Where |
|---|---|---|
| `mino-wave.png` | right hand raised, smiling | landing hero |
| `mino-idle.png` | arms down, straight on | landing close, notices |
| `mino-think.png` | hand to the chin, eyes up, head tilted | "thinking" moments |
| `mino-point.png` | right arm out toward the content | pointing at a block |

## Re-rendering

The scene is code (see the spec). A new pose is a query against the
committed scene in the 3D Jutsu project that moves the sleeve curves and,
if needed, the head, renders once at 1000 px and publishes the PNG; then
`sips -Z 800` it into the folder above and add a line to `MINO_RENDERS`.
One render per query: the worker's execution limit is five minutes.

## Brand colour (confirmed)

Orange is the primary brand colour: the hoodie is `#f26b1d` in the
renders (`--accent` `#B5450C` light / `#F0954D` dark in the interface).
Secondary `#2C4A7C` light / `#7DA2E8` dark (`--secondary`). Base: the
app's cream. The character itself is cream, black, orange and white —
never recoloured for dark mode.
