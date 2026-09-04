/**
 * The Mino rig: one SVG, in layers, driven by a Pose.
 *
 * PROVISIONAL ART. No source renders of Mino exist in this repository or
 * anywhere reachable from it (see MINO_CHARACTER_SPEC.md, "Asset audit"), so
 * this drawing is authored from the written description of the character —
 * cream body, oversized round head, single curl, large glossy dark eyes,
 * small mouth, round hands, orange hoodie with the white mark. It is built as
 * the real rig will be built: separate layers for body, hoodie, mark, head,
 * curl, eyes (whites, pupils, highlights, lids), mouth and hands, each with
 * its own transform origin. When official art arrives, each layer's geometry
 * is replaced in place — the props, the origins and the controller stay.
 *
 * Nothing here animates by itself. Transforms are set from `pose`; the
 * smoothing between poses is CSS transitions (declared once, in
 * globals.css) plus the controller's springs for gaze and head. Under
 * reduced motion the transitions collapse and poses simply switch.
 */

import type { Pose } from '@/components/mino/machine';

const W = 480;

// Rig-space anchor points. Everything below is relative to these.
const HEAD = { cx: 240, cy: 205, r: 128 };
const EYE_L = { cx: 196, cy: 212 };
const EYE_R = { cx: 284, cy: 212 };
const EYE_R_PX = 21;
const PUPIL_TRAVEL = 9;
const MOUTH_Y = 262;

const MOUTH_PATHS: Record<Pose['mouth'], string> = {
  neutral: `M226 ${MOUTH_Y} Q240 ${MOUTH_Y + 6} 254 ${MOUTH_Y}`,
  smile: `M222 ${MOUTH_Y - 2} Q240 ${MOUTH_Y + 14} 258 ${MOUTH_Y - 2}`,
  open: `M228 ${MOUTH_Y - 2} Q240 ${MOUTH_Y + 18} 252 ${MOUTH_Y - 2} Z`,
  think: `M230 ${MOUTH_Y + 2} Q240 ${MOUTH_Y - 2} 250 ${MOUTH_Y + 3}`,
  o: `M240 ${MOUTH_Y - 6} a7 7 0 1 0 0.01 0 Z`,
  flat: `M229 ${MOUTH_Y + 1} L251 ${MOUTH_Y + 1}`,
};

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
  const headShift = pose.turn * 14;
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
        <radialGradient id="mino-skin" cx="42%" cy="34%" r="70%">
          <stop offset="0%" stopColor="#fbf6ec" />
          <stop offset="65%" stopColor="#efe6d6" />
          <stop offset="100%" stopColor="#d9ccb6" />
        </radialGradient>
        <radialGradient id="mino-hoodie" cx="40%" cy="30%" r="80%">
          <stop offset="0%" stopColor="#ff8f47" />
          <stop offset="60%" stopColor="#f26b1d" />
          <stop offset="100%" stopColor="#c9500f" />
        </radialGradient>
        <radialGradient id="mino-eye" cx="45%" cy="40%" r="60%">
          <stop offset="0%" stopColor="#2a2622" />
          <stop offset="100%" stopColor="#0f0d0b" />
        </radialGradient>
        <clipPath id="mino-eye-l">
          <circle cx={EYE_L.cx} cy={EYE_L.cy} r={EYE_R_PX} />
        </clipPath>
        <clipPath id="mino-eye-r">
          <circle cx={EYE_R.cx} cy={EYE_R.cy} r={EYE_R_PX} />
        </clipPath>
      </defs>

      {/* ground shadow: lifts with the figure */}
      <ellipse
        className="mino-layer mino-shadow"
        cx="240"
        cy="444"
        rx={112 + pose.lift * 2}
        ry="12"
        fill="#000"
        opacity={0.1 - pose.lift * 0.004}
      />

      <g className="mino-layer mino-figure-root" style={{ transform: `translateY(${pose.lift}px)` }}>
        {/* body + hoodie: leans a little, breathes via CSS */}
        <g
          className="mino-layer mino-body"
          style={{ transform: `translateX(${lean}px)`, transformOrigin: '240px 440px' }}
        >
          <path
            d="M240 300 C 302 300 330 336 330 386 C 330 428 300 446 240 446 C 180 446 150 428 150 386 C 150 336 178 300 240 300 Z"
            fill="url(#mino-hoodie)"
          />
          {/* hood collar */}
          <path
            d="M186 318 Q240 348 294 318 Q276 336 240 340 Q204 336 186 318 Z"
            fill="#c9500f"
            opacity="0.85"
          />
          {/* pocket */}
          <path d="M204 400 Q240 412 276 400 L272 424 Q240 432 208 424 Z" fill="#d9570f" opacity="0.6" />
          {/* the mark: a white ring with the orange centre — the placeholder's emblem, kept */}
          <g className="mino-layer mino-mark">
            <circle cx="240" cy="372" r="15" fill="#fbf8f3" />
            <circle cx="240" cy="372" r="5.5" fill="#f26b1d" />
          </g>
        </g>

        {/* hands: two round mitts on short arms, posed by name */}
        <g className={`mino-layer mino-hands mino-hands-${pose.hands}`}>
          <g className="mino-hand mino-hand-l" style={{ transformOrigin: '176px 372px' }}>
            <path d="M176 372 Q150 388 146 404" stroke="#f26b1d" strokeWidth="18" strokeLinecap="round" fill="none" />
            <circle cx="144" cy="408" r="16" fill="url(#mino-skin)" />
          </g>
          <g className="mino-hand mino-hand-r" style={{ transformOrigin: '304px 372px' }}>
            <path d="M304 372 Q330 388 334 404" stroke="#f26b1d" strokeWidth="18" strokeLinecap="round" fill="none" />
            <circle cx="336" cy="408" r="16" fill="url(#mino-skin)" />
          </g>
          {pose.hands === 'hold' && (
            <rect x="196" y="378" width="88" height="56" rx="6" fill="#fbf8f3" stroke="#e9e3da" strokeWidth="2" />
          )}
          {pose.hands === 'write' && (
            <path d="M318 372 L352 338" stroke="#3d3831" strokeWidth="6" strokeLinecap="round" />
          )}
        </g>

        {/* head: turns (translate) and tilts (rotate) around the neck */}
        <g
          className="mino-layer mino-head"
          style={{
            transform: `translateX(${headShift}px) rotate(${headTilt}deg)`,
            transformOrigin: '240px 320px',
          }}
        >
          <circle cx={HEAD.cx} cy={HEAD.cy} r={HEAD.r} fill="url(#mino-skin)" />
          {/* cheek warmth */}
          <ellipse cx="170" cy="252" rx="16" ry="9" fill="#f4b99a" opacity="0.35" />
          <ellipse cx="310" cy="252" rx="16" ry="9" fill="#f4b99a" opacity="0.35" />
          {/* curl */}
          <path
            className="mino-layer mino-curl"
            d="M232 84 C 226 60 252 48 268 60 C 284 72 270 92 254 88 C 262 78 252 68 244 74 C 238 78 240 86 248 88"
            fill="none"
            stroke="#d9ccb6"
            strokeWidth="9"
            strokeLinecap="round"
            style={{ transformOrigin: '240px 92px' }}
          />

          {/* eyes */}
          <g className="mino-layer mino-eyes">
            {[
              { c: EYE_L, clip: 'mino-eye-l' },
              { c: EYE_R, clip: 'mino-eye-r' },
            ].map(({ c, clip }) => (
              <g key={clip}>
                <circle cx={c.cx} cy={c.cy} r={EYE_R_PX} fill="url(#mino-eye)" />
                <g clipPath={`url(#${clip})`}>
                  {/* pupil highlight travels with gaze */}
                  <g style={{ transform: `translate(${px}px, ${py}px)` }} className="mino-gaze">
                    <circle cx={c.cx - 7} cy={c.cy - 8} r="6" fill="#fbf8f3" />
                    <circle cx={c.cx + 6} cy={c.cy + 7} r="2.5" fill="#fbf8f3" opacity="0.7" />
                  </g>
                  {/* upper lid: skin-coloured, scales down to blink; squint lifts the lower lid */}
                  <rect
                    className="mino-lid"
                    x={c.cx - EYE_R_PX - 2}
                    y={c.cy - EYE_R_PX - 2}
                    width={EYE_R_PX * 2 + 4}
                    height={EYE_R_PX * 2 + 4}
                    fill="#efe6d6"
                    style={{
                      transform: `scaleY(${lidScale})`,
                      transformOrigin: `${c.cx}px ${c.cy - EYE_R_PX - 2}px`,
                    }}
                  />
                  <ellipse
                    className="mino-lid-low"
                    cx={c.cx}
                    cy={c.cy + EYE_R_PX + 14}
                    rx={EYE_R_PX + 6}
                    ry={14}
                    fill="#efe6d6"
                    style={{
                      transform: `translateY(${-pose.squint * 14}px)`,
                    }}
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
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      </g>
    </svg>
  );
}
