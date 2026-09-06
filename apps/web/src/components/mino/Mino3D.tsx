/**
 * Mino, rendered.
 *
 * The official renders: the character modelled and lit in Blender from the
 * @noemalearn reference posts (MINO_CHARACTER_SPEC.md, "Official renders"),
 * exported on transparent ground. Static by nature — the live rig
 * (`Mino`, `MinoLive`) keeps the states and the gaze; this is for the places
 * where fidelity matters more than motion: the landing hero, the close, an
 * empty state that wants the real figure.
 *
 * Poses are files in `public/brand/mino/3d`; add a pose by adding a file
 * and a line to `MINO_RENDERS`.
 */

import Image from "next/image";
import { MINO_RENDERS, type MinoRenderPose } from "@/brand/mino";

export function Mino3D({
  pose = "idle",
  className = "",
  priority = false,
  alt = "",
}: {
  pose?: MinoRenderPose;
  className?: string;
  /** The landing hero loads first; everything else is lazy. */
  priority?: boolean;
  /** Empty by default: the figure is decoration next to the real copy. */
  alt?: string;
}) {
  return (
    <Image
      src={MINO_RENDERS[pose]}
      alt={alt}
      width={800}
      height={800}
      priority={priority}
      unoptimized
      draggable={false}
      className={`mino-render h-auto w-full select-none ${className}`}
    />
  );
}
