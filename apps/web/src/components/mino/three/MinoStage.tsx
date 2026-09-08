'use client';

/**
 * Mino in WebGL: the model built in Blender (MINO_CHARACTER_SPEC.md,
 * "Official renders"), loaded as a meshopt-compressed GLB and posed live.
 *
 * The rig is the model's own hierarchy — `Neck`, `ShoulderR`, `ShoulderL`,
 * `EyeR`, `EyeL`, `Tip`, `Hips` — so animation is transforms on named
 * nodes, driven every frame from the same `Pose` the SVG rig reads. No
 * armature, no baked clips: the controller decides what Mino does, this
 * file decides how the body does it. Motion between poses is critically
 * damped, so a state change is a settle, not a cut.
 *
 * Lighting is a small studio: a warm key with soft shadows, a fill, a rim,
 * a synthetic environment for the soft reflections on the eyes and the
 * hoodie, and a contact shadow on the ground. No HDR download.
 */

import { ContactShadows, Environment, Lightformer, useGLTF } from '@react-three/drei';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import type { Pose } from '@/components/mino/machine';

export const MINO_MODEL = '/brand/mino/mino.glb';

export type Framing = 'full' | 'bust';

// ── the pose, translated into transforms ─────────────────────────────

type Arm = { x: number; y: number; z: number };
const REST: Arm = { x: 0, y: 0, z: 0 };
// Rotations on the shoulder pivots, in radians (Euler XYZ). The arm hangs
// along -y; z swings it sideways, x brings it forward. `l` mirrors `r`.
const ARMS: Record<Pose['hands'], { r: Arm; l: Arm }> = {
  rest: { r: REST, l: REST },
  point: { r: { x: -1.75, y: 0, z: -0.25 }, l: REST },
  wave: { r: { x: -0.2, y: 0, z: -2.45 }, l: REST },
  hold: { r: { x: -1.45, y: 0, z: 0.4 }, l: { x: -1.45, y: 0, z: -0.4 } },
  chin: { r: { x: -1.35, y: 0, z: 0.6 }, l: { x: -1.0, y: 0, z: -0.3 } },
  up: { r: { x: -0.3, y: 0, z: -2.7 }, l: { x: -0.3, y: 0, z: 2.7 } },
  write: { r: { x: -1.3, y: 0, z: 0.2 }, l: { x: -1.2, y: 0, z: -0.35 } },
};

const MOUTHS: Record<Pose['mouth'], { sx: number; sy: number; rz: number }> = {
  neutral: { sx: 0.8, sy: 0.7, rz: 0 },
  smile: { sx: 1.1, sy: 1.1, rz: 0 },
  open: { sx: 1.0, sy: 2.6, rz: 0 },
  think: { sx: 0.7, sy: 0.8, rz: 0.35 },
  o: { sx: 0.55, sy: 2.2, rz: 0 },
  flat: { sx: 1.0, sy: 0.3, rz: 0 },
};

function damp(current: number, target: number, lambda: number, dt: number) {
  return THREE.MathUtils.damp(current, target, lambda, dt);
}

function Rig({
  pose,
  blink,
  motion,
  framing,
  onLoaded,
}: {
  pose: Pose;
  blink: number;
  motion: boolean;
  framing: Framing;
  onLoaded?: () => void;
}) {
  const gltf = useGLTF(MINO_MODEL, false, true);
  // Each canvas gets its own copy of the hierarchy; geometries and
  // materials stay shared, which is what makes several figures cheap.
  const scene = useMemo(() => gltf.scene.clone(true), [gltf.scene]);
  const nodes = useMemo(() => {
    const find = (name: string) => scene.getObjectByName(name) ?? null;
    return {
      root: find('Mino'),
      neck: find('Neck'),
      shoulderR: find('ShoulderR'),
      shoulderL: find('ShoulderL'),
      eyeR: find('EyeR'),
      eyeL: find('EyeL'),
      tip: find('Tip'),
      hips: find('Hips'),
      mouth: find('mouth'),
    };
  }, [scene]);
  const base = useRef<{
    eyeR: THREE.Vector3;
    eyeL: THREE.Vector3;
    mouth: THREE.Vector3;
  } | null>(null);
  const clock = useRef(0);
  const target = useRef(pose);
  target.current = pose;
  const blinkRef = useRef(blink);
  blinkRef.current = blink;

  useLayoutEffect(() => {
    scene.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.castShadow = true;
        o.receiveShadow = true;
        const m = o.material as THREE.MeshStandardMaterial;
        if (m && 'envMapIntensity' in m) m.envMapIntensity = 0.55;
      }
    });
    base.current = {
      eyeR: nodes.eyeR?.position.clone() ?? new THREE.Vector3(),
      eyeL: nodes.eyeL?.position.clone() ?? new THREE.Vector3(),
      mouth: nodes.mouth?.position.clone() ?? new THREE.Vector3(),
    };
  }, [scene, nodes]);

  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.05);
    clock.current += dt;
    const t = clock.current;
    const p = target.current;
    const lam = motion ? 9 : 1000; // no easing when motion is reduced: poses switch
    const { root, neck, shoulderR, shoulderL, eyeR, eyeL, tip, mouth } = nodes;
    const b = base.current;
    if (!b) return;

    // breathing and the tip's sway are the only motion Mino makes on his own
    const breath = motion ? Math.sin(t * 1.25) * 0.012 : 0;
    const sway = motion ? Math.sin(t * 0.9 + 1) * 0.06 : 0;

    if (root) {
      root.rotation.x = damp(root.rotation.x, p.lean * 0.16, lam, dt);
      root.position.y = damp(root.position.y, -p.lift * 0.004, lam, dt);
    }
    if (neck) {
      neck.rotation.z = damp(neck.rotation.z, -THREE.MathUtils.degToRad(p.tilt), lam, dt);
      neck.rotation.y = damp(neck.rotation.y, p.turn * 0.4 + p.gaze.x * 0.14, lam, dt);
      neck.rotation.x = damp(neck.rotation.x, p.gaze.y * 0.1, lam, dt);
      neck.scale.y = 1 + breath;
      neck.scale.x = neck.scale.z = 1 - breath * 0.5;
    }
    if (tip) tip.rotation.z = damp(tip.rotation.z, sway + p.tilt * 0.01, lam, dt);

    const openness = Math.max(0.06, p.eyes * (1 - blinkRef.current));
    const squint = 1 - p.squint * 0.45;
    for (const [eye, origin] of [
      [eyeR, b.eyeR],
      [eyeL, b.eyeL],
    ] as const) {
      if (!eye) continue;
      eye.scale.y = damp(eye.scale.y, openness * squint, motion ? 40 : 1000, dt);
      eye.position.x = damp(eye.position.x, origin.x + p.gaze.x * 0.012, lam, dt);
      eye.position.y = damp(eye.position.y, origin.y - p.gaze.y * 0.01 - p.squint * 0.008, lam, dt);
    }
    if (mouth) {
      const m = MOUTHS[p.mouth];
      mouth.scale.x = damp(mouth.scale.x, m.sx, lam, dt);
      mouth.scale.y = damp(mouth.scale.y, m.sy, lam, dt);
      mouth.rotation.z = damp(mouth.rotation.z, m.rz, lam, dt);
    }
    const arms = ARMS[p.hands];
    const waveBeat = motion && p.hands === 'wave' ? Math.sin(t * 7) * 0.22 : 0;
    const cheer = motion && p.hands === 'up' ? Math.sin(t * 5) * 0.08 : 0;
    if (shoulderR) {
      shoulderR.rotation.x = damp(shoulderR.rotation.x, arms.r.x, lam, dt);
      shoulderR.rotation.z = damp(shoulderR.rotation.z, arms.r.z + waveBeat - cheer, lam, dt);
    }
    if (shoulderL) {
      shoulderL.rotation.x = damp(shoulderL.rotation.x, arms.l.x, lam, dt);
      shoulderL.rotation.z = damp(shoulderL.rotation.z, arms.l.z + cheer, lam, dt);
    }
  });

  // Suspense means this body runs only once the GLB is in hand, so this is
  // the moment the figure exists in the scene — which is what the contact
  // shadow has to wait for.
  useEffect(() => onLoaded?.(), [onLoaded]);

  const y = framing === 'bust' ? -0.72 : -0.56;
  return <primitive object={scene} position={[0, y, 0]} />;
}

function Studio({ framing, figure }: { framing: Framing; figure: boolean }) {
  const { camera } = useThree();
  useEffect(() => {
    if (framing === 'bust') {
      camera.position.set(0.18, 0.28, 2.2);
      camera.lookAt(0, 0.22, 0);
    } else {
      camera.position.set(0.42, 0.14, 3.15);
      camera.lookAt(0, 0.02, 0);
    }
  }, [camera, framing]);
  return (
    <>
      <hemisphereLight args={['#fff4e6', '#d9c7b2', 0.55]} />
      <directionalLight
        position={[-1.6, 2.4, 2.2]}
        intensity={2.2}
        color="#fff1e0"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.02}
      >
        <orthographicCamera attach="shadow-camera" args={[-1.2, 1.2, 1.2, -1.2, 0.5, 6]} />
      </directionalLight>
      <directionalLight position={[2.2, 0.6, 1.6]} intensity={0.7} color="#fff8f0" />
      <directionalLight position={[0.8, 1.6, -2.2]} intensity={0.9} color="#ffe2c8" />
      <Environment resolution={64} frames={1}>
        <Lightformer intensity={2.4} color="#fff3e3" position={[-2, 3, 2]} scale={[3, 3, 1]} />
        <Lightformer intensity={1.2} color="#ffffff" position={[3, 1, 1]} scale={[2, 4, 1]} />
        <Lightformer intensity={1.0} color="#ffd9bd" position={[0, 2, -3]} scale={[4, 2, 1]} />
        <Lightformer
          intensity={0.5}
          color="#e9dccb"
          position={[0, -2, 0]}
          rotation={[Math.PI / 2, 0, 0]}
          scale={[5, 5, 1]}
        />
      </Environment>
      {/* One frame is all this shadow needs — but only once there is a figure
          to cast it. Mounted with the lights, it rendered its single frame
          while the model was still suspended and left an uninitialised buffer
          on screen: a brown band across the character. */}
      {figure && (
        <ContactShadows
          position={[0, framing === 'bust' ? -0.72 : -0.56, 0]}
          opacity={0.42}
          scale={2.4}
          blur={2.2}
          far={1.2}
          resolution={256}
          frames={1}
        />
      )}
    </>
  );
}

/** Keeps the frame loop at a modest rate, and only while the stage is on screen. */
function Pacer({ active, fps }: { active: boolean; fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let last = 0;
    const step = (now: number) => {
      if (now - last >= 1000 / fps) {
        last = now;
        invalidate();
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [active, fps, invalidate]);
  return null;
}

export function MinoStage({
  pose,
  blink = 0,
  active = true,
  motion = true,
  framing = 'full',
  dpr = [1, 1.5],
  fps = 30,
  className = '',
  onReady,
}: {
  pose: Pose;
  blink?: number;
  /** Off screen, the loop stops: nothing renders, nothing is computed. */
  active?: boolean;
  /** Reduced motion: no easing, no breathing; poses switch and the frame settles. */
  motion?: boolean;
  framing?: Framing;
  dpr?: [number, number];
  fps?: number;
  className?: string;
  onReady?: () => void;
}) {
  const [figure, setFigure] = useState(false);
  const onFigure = useCallback(() => setFigure(true), []);
  return (
    <Canvas
      className={className}
      dpr={dpr}
      frameloop="demand"
      shadows="soft"
      camera={{ fov: 26, near: 0.1, far: 12 }}
      gl={{
        antialias: true,
        alpha: true,
        powerPreference: 'low-power',
        // Only for the visual check in development: lets a script read the
        // canvas back. Costs memory, so never on by default.
        preserveDrawingBuffer:
          typeof location !== 'undefined' && location.search.includes('mino-capture'),
      }}
      onCreated={({ gl }) => {
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 1.05;
        gl.setClearColor(0x000000, 0);
        onReady?.();
      }}
      style={{ background: 'transparent' }}
    >
      <Pacer active={active} fps={motion ? fps : 4} />
      <Studio framing={framing} figure={figure} />
      <Rig pose={pose} blink={blink} motion={motion} framing={framing} onLoaded={onFigure} />
    </Canvas>
  );
}

useGLTF.preload(MINO_MODEL, false, true);
