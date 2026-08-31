// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useHeroTilt } from './useHeroTilt';

function mockMatchMedia({ hover, reducedMotion }: { hover: boolean; reducedMotion: boolean }) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('hover') ? hover : query.includes('prefers-reduced-motion') ? reducedMotion : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useHeroTilt', () => {
  it('is inactive on a touch device -- no hover, no fine pointer', () => {
    mockMatchMedia({ hover: false, reducedMotion: false });

    const { result } = renderHook(() => useHeroTilt());

    expect(result.current.active).toBe(false);
  });

  it('is inactive under prefers-reduced-motion even with a real cursor available', () => {
    mockMatchMedia({ hover: true, reducedMotion: true });

    const { result } = renderHook(() => useHeroTilt());

    expect(result.current.active).toBe(false);
  });

  it('is active on a real desktop pointer with no reduced-motion preference, and tracks the cursor', () => {
    mockMatchMedia({ hover: true, reducedMotion: false });

    const { result } = renderHook(() => useHeroTilt());
    expect(result.current.active).toBe(true);

    const node = document.createElement('div');
    document.body.appendChild(node);
    vi.spyOn(node, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
      right: 100,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON() {},
    });

    act(() => {
      result.current.containerRef(node);
    });

    act(() => {
      // Cursor at the far right edge -- clamps to the maximum rotation.
      node.dispatchEvent(new MouseEvent('mousemove', { clientX: 100, clientY: 50, bubbles: true }));
    });

    expect(result.current.style.transform).toContain('rotate(2.50deg)');

    act(() => {
      node.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }));
    });

    expect(result.current.style.transform).toBe('none');

    document.body.removeChild(node);
  });
});
