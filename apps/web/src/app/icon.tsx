import { ImageResponse } from 'next/og';

/**
 * Placeholder favicon -- not final brand art. No standalone icon mark exists
 * for Noema yet (the shipped identity is a wordmark; see MINO_ASSETS.md for
 * the same "clearly-labelled placeholder, not final art" precedent this
 * follows). A single letterform in the real accent colour reads at 16px far
 * better than a squeezed full logo would, which is what the brief itself
 * asked for -- swap this file for real brand art when it exists, everything
 * that references it (browser tab, bookmarks, `manifest.ts`) picks it up
 * automatically via Next's file-convention icons, no other change needed.
 *
 * Hex values match `--accent`/`--ink-50` in globals.css -- hardcoded because
 * ImageResponse renders via Satori, not a browser, so it can't resolve a CSS
 * custom property.
 */
export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#b5450c',
          borderRadius: 7,
          color: '#fbfaf9',
          fontSize: 22,
          fontWeight: 600,
        }}
      >
        N
      </div>
    ),
    { ...size },
  );
}
