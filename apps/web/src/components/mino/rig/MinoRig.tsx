/**
 * The Mino rig: one SVG, in layers, driven by a Pose.
 *
 * Drawn from the reference renders (the @noemalearn posts, see
 * MINO_CHARACTER_SPEC.md "Reference"): one continuous soft body, wide at the
 * base and narrowing to a rounded top with a single small curl pointing
 * back-right; very large, tall, glossy black eyes with two highlights; a tiny
 * low mouth; a faint blush; short rounded arms and stubby feet in the body
 * colour; the orange hoodie over the lower body with the white mark on the
 * chest. Cream, black, orange, white — nothing else.
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

// Rig-space anchors. The face sits in the upper half of one body shape.
const EYE_L = { cx: 200, cy: 222 };
const EYE_R = { cx: 280, cy: 222 };
const EYE_RX = 20;
const EYE_RY = 27;
const PUPIL_TRAVEL = 8;
const MOUTH_Y = 286;

const MOUTH_PATHS: Record<Pose['mouth'], string> = {
  neutral: `M231 ${MOUTH_Y} Q240 ${MOUTH_Y + 5} 249 ${MOUTH_Y}`,
  smile: `M226 ${MOUTH_Y - 2} Q240 ${MOUTH_Y + 12} 254 ${MOUTH_Y - 2}`,
  open: `M231 ${MOUTH_Y - 3} Q240 ${MOUTH_Y + 14} 249 ${MOUTH_Y - 3} Z`,
  think: `M233 ${MOUTH_Y + 2} Q240 ${MOUTH_Y - 1} 248 ${MOUTH_Y + 3}`,
  o: `M240 ${MOUTH_Y - 5} a5.5 5.5 0 1 0 0.01 0 Z`,
  flat: `M232 ${MOUTH_Y + 1} L248 ${MOUTH_Y + 1}`,
};

// The body: a single closed path — droplet, not a ball on an egg.
const BODY =
  'M240 62 ' +
  'C 292 62 352 128 352 246 ' + // right side, widening down
  'C 352 330 318 382 268 402 ' +
  'C 256 407 224 407 212 402 ' +
  'C 162 382 128 330 128 246 ' +
  'C 128 128 188 62 240 62 Z';

// The hoodie covers the lower body; its collar dips at the front.
const HOODIE =
  'M134 262 ' +
  'C 150 246 200 240 240 246 ' +
  'C 280 240 330 246 346 262 ' +
  'C 350 332 316 386 268 404 ' +
  'C 256 409 224 409 212 404 ' +
  'C 164 386 130 332 134 262 Z';

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
        <radialGradient id="mino-skin" cx="40%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#fdf9f1" />
          <stop offset="60%" stopColor="#f1e9da" />
          <stop offset="100%" stopColor="#d8ccb7" />
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
        cy="440"
        rx={98 + pose.lift * 2}
        ry="10"
        fill="#000"
        opacity={0.1 - pose.lift * 0.004}
      />

      <g className="mino-layer mino-figure-root" style={{ transform: `translateY(${pose.lift}px)` }}>
        {/* feet: stubby, body-coloured, under the hoodie's hem */}
        <g className="mino-layer mino-feet">
          <ellipse cx="208" cy="426" rx="26" ry="13" fill="url(#mino-skin)" />
          <ellipse cx="272" cy="426" rx="26" ry="13" fill="url(#mino-skin)" />
        </g>

        {/* body + hoodie: the head is the top of the same shape; the whole
            figure turns and tilts around the base */}
        <g
          className="mino-layer mino-head"
          style={{
            transform: `translateX(${headShift + lean}px) rotate(${headTilt}deg)`,
            transformOrigin: '240px 400px',
          }}
        >
          <g className="mino-layer mino-body" style={{ transformOrigin: '240px 404px' }}>
            <path d={BODY} fill="url(#mino-skin)" />
            {/* the curl: a short stroke that lifts off the crown, back-right */}
            <path
              className="mino-layer mino-curl"
              d="M244 66 C 250 44 272 40 282 54 C 288 63 280 74 270 72 C 276 62 266 54 258 60 C 252 64 252 70 258 74"
              fill="none"
              stroke="#e7dccb"
              strokeWidth="9"
              strokeLinecap="round"
              style={{ transformOrigin: '246px 70px' }}
            />
            <path d={HOODIE} fill="url(#mino-hoodie)" />
            {/* collar shadow */}
            <path
              d="M150 262 C 180 250 210 246 240 250 C 270 246 300 250 330 262 C 300 258 270 258 240 262 C 210 258 180 258 150 262 Z"
              fill="#b8460c"
              opacity="0.55"
            />
            {/* pocket seam */}
            <path d="M206 372 Q240 384 274 372" stroke="#c9500f" strokeWidth="3" fill="none" opacity="0.5" />
            {/* the mark on the chest: three white lobes */}
            <g className="mino-layer mino-mark" opacity="0.96">
              <circle cx="232" cy="312" r="8" fill="#fbf8f3" />
              <circle cx="249" cy="308" r="8" fill="#fbf8f3" />
              <circle cx="242" cy="325" r="8" fill="#fbf8f3" />
            </g>
          </g>

          {/* cheeks */}
          <ellipse cx="176" cy="262" rx="14" ry="8" fill="#f2b090" opacity="0.4" />
          <ellipse cx="304" cy="262" rx="14" ry="8" fill="#f2b090" opacity="0.4" />

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
                    <ellipse cx={c.cx - 7} cy={c.cy - 11} rx="6" ry="7" fill="#fbf8f3" />
                    <circle cx={c.cx + 6} cy={c.cy + 10} r="2.6" fill="#fbf8f3" opacity="0.75" />
                  </g>
                  {/* upper lid: body-coloured, scales down to blink */}
                  <rect
                    className="mino-lid"
                    x={c.cx - EYE_RX - 2}
                    y={c.cy - EYE_RY - 2}
                    width={EYE_RX * 2 + 4}
                    height={EYE_RY * 2 + 4}
                    fill="#f1e9da"
                    style={{
                      transform: `scaleY(${lidScale})`,
                      transformOrigin: `${c.cx}px ${c.cy - EYE_RY - 2}px`,
                    }}
                  />
                  {/* lower lid: rises with a squint (happy eyes) */}
                  <ellipse
                    className="mino-lid-low"
                    cx={c.cx}
                    cy={c.cy + EYE_RY + 16}
                    rx={EYE_RX + 6}
                    ry={16}
                    fill="#f1e9da"
                    style={{ transform: `translateY(${-pose.squint * 16}px)` }}
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
          <g className="mino-hand mino-hand-l" style={{ transformOrigin: '150px 318px' }}>
            <path d="M150 318 Q126 336 122 356" stroke="#f26b1d" strokeWidth="20" strokeLinecap="round" fill="none" />
            <circle cx="120" cy="362" r="15" fill="url(#mino-skin)" />
          </g>
          <g className="mino-hand mino-hand-r" style={{ transformOrigin: '330px 318px' }}>
            <path d="M330 318 Q354 336 358 356" stroke="#f26b1d" strokeWidth="20" strokeLinecap="round" fill="none" />
            <circle cx="360" cy="362" r="15" fill="url(#mino-skin)" />
          </g>
          {pose.hands === 'hold' && (
            <rect x="196" y="330" width="88" height="56" rx="6" fill="#fbf8f3" stroke="#e9e3da" strokeWidth="2" />
          )}
          {pose.hands === 'write' && (
            <path d="M344 326 L376 292" stroke="#3d3831" strokeWidth="6" strokeLinecap="round" />
          )}
        </g>
      </g>
    </svg>
  );
}
