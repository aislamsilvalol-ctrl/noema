/**
 * The Mino rig: one SVG, in layers, driven by a Pose.
 *
 * Drawn from the character the owner keeps coming back to — the @noemalearn
 * profile figure (`public/brand/mino/icon-512.png`): one drop-shaped mass,
 * widest low, its crown narrowing into a single short curl that leans
 * right; very large, tall, glossy black eyes wide apart with a big
 * upper-left highlight and a small lower-right one; a faint warm blush; a
 * tiny low smile; the hoodie as a garment over the lower third — a U
 * neckline, short sleeves ending in bone mitts, a kangaroo seam — and two
 * dark stubby feet under the hem. Matte ceramic cream, black, coral-ember,
 * bone — nothing else.
 *
 * Nothing here animates by itself. Transforms are set from `pose`; the
 * smoothing between poses is CSS transitions (globals.css) plus the
 * controller's springs for gaze and head. Under reduced motion the
 * transitions collapse and poses simply switch.
 */

import type { Pose } from '@/components/mino/machine';

const W = 480;

// Rig-space anchors. The eyes sit just below the middle of the mass, wide
// apart; the mouth low and small between them.
const EYE_L = { cx: 172, cy: 258 };
const EYE_R = { cx: 308, cy: 258 };
const EYE_RX = 30;
const EYE_RY = 43;
const PUPIL_TRAVEL = 9;
const MOUTH_Y = 318;

/**
 * The avatar crop: the face. At 28 px the whole figure is a coral hem under
 * a cream drop; the eyes are what has to read beside the name "Mino".
 */
export const FACE_VIEWBOX = '84 60 312 312';

const MOUTH_PATHS: Record<Pose['mouth'], string> = {
  neutral: `M231 ${MOUTH_Y} Q240 ${MOUTH_Y + 5} 249 ${MOUTH_Y}`,
  smile: `M226 ${MOUTH_Y - 2} Q240 ${MOUTH_Y + 11} 254 ${MOUTH_Y - 2}`,
  open: `M230 ${MOUTH_Y - 3} Q240 ${MOUTH_Y + 14} 250 ${MOUTH_Y - 3} Z`,
  think: `M232 ${MOUTH_Y + 2} Q240 ${MOUTH_Y - 1} 248 ${MOUTH_Y + 3}`,
  o: `M240 ${MOUTH_Y - 4} a5 5 0 1 0 0.01 0 Z`,
  flat: `M231 ${MOUTH_Y + 1} L249 ${MOUTH_Y + 1}`,
};

// The mass: one closed drop. The crown narrows to where the curl grows; the
// cheeks are the widest part, low; the base rounds under to sit.
const BODY =
  'M240 54 ' +
  'C 296 66 348 168 370 258 ' + // crown down the right cheek
  'C 388 330 382 398 330 430 ' + // the cheek rounding under, right
  'C 302 446 178 446 150 430 ' + // the base
  'C 98 398 92 330 110 258 ' + // rounding under, left
  'C 132 168 184 66 240 54 Z';

// The hoodie: a garment over the lower third — a U neckline that dips at the
// front, sides a few units proud of the mass, a hem that hangs looser.
const HOODIE =
  'M118 322 ' +
  'C 150 346 200 358 240 358 ' +
  'C 280 358 330 346 362 322 ' +
  'C 384 356 392 402 372 436 ' + // right side, out to the hem
  'C 356 452 124 452 108 436 ' + // the hem
  'C 88 402 96 356 118 322 Z';

// The neckline's inner edge: the mass shows above it, the cloth's own shadow
// sits just under it.
const NECK_SHADOW =
  'M118 322 C 150 346 200 358 240 358 C 280 358 330 346 362 322 ' +
  'C 332 352 282 366 240 366 C 198 366 148 352 118 322 Z';

export function MinoRig({
  pose,
  blink = 0,
  crop = 'full',
  className = '',
  style,
}: {
  pose: Pose;
  /** 0 open … 1 shut; layered over `pose.eyes` by the controller. */
  blink?: number;
  /** `face` frames the head for avatar sizes; `full` is the whole figure. */
  crop?: 'full' | 'face';
  className?: string;
  style?: React.CSSProperties;
}) {
  const openness = Math.max(0, Math.min(1, pose.eyes * (1 - blink)));
  const lidScale = 1 - openness;
  const px = pose.gaze.x * PUPIL_TRAVEL;
  const py = pose.gaze.y * PUPIL_TRAVEL;
  const headShift = pose.turn * 12;
  const headTilt = pose.tilt;
  const lean = pose.lean * 6;

  return (
    <svg
      viewBox={crop === 'face' ? FACE_VIEWBOX : `0 0 ${W} ${W}`}
      role="presentation"
      aria-hidden="true"
      className={`mino-rig ${className}`}
      style={style}
    >
      <defs>
        {/* ceramic: lit from the upper left, warm in the core, cooler at the rim */}
        <radialGradient id="mino-skin" cx="38%" cy="30%" r="74%">
          <stop offset="0%" stopColor="#fffcf5" />
          <stop offset="55%" stopColor="#f4ecdd" />
          <stop offset="100%" stopColor="#d6c9b3" />
        </radialGradient>
        {/* the same skin, in rig units: the lids are shaded exactly like the
            face around them, so a shut eye is skin, not a paler oval */}
        <radialGradient id="mino-skin-abs" gradientUnits="userSpaceOnUse" cx="200" cy="170" r="300">
          <stop offset="0%" stopColor="#fffcf5" />
          <stop offset="55%" stopColor="#f4ecdd" />
          <stop offset="100%" stopColor="#d6c9b3" />
        </radialGradient>
        <radialGradient id="mino-hoodie" cx="42%" cy="18%" r="88%">
          <stop offset="0%" stopColor="#ff9868" />
          <stop offset="50%" stopColor="#ee5a2e" />
          <stop offset="100%" stopColor="#b93c17" />
        </radialGradient>
        <radialGradient id="mino-eye" cx="45%" cy="40%" r="65%">
          <stop offset="0%" stopColor="#2a2622" />
          <stop offset="100%" stopColor="#0b0a0a" />
        </radialGradient>
        <linearGradient id="mino-foot" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3a3742" />
          <stop offset="100%" stopColor="#1c1a22" />
        </linearGradient>
        <clipPath id="mino-eye-l">
          <ellipse cx={EYE_L.cx} cy={EYE_L.cy} rx={EYE_RX} ry={EYE_RY} />
        </clipPath>
        <clipPath id="mino-eye-r">
          <ellipse cx={EYE_R.cx} cy={EYE_R.cy} rx={EYE_RX} ry={EYE_RY} />
        </clipPath>
        <clipPath id="mino-body-clip">
          <path d={BODY} />
        </clipPath>
      </defs>

      {/* ground shadow: lifts with the figure */}
      <ellipse
        className="mino-layer mino-shadow"
        cx="240"
        cy="454"
        rx={112 + pose.lift * 2}
        ry="10"
        fill="#0b1440"
        opacity={0.12 - pose.lift * 0.004}
      />

      <g className="mino-layer mino-figure-root" style={{ transform: `translateY(${pose.lift}px)` }}>
        {/* feet: dark and stubby, under the hem */}
        <g className="mino-layer mino-feet">
          <ellipse cx="198" cy="446" rx="31" ry="12" fill="url(#mino-foot)" />
          <ellipse cx="282" cy="446" rx="31" ry="12" fill="url(#mino-foot)" />
        </g>

        {/* the mass and its garment turn and tilt together, around the base */}
        <g
          className="mino-layer mino-head"
          style={{
            transform: `translateX(${headShift + lean}px) rotate(${headTilt}deg)`,
            transformOrigin: '240px 430px',
          }}
        >
          <g className="mino-layer mino-body" style={{ transformOrigin: '240px 440px' }}>
            <path d={BODY} fill="url(#mino-skin)" />
            {/* the ceramic's occlusion: darker where the mass turns under, and
                a cool rim on the shadow side */}
            <g clipPath="url(#mino-body-clip)">
              <ellipse cx="240" cy="478" rx="200" ry="120" fill="#b9ab93" opacity="0.22" />
              <ellipse cx="392" cy="300" rx="70" ry="150" fill="#c9bca6" opacity="0.18" />
            </g>
            {/* the curl: one short teardrop growing out of the crown, leaning
                right, as in the reference — not a spiral */}
            <path
              className="mino-layer mino-curl"
              d="M228 70 C 222 46 232 22 254 14 C 274 7 296 16 296 34 C 296 46 286 52 278 48 C 274 46 272 40 276 36 C 268 40 262 52 258 66 Z"
              fill="url(#mino-skin)"
              stroke="#dfd3bd"
              strokeWidth="2"
              strokeLinejoin="round"
              style={{ transformOrigin: '242px 70px' }}
            />
            <path d={HOODIE} fill="url(#mino-hoodie)" />
            <path d={NECK_SHADOW} fill="#a4321a" opacity="0.5" />
            {/* the kangaroo seam and the hem's fold */}
            <path d="M196 414 Q240 426 284 414" stroke="#b33a17" strokeWidth="3" fill="none" opacity="0.55" strokeLinecap="round" />
            <path d="M112 434 Q240 448 368 434" stroke="#a4321a" strokeWidth="2.5" fill="none" opacity="0.4" />
            {/* the mark on the chest: three bone lobes */}
            <g className="mino-layer mino-mark" opacity="0.95">
              <circle cx="231" cy="384" r="7" fill="#f9f5ee" />
              <circle cx="249" cy="380" r="7" fill="#f9f5ee" />
              <circle cx="242" cy="396" r="7" fill="#f9f5ee" />
            </g>
          </g>

          {/* blush: faint, outside the eyes, at cheek height */}
          <ellipse cx="126" cy="298" rx="22" ry="12" fill="#f5a184" opacity="0.5" />
          <ellipse cx="354" cy="298" rx="22" ry="12" fill="#f5a184" opacity="0.5" />

          {/* eyes: tall glossy ovals, two highlights each */}
          <g className="mino-layer mino-eyes">
            {[
              { c: EYE_L, clip: 'mino-eye-l' },
              { c: EYE_R, clip: 'mino-eye-r' },
            ].map(({ c, clip }) => (
              <g key={clip}>
                <ellipse cx={c.cx} cy={c.cy} rx={EYE_RX} ry={EYE_RY} fill="url(#mino-eye)" />
                <g clipPath={`url(#${clip})`}>
                  <g style={{ transform: `translate(${px}px, ${py}px)` }} className="mino-gaze">
                    <ellipse cx={c.cx - 9} cy={c.cy - 15} rx="11" ry="13" fill="#fbf8f3" />
                    <circle cx={c.cx + 9} cy={c.cy + 13} r="4.5" fill="#fbf8f3" opacity="0.8" />
                  </g>
                  {/* lower lid: rises with a squint (happy eyes) */}
                  <ellipse
                    className="mino-lid-low"
                    cx={c.cx}
                    cy={c.cy + EYE_RY + 19}
                    rx={EYE_RX + 6}
                    ry={19}
                    fill="url(#mino-skin-abs)"
                    style={{ transform: `translateY(${-pose.squint * 19}px)` }}
                  />
                </g>
                {/* upper lid: body-coloured, a touch larger than the eye and
                    outside its clip, so a shut eye leaves no dark rim; scales
                    down from the top to blink or droop */}
                <ellipse
                  className="mino-lid"
                  cx={c.cx}
                  cy={c.cy}
                  rx={EYE_RX + 2.5}
                  ry={EYE_RY + 2.5}
                  fill="url(#mino-skin-abs)"
                  style={{
                    transform: `scaleY(${lidScale})`,
                    transformOrigin: `${c.cx}px ${c.cy - EYE_RY - 2.5}px`,
                  }}
                />
              </g>
            ))}
          </g>

          {/* mouth */}
          <path
            className="mino-layer mino-mouth"
            d={MOUTH_PATHS[pose.mouth]}
            fill={pose.mouth === 'open' || pose.mouth === 'o' ? '#3d3530' : 'none'}
            stroke="#3d3530"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>

        {/* arms: short sleeves of the hoodie, bone mitts at the ends */}
        <g className={`mino-layer mino-hands mino-hands-${pose.hands}`}>
          <g className="mino-hand mino-hand-l" style={{ transformOrigin: '124px 356px' }}>
            <path d="M124 356 Q96 372 88 396" stroke="#e4522a" strokeWidth="24" strokeLinecap="round" fill="none" />
            <circle cx="86" cy="402" r="17" fill="url(#mino-skin)" />
          </g>
          <g className="mino-hand mino-hand-r" style={{ transformOrigin: '356px 356px' }}>
            <path d="M356 356 Q384 372 392 396" stroke="#e4522a" strokeWidth="24" strokeLinecap="round" fill="none" />
            <circle cx="394" cy="402" r="17" fill="url(#mino-skin)" />
          </g>
          {pose.hands === 'hold' && (
            <rect x="196" y="368" width="88" height="56" rx="6" fill="#fbf8f3" stroke="#e9e3da" strokeWidth="2" />
          )}
          {pose.hands === 'write' && (
            <path d="M388 366 L420 332" stroke="#3d3530" strokeWidth="6" strokeLinecap="round" />
          )}
        </g>
      </g>
    </svg>
  );
}
