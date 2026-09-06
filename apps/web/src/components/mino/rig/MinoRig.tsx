/**
 * The Mino rig: one SVG, in layers, driven by a Pose.
 *
 * Drawn from the reference renders (the @noemalearn posts, see
 * MINO_CHARACTER_SPEC.md "Reference"): one continuous soft body, wide at the
 * base and narrowing to a rounded top — a bell, not an egg and not a head on
 * a cushion — with only a soft waist where the hoodie begins; a single small
 * tip on the crown, leaning right; very large, tall, glossy black eyes wide
 * apart with two highlights; a tiny low mouth; a faint blush; short rounded
 * arms and stubby feet in the body colour; the orange hoodie from the waist
 * down with the white three-lobed mark on the chest. Cream, black, orange,
 * white — nothing else.
 *
 * Still a drawing of the reference, not the reference: official vector
 * renders replace each layer's geometry in place. The props, the transform
 * origins, the class hooks and the controller stay exactly as they are.
 *
 * Nothing here animates by itself. Transforms are set from `pose`; the
 * smoothing between poses is CSS transitions (globals.css) plus the
 * controller's springs for gaze and head. Under reduced motion the
 * transitions collapse and poses simply switch.
 */

import type { Pose } from '@/components/mino/machine';

const W = 480;

// Rig-space anchors. The face sits in the middle of the head, eyes wide apart.
const EYE_L = { cx: 194, cy: 194 };
const EYE_R = { cx: 286, cy: 194 };
const EYE_RX = 26;
const EYE_RY = 34;
const PUPIL_TRAVEL = 8;
const MOUTH_Y = 258;

/**
 * The avatar crop: the head and the top of the hoodie. At 28 px the whole
 * figure is an orange blob under a cream dot; the face is what has to read
 * beside the name "Mino" on every reply.
 */
export const FACE_VIEWBOX = '96 28 288 288';

const MOUTH_PATHS: Record<Pose['mouth'], string> = {
  neutral: `M230 ${MOUTH_Y} Q240 ${MOUTH_Y + 6} 250 ${MOUTH_Y}`,
  smile: `M224 ${MOUTH_Y - 2} Q240 ${MOUTH_Y + 13} 256 ${MOUTH_Y - 2}`,
  open: `M230 ${MOUTH_Y - 3} Q240 ${MOUTH_Y + 15} 250 ${MOUTH_Y - 3} Z`,
  think: `M232 ${MOUTH_Y + 2} Q240 ${MOUTH_Y - 1} 248 ${MOUTH_Y + 3}`,
  o: `M240 ${MOUTH_Y - 5} a5.5 5.5 0 1 0 0.01 0 Z`,
  flat: `M231 ${MOUTH_Y + 1} L249 ${MOUTH_Y + 1}`,
};

// The body: one closed path, a bell. The dome of the head is the narrow
// end (widest at eye level), the outline eases in at the waist and flares
// to the base, which is the widest part of the figure. Head and body are
// the same curve; nothing sits on anything.
const BODY =
  'M240 58 ' +
  'C 302 58 352 118 352 198 ' + // the dome, right
  'C 352 244 346 274 338 292 ' + // down to the waist
  'C 358 318 374 354 372 392 ' + // the flare to the base
  'C 370 418 318 432 240 432 ' +
  'C 162 432 110 418 108 392 ' +
  'C 106 354 122 318 142 292 ' + // the flare, left
  'C 134 274 128 244 128 198 ' + // the dome, left
  'C 128 118 178 58 240 58 Z';

// The hoodie: from the waist down, on the body's own outline, the collar
// dipping at the front.
const HOODIE =
  'M142 292 ' +
  'C 174 282 206 280 240 288 ' +
  'C 274 280 306 282 338 292 ' +
  'C 358 318 374 354 372 392 ' +
  'C 370 418 318 432 240 432 ' +
  'C 162 432 110 418 108 392 ' +
  'C 106 354 122 318 142 292 Z';

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
        <radialGradient id="mino-skin" cx="40%" cy="28%" r="78%">
          <stop offset="0%" stopColor="#fefbf4" />
          <stop offset="60%" stopColor="#f2eadc" />
          <stop offset="100%" stopColor="#d9cdb8" />
        </radialGradient>
        {/* the same skin, in rig units: the lids are shaded exactly like the
            face around them, so a shut eye is skin, not a paler oval */}
        <radialGradient id="mino-skin-abs" gradientUnits="userSpaceOnUse" cx="214" cy="163" r="253">
          <stop offset="0%" stopColor="#fefbf4" />
          <stop offset="60%" stopColor="#f2eadc" />
          <stop offset="100%" stopColor="#d9cdb8" />
        </radialGradient>
        <radialGradient id="mino-hoodie" cx="40%" cy="25%" r="85%">
          <stop offset="0%" stopColor="#ff9450" />
          <stop offset="55%" stopColor="#f26b1d" />
          <stop offset="100%" stopColor="#c44d0e" />
        </radialGradient>
        <radialGradient id="mino-eye" cx="45%" cy="38%" r="65%">
          <stop offset="0%" stopColor="#2b2521" />
          <stop offset="100%" stopColor="#0d0b0a" />
        </radialGradient>
        <clipPath id="mino-eye-l">
          <ellipse cx={EYE_L.cx} cy={EYE_L.cy} rx={EYE_RX} ry={EYE_RY} />
        </clipPath>
        <clipPath id="mino-eye-r">
          <ellipse cx={EYE_R.cx} cy={EYE_R.cy} rx={EYE_RX} ry={EYE_RY} />
        </clipPath>
      </defs>

      {/* ground shadow: lifts with the figure */}
      <ellipse
        className="mino-layer mino-shadow"
        cx="240"
        cy="448"
        rx={112 + pose.lift * 2}
        ry="10"
        fill="#000"
        opacity={0.1 - pose.lift * 0.004}
      />

      <g className="mino-layer mino-figure-root" style={{ transform: `translateY(${pose.lift}px)` }}>
        {/* feet: stubby, body-coloured, under the hoodie's hem */}
        <g className="mino-layer mino-feet">
          <ellipse cx="200" cy="437" rx="30" ry="12" fill="url(#mino-skin)" />
          <ellipse cx="280" cy="437" rx="30" ry="12" fill="url(#mino-skin)" />
        </g>

        {/* head + body are one shape; the whole figure turns and tilts
            around its base */}
        <g
          className="mino-layer mino-head"
          style={{
            transform: `translateX(${headShift + lean}px) rotate(${headTilt}deg)`,
            transformOrigin: '240px 424px',
          }}
        >
          <g className="mino-layer mino-body" style={{ transformOrigin: '240px 432px' }}>
            <path d={BODY} fill="url(#mino-skin)" />
            {/* the tip: one short teardrop on the crown, leaning right, as in the
                reference — not a spiral */}
            <path
              className="mino-layer mino-curl"
              d="M232 64 C 234 46 246 32 262 30 C 272 29 278 38 272 46 C 266 54 254 58 248 66 Z"
              fill="url(#mino-skin)"
              stroke="#e4d9c7"
              strokeWidth="2"
              strokeLinejoin="round"
              style={{ transformOrigin: '244px 64px' }}
            />
            <path d={HOODIE} fill="url(#mino-hoodie)" />
            {/* collar shadow */}
            <path
              d="M142 292 C 174 282 206 280 240 288 C 274 280 306 282 338 292 C 306 294 274 292 240 300 C 206 292 174 294 142 292 Z"
              fill="#b8460c"
              opacity="0.55"
            />
            {/* pocket seam */}
            <path d="M200 402 Q240 414 280 402" stroke="#c9500f" strokeWidth="3" fill="none" opacity="0.5" />
            {/* the mark on the chest: three white lobes */}
            <g className="mino-layer mino-mark" opacity="0.96">
              <circle cx="231" cy="350" r="8" fill="#fbf8f3" />
              <circle cx="249" cy="346" r="8" fill="#fbf8f3" />
              <circle cx="242" cy="363" r="8" fill="#fbf8f3" />
            </g>
          </g>

          {/* cheeks */}
          <ellipse cx="158" cy="238" rx="15" ry="9" fill="#f2b090" opacity="0.38" />
          <ellipse cx="322" cy="238" rx="15" ry="9" fill="#f2b090" opacity="0.38" />

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
                    <ellipse cx={c.cx - 8} cy={c.cy - 12} rx="7" ry="8" fill="#fbf8f3" />
                    <circle cx={c.cx + 7} cy={c.cy + 11} r="2.8" fill="#fbf8f3" opacity="0.75" />
                  </g>
                  {/* lower lid: rises with a squint (happy eyes) */}
                  <ellipse
                    className="mino-lid-low"
                    cx={c.cx}
                    cy={c.cy + EYE_RY + 17}
                    rx={EYE_RX + 6}
                    ry={17}
                    fill="url(#mino-skin-abs)"
                    style={{ transform: `translateY(${-pose.squint * 17}px)` }}
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
            fill={pose.mouth === 'open' || pose.mouth === 'o' ? '#3d3831' : 'none'}
            stroke="#3d3831"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>

        {/* arms: short, rounded, body-coloured mitts on hoodie sleeves */}
        <g className={`mino-layer mino-hands mino-hands-${pose.hands}`}>
          <g className="mino-hand mino-hand-l" style={{ transformOrigin: '152px 330px' }}>
            <path d="M152 330 Q126 346 120 368" stroke="#f26b1d" strokeWidth="22" strokeLinecap="round" fill="none" />
            <circle cx="118" cy="374" r="16" fill="url(#mino-skin)" />
          </g>
          <g className="mino-hand mino-hand-r" style={{ transformOrigin: '328px 330px' }}>
            <path d="M328 330 Q354 346 360 368" stroke="#f26b1d" strokeWidth="22" strokeLinecap="round" fill="none" />
            <circle cx="362" cy="374" r="16" fill="url(#mino-skin)" />
          </g>
          {pose.hands === 'hold' && (
            <rect x="196" y="346" width="88" height="56" rx="6" fill="#fbf8f3" stroke="#e9e3da" strokeWidth="2" />
          )}
          {pose.hands === 'write' && (
            <path d="M346 342 L378 308" stroke="#3d3831" strokeWidth="6" strokeLinecap="round" />
          )}
        </g>
      </g>
    </svg>
  );
}
