// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useActiveSection } from './useActiveSection';

type Callback = (entries: Partial<IntersectionObserverEntry>[]) => void;

function installObserver() {
  const observed: Element[] = [];
  let callback: Callback = () => undefined;
  class FakeObserver {
    constructor(cb: Callback) {
      callback = cb;
    }
    observe(element: Element) {
      observed.push(element);
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('IntersectionObserver', FakeObserver);
  return { observed, fire: (entries: Partial<IntersectionObserverEntry>[]) => callback(entries) };
}

afterEach(() => vi.unstubAllGlobals());

describe('useActiveSection', () => {
  it('starts on the first id and follows whichever registered section enters the centre band', () => {
    const { observed, fire } = installObserver();
    window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as unknown as typeof window.matchMedia;
    const { result } = renderHook(() => useActiveSection(['ask', 'learn', 'practice']));
    expect(result.current.active).toBe('ask');

    const learn = document.createElement('section');
    act(() => result.current.register('learn')(learn));
    expect(learn.getAttribute('data-section')).toBe('learn');
    expect(observed).toContain(learn);

    act(() => fire([{ isIntersecting: true, target: learn }]));
    expect(result.current.active).toBe('learn');

    act(() => fire([{ isIntersecting: false, target: learn }]));
    expect(result.current.active).toBe('learn');
  });

  it('never observes under reduced motion, so the first section stays', () => {
    const { observed } = installObserver();
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as unknown as typeof window.matchMedia;
    const { result } = renderHook(() => useActiveSection(['ask', 'learn']));
    const learn = document.createElement('section');
    act(() => result.current.register('learn')(learn));
    expect(observed).toHaveLength(0);
    expect(result.current.active).toBe('ask');
  });
});
