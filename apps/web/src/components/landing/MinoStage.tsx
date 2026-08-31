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
 */
export function MinoStage({ state, className }: { state: MinoState; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={MINO_ASSETS[state]} alt="" aria-hidden="true" width={480} height={480} className={className} />
  );
}
