/**
 * TeacherCharacter: who is teaching, as data.
 *
 * Mino is the default and today the only one. The interface never hard-codes
 * his name or rig: every label, avatar and presence figure resolves through
 * `TEACHER`, so a second character — one that belongs to the Noema universe,
 * approved visually first — is a second entry here, not a redesign. Nothing
 * else in the app changes to add one.
 */

import type { ComponentType } from "react";
import type { Pose } from "@/components/mino/machine";
import { MinoRig } from "@/components/mino/rig/MinoRig";

export interface TeacherCharacter {
  id: string;
  /** The name learners see beside every reply and in the composer. */
  name: string;
  Rig: ComponentType<{
    pose: Pose;
    blink?: number;
    className?: string;
    style?: React.CSSProperties;
  }>;
}

export const MINO: TeacherCharacter = {
  id: "mino",
  name: "Mino",
  Rig: MinoRig,
};

/** The active character. One today; a setting later. */
export const TEACHER: TeacherCharacter = MINO;
