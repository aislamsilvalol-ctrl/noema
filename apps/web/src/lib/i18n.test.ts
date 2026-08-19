import { afterEach, describe, expect, it, vi } from 'vitest';

import { detectLocale } from '@/lib/i18n';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('detectLocale', () => {
  it('falls back to English when navigator does not exist', () => {
    vi.stubGlobal('navigator', undefined);

    expect(detectLocale()).toBe('en');
  });

  it('picks the first served language in the browser\'s own preference order', () => {
    vi.stubGlobal('navigator', { languages: ['fr-FR', 'pt-BR', 'en-US'] });

    expect(detectLocale()).toBe('pt');
  });

  it('falls back to English when nothing in the list is served', () => {
    vi.stubGlobal('navigator', { languages: ['fr-FR', 'de-DE'] });

    expect(detectLocale()).toBe('en');
  });

  it('reads navigator.language when languages is absent', () => {
    vi.stubGlobal('navigator', { language: 'es-ES' });

    expect(detectLocale()).toBe('es');
  });

  it('matches the language tag case-insensitively', () => {
    vi.stubGlobal('navigator', { languages: ['PT-BR'] });

    expect(detectLocale()).toBe('pt');
  });
});
