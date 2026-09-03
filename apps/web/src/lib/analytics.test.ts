// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { track } from './analytics';

afterEach(() => {
  delete window.plausible;
});

describe('track', () => {
  it('calls window.plausible with the event name and props when it exists', () => {
    const plausible = vi.fn();
    window.plausible = plausible;

    track('cta_clicked', { location: 'hero' });

    expect(plausible).toHaveBeenCalledWith('cta_clicked', { props: { location: 'hero' } });
  });

  it('calls window.plausible with no options when there are no props', () => {
    const plausible = vi.fn();
    window.plausible = plausible;

    track('signup_started');

    expect(plausible).toHaveBeenCalledWith('signup_started', undefined);
  });

  it('is a silent no-op when Plausible never loaded', () => {
    expect(() => track('signup_completed')).not.toThrow();
  });
});
