import { ImageResponse } from 'next/og';

/** Same placeholder mark as `icon.tsx`, at the size iOS expects for a
 * home-screen bookmark -- see that file's docstring for why it's a
 * letterform, not squeezed brand art. */
export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

export default function AppleIcon() {
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
          color: '#fbfaf9',
          fontSize: 108,
          fontWeight: 600,
        }}
      >
        N
      </div>
    ),
    { ...size },
  );
}
