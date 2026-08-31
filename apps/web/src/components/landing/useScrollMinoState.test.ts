// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useScrollMinoState, type MinoSection } from './useScrollMinoState';

const SECTIONS: MinoSection[] = [
  { id: 'hero', state: 'hero' },
  { id: 'pricing', state: 'pointing' },
];

class FakeIntersectionObserver implements IntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  callback: IntersectionObserverCallback;
  observed = new Set<Element>();
  root = null;
  rootMargin = '';
  thresholds: ReadonlyArray<number> = [];

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    FakeIntersectionObserver.instances.push(this);
  }

  observe(element: Element) {
    this.observed.add(element);
  }

  unobserve(element: Element) {
    this.observed.delete(element);
  }

  disconnect() {
    this.observed.clear();
  }

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  fire(target: Element, isIntersecting: boolean) {
    this.callback(
      [{ isIntersecting, target } as IntersectionObserverEntry],
      this,
    );
  }
}

function mockMatchMedia(reducedMotion: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? reducedMotion : false,
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
  FakeIntersectionObserver.instances = [];
});

describe('useScrollMinoState', () => {
  it('never creates an observer, and never leaves the first section state, under reduced motion', () => {
    mockMatchMedia(true);
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);

    const { result } = renderHook(() => useScrollMinoState(SECTIONS));

    expect(result.current.state).toBe('hero');
    expect(FakeIntersectionObserver.instances).toHaveLength(0);
  });

  it('updates state when a registered section intersects the viewport centre', () => {
    mockMatchMedia(false);
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);

    const { result } = renderHook(() => useScrollMinoState(SECTIONS));

    const pricing = document.createElement('section');
    act(() => {
      result.current.registerSection('pricing')(pricing);
    });

    expect(FakeIntersectionObserver.instances).toHaveLength(1);
    const observer = FakeIntersectionObserver.instances[0]!;
    expect(observer.observed.has(pricing)).toBe(true);
    expect(pricing.getAttribute('data-mino-section')).toBe('pricing');

    act(() => {
      observer.fire(pricing, true);
    });

    expect(result.current.state).toBe('pointing');
  });

  it('ignores an intersection entry for an element that was never registered', () => {
    mockMatchMedia(false);
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);

    const { result } = renderHook(() => useScrollMinoState(SECTIONS));
    const observer = FakeIntersectionObserver.instances[0]!;
    const stray = document.createElement('div');

    act(() => {
      observer.fire(stray, true);
    });

    expect(result.current.state).toBe('hero');
  });
});
