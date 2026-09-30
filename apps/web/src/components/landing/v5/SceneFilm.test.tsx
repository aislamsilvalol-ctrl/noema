// @vitest-environment jsdom
import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SceneFilm } from './SceneFilm';

function media(matches: Record<string, boolean>) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: Object.entries(matches).some(([key, on]) => on && query.includes(key)),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

class NoObserver {
  observe() {}
  disconnect() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SceneFilm', () => {
  it('shows the still and no film for reduced motion', () => {
    media({ 'prefers-reduced-motion': true });
    const { container } = render(<SceneFilm scene="valley" film={{ src: '/f/valley', mobile: true }} />);
    expect(container.querySelector('img')).not.toBeNull();
    expect(container.querySelector('video')).toBeNull();
  });

  it('plays the wide cut on a desktop, webm first', () => {
    media({});
    vi.stubGlobal('IntersectionObserver', NoObserver);
    const { container } = render(<SceneFilm scene="valley" film={{ src: '/f/valley', mobile: true }} />);
    const sources = [...container.querySelectorAll('video source')].map((s) => s.getAttribute('src'));
    expect(sources).toEqual(['/f/valley.webm', '/f/valley.mp4']);
    expect(container.querySelector('video')?.getAttribute('preload')).toBe('none');
  });

  it('plays the vertical cut on a portrait phone', () => {
    media({ 'max-width: 640px': true });
    vi.stubGlobal('IntersectionObserver', NoObserver);
    const { container } = render(<SceneFilm scene="trail" film={{ src: '/f/trail', mobile: true }} />);
    expect(container.querySelector('video source')?.getAttribute('src')).toBe('/f/trail-mobile.webm');
  });
});
