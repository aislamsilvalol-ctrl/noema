/**
 * The Mino rig: one SVG, in layers, driven by a Pose.
 *
 * Drawn from the reference renders (the @noemalearn posts, see
 * MINO_CHARACTER_SPEC.md "Reference"): a big, domed, rounded head that flows
 * into a shorter, chubby body with only a soft waist between them — a
 * marshmallow, not an egg and not a ball on a body; a single small curl on
 * the crown, leaning right; very large, tall, glossy black eyes wide apart
 * with two highlights; a tiny low mouth; a faint blush; short rounded arms
 * and stubby feet in the body colour; the orange hoodie from the waist down
 * with the white three-lobed mark on the chest. Cream, black, orange, white —
 * nothing else.
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
const EYE_L = { cx: 196, cy: 200 };
const EYE_R = { cx: 284, cy: 200 };
const EYE_RX = 25;
const EYE_RY = 33;
const PUPIL_TRAVEL = 8;
const MOUTH_Y = 262;

const MOUTH_PATHS: Record<Pose['mouth'], string> = {
  neutral: `M230 ${MOUTH_Y} Q240 ${MOUTH_Y + 6} 250 ${MOUTH_Y}`,
  smile: `M224 ${MOUTH_Y - 2} Q240 ${MOUTH_Y + 13} 256 ${MOUTH_Y - 2}`,
  open: `M230 ${MOUTH_Y - 3} Q240 ${MOUTH_Y + 15} 250 ${MOUTH_Y - 3} Z`,
  think: `M232 ${MOUTH_Y + 2} Q240 ${MOUTH_Y - 1} 248 ${MOUTH_Y + 3}`,
  o: `M240 ${MOUTH_Y - 5} a5.5 5.5 0 1 0 0.01 0 Z`,
  flat: `M231 ${MOUTH_Y + 1} L249 ${MOUTH_Y + 1}`,
};

// The body: one closed path. A wide, domed head (widest a little above the
// eyes), a soft inward curve where a neck would be, then a shorter, rounder
// body that the hoodie covers. The top is flattened, not pointed.
const BODY =
  'M240 66 ' +
  'C 316 66 366 122 366 198 ' + // head, right
  'C 366 250 346 282 322 300 ' + // cheek down to the waist
  'C 348 322 356 358 350 388 ' + // hip, right
  'C 344 416 300 428 240 428 ' +
  'C 180 428 136 416 130 388 ' + // hip, left
  'C 124 358 132 322 158 300 ' +
  'C 134 282 114 250 114 198 ' + // head, left
  'C 114 122 164 66 240 66 Z';

// The hoodie: from the waist down, collar dipping at the front.
const HOODIE =
  'M158 300 ' +
  'C 186 288 214 284 240 292 ' +
  'C 266 284 294 288 322 300 ' +
  'C 348 322 356 358 350 388 ' +
  'C 344 416 300 428 240 428 ' +
  'C 180 428 136 416 130 388 ' +
  'C 124 358 132 322 158 300 Z';

export function MinoRig({
  pose,
  blink = 0,
  className = '',
  style,
}: {
  pose: Pose;
  /** 0 open … 1 shut; layered over `pose.eyes` by the controller. */
  blink?: number;
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
      viewBox={`0 0 ${W} ${W}`}
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
        cy="446"
        rx={104 + pose.lift * 2}
        ry="10"
        fill="#000"
        opacity={0.1 - pose.lift * 0.004}
      />

      <g className="mino-layer mino-figure-root" style={{ transform: `translateY(${pose.lift}px)` }}>
        {/* feet: stubby, body-coloured, under the hoodie's hem */}
        <g className="mino-layer mino-feet">
          <ellipse cx="206" cy="434" rx="28" ry="12" fill="url(#mino-skin)" />
          <ellipse cx="274" cy="434" rx="28" ry="12" fill="url(#mino-skin)" />
        </g>

        {/* head + body are one shape; the whole figure turns and tilts
            around its base */}
        <g
          className="mino-layer mino-head"
          style={{
            transform: `translateX(${headShift + lean}px) rotate(${headTilt}deg)`,
            transformOrigin: '240px 420px',
          }}
        >
          <g className="mino-layer mino-body" style={{ transformOrigin: '240px 428px' }}>
            <path d={BODY} fill="url(#mino-skin)" />
            {/* the tip: one short teardrop on the crown, leaning right, as in the
                reference — not a spiral */}
            <path
              className="mino-layer mino-curl"
              d="M232 72 C 234 54 246 40 262 38 C 272 37 278 46 272 54 C 266 62 254 66 248 74 Z"
              fill="url(#mino-skin)"
              stroke="#e4d9c7"
              strokeWidth="2"
              strokeLinejoin="round"
              style={{ transformOrigin: '244px 72px' }}
            />
            <path d={HOODIE} fill="url(#mino-hoodie)" />
            {/* collar shadow */}
            <path
              d="M158 300 C 186 288 214 284 240 292 C 266 284 294 288 322 300 C 294 300 266 298 240 304 C 214 298 186 300 158 300 Z"
              fill="#b8460c"
              opacity="0.55"
            />
            {/* pocket seam */}
            <path d="M204 396 Q240 408 276 396" stroke="#c9500f" strokeWidth="3" fill="none" opacity="0.5" />
            {/* the mark on the chest: three white lobes */}
            <g className="mino-layer mino-mark" opacity="0.96">
              <circle cx="231" cy="346" r="8" fill="#fbf8f3" />
              <circle cx="249" cy="342" r="8" fill="#fbf8f3" />
              <circle cx="242" cy="359" r="8" fill="#fbf8f3" />
            </g>
          </g>

          {/* cheeks */}
          <ellipse cx="164" cy="246" rx="15" ry="9" fill="#f2b090" opacity="0.38" />
          <ellipse cx="316" cy="246" rx="15" ry="9" fill="#f2b090" opacity="0.38" />

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
                  {/* upper lid: body-coloured, scales down to blink */}
                  <rect
                    className="mino-lid"
                    x={c.cx - EYE_RX - 2}
                    y={c.cy - EYE_RY - 2}
                    width={EYE_RX * 2 + 4}
                    height={EYE_RY * 2 + 4}
                    fill="#f2eadc"
                    style={{
                      transform: `scaleY(${lidScale})`,
                      transformOrigin: `${c.cx}px ${c.cy - EYE_RY - 2}px`,
                    }}
                  />
                  {/* lower lid: rises with a squint (happy eyes) */}
                  <ellipse
                    className="mino-lid-low"
                    cx={c.cx}
                    cy={c.cy + EYE_RY + 17}
                    rx={EYE_RX + 6}
                    ry={17}
                    fill="#f2eadc"
                    style={{ transform: `translateY(${-pose.squint * 17}px)` }}
                  />
                </g>
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
          <g className="mino-hand mino-hand-l" style={{ transformOrigin: '146px 340px' }}>
            <path d="M146 340 Q118 356 112 378" stroke="#f26b1d" strokeWidth="22" strokeLinecap="round" fill="none" />
            <circle cx="110" cy="384" r="16" fill="url(#mino-skin)" />
          </g>
          <g className="mino-hand mino-hand-r" style={{ transformOrigin: '334px 340px' }}>
            <path d="M334 340 Q362 356 368 378" stroke="#f26b1d" strokeWidth="22" strokeLinecap="round" fill="none" />
            <circle cx="370" cy="384" r="16" fill="url(#mino-skin)" />
          </g>
          {pose.hands === 'hold' && (
            <rect x="196" y="352" width="88" height="56" rx="6" fill="#fbf8f3" stroke="#e9e3da" strokeWidth="2" />
          )}
          {pose.hands === 'write' && (
            <path d="M354 350 L386 316" stroke="#3d3831" strokeWidth="6" strokeLinecap="round" />
          )}
        </g>
      </g>
    </svg>
  );
}
