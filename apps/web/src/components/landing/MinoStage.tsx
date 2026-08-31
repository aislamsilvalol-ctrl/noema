import { MINO_ASSETS, type MinoState } from '@/brand/mino';

/**
 * Renders one Mino state. Purely decorative -- the surrounding copy already
 * carries every fact a visitor or screen reader needs, so this is
 * `aria-hidden` rather than described, matching how the rest of the app
 * treats decorative imagery (`review/page.tsx`'s card image).
 *
 * A plain `<img>`, not `next/image`: these are local SVGs, and this repo has
 * no `images.dangerouslyAllowSVG` configured (SVGs can carry a script
 * payload, so Next disables them in its optimizer by default) -- adding
 * that flag for a placeholder asset isn't worth the security surface.
 *
 * `style` exists for `useHeroTilt`'s cursor transform -- an inline style
 * because it changes on every `mousemove`, and re-rendering a Tailwind class
 * name at that frequency would mean constant className-string churn for no
 * benefit `style` does not already give for free.
 */
export function MinoStage({
  state,
  className,
  style,
}: {
  state: MinoState;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={MINO_ASSETS[state]}
      alt=""
      aria-hidden="true"
      width={480}
      height={480}
      className={className}
      style={style}
    />
  );
}
