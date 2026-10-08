// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ATTRIBUTION_KEY, captureAttribution, readAttribution, track, trackOnce } from './analytics';

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

describe('trackOnce', () => {
  afterEach(() => window.sessionStorage.clear());

  it('sends an event once per tab session', () => {
    const plausible = vi.fn();
    window.plausible = plausible;

    trackOnce('subscription_started');
    trackOnce('subscription_started');

    expect(plausible).toHaveBeenCalledTimes(1);
  });
});

describe('signup attribution', () => {
  afterEach(() => window.localStorage.clear());

  it('keeps the four UTM tags of the first tagged visit, and nothing else', () => {
    captureAttribution('?utm_source=newsletter&utm_medium=email&utm_campaign=launch&utm_term=x&email=a@b.c');

    expect(readAttribution()).toEqual({
      utm_source: 'newsletter',
      utm_medium: 'email',
      utm_campaign: 'launch',
    });
  });

  it('lets the first touch win over a later tagged visit', () => {
    captureAttribution('?utm_source=instagram');
    captureAttribution('?utm_source=google');

    expect(readAttribution()).toEqual({ utm_source: 'instagram' });
  });

  it('keeps nothing from an untagged visit and cuts long values', () => {
    captureAttribution('?ref=x');
    expect(readAttribution()).toBeNull();

    captureAttribution(`?utm_content=${'y'.repeat(300)}`);
    expect(readAttribution()?.utm_content).toHaveLength(100);
  });

  it('ignores a stored value that is not what it wrote', () => {
    window.localStorage.setItem(ATTRIBUTION_KEY, '{"utm_source": 5, "email": "a@b.c"}');
    expect(readAttribution()).toBeNull();
  });
});
