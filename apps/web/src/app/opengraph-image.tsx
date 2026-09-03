import { ImageResponse } from 'next/og';
import { siteConfig } from '@/lib/site-config';

/**
 * Server-rendered from real brand tokens, not a generated image asset -- no
 * image-generation credit spent, and it stays a real diff instead of a
 * binary. Deliberately typographic: the vendored fonts are woff2 (Satori,
 * ImageResponse's renderer, needs ttf/otf), so this uses the system default
 * rather than pulling in a font-conversion step for one image.
 *
 * A social card reads better dark -- this deliberately uses the *dark-mode*
 * token values from globals.css (`#17140f` background, `#f0954d` accent,
 * `#f7f4ef` text) as a fixed, single-theme card, not a mix-up of light/dark.
 */
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '80px',
          background: '#17140f',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <div
            style={{
              display: 'flex',
              width: 56,
              height: 56,
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 12,
              background: '#f0954d',
              color: '#17140f',
              fontSize: 32,
              fontWeight: 700,
            }}
          >
            N
          </div>
          <div style={{ display: 'flex', fontSize: 40, color: '#f7f4ef', fontWeight: 600 }}>
            {siteConfig.name}
          </div>
        </div>

        <div style={{ display: 'flex', marginTop: 56, fontSize: 56, color: '#f7f4ef' }}>
          {siteConfig.tagline}
        </div>
      </div>
    ),
    { ...size },
  );
}
