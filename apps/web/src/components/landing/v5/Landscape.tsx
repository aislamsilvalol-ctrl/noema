/**
 * A NOEMA Landscape: one of the rendered scenes, full-bleed.
 *
 * The scenes are built in Blender with Mino physically in them and passed
 * through one post pipeline (docs/brand-os.md §8), so every one of them is
 * the same campaign. Served as AVIF/WebP at three widths with a JPEG
 * fallback; the hero's is fetched first, the rest lazily. The image is the
 * protagonist: the caller puts type on top, never a box.
 */

export type Scene = 'valley' | 'routes' | 'crest' | 'trail' | 'closeup' | 'horizon' | 'bleach';

const WIDTHS = [640, 1000, 1600] as const;
const SIZE = { width: 1600, height: 900 } as const;

function set(scene: Scene, format: 'avif' | 'webp'): string {
  return WIDTHS.map((w) => `/brand/landscapes/${scene}-${w}.${format} ${w}w`).join(', ');
}

export function Landscape({
  scene,
  priority = false,
  position = '50% 60%',
}: {
  scene: Scene;
  priority?: boolean;
  /** `object-position`: where the image anchors when the viewport crops it. */
  position?: string;
}) {
  return (
    <picture>
      <source type="image/avif" srcSet={set(scene, 'avif')} sizes="100vw" />
      <source type="image/webp" srcSet={set(scene, 'webp')} sizes="100vw" />
      {/* eslint-disable-next-line @next/next/no-img-element -- art-directed sources */}
      <img
        src={`/brand/landscapes/${scene}.jpg`}
        alt=""
        width={SIZE.width}
        height={SIZE.height}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : undefined}
        decoding={priority ? 'sync' : 'async'}
        draggable={false}
        style={{ objectPosition: position }}
      />
    </picture>
  );
}
