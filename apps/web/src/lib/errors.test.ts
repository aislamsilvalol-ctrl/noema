import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api';
import { en } from '@/locales/en';
import { es } from '@/locales/es';
import { pt } from '@/locales/pt';
import { humanError, humanStreamError } from './errors';

function problem(slug: string, detail: string, status = 400) {
  return new ApiError({ type: `https://noema.dev/errors/${slug}`, title: 'x', status, detail });
}

describe('humanError', () => {
  it('says a known API sentence in the learner\'s language', () => {
    const err = problem('unauthorized', 'Invalid email or password.', 401);
    expect(humanError(err, pt)).toBe('E-mail ou senha incorretos.');
    expect(humanError(err, es)).toBe('Correo o contraseña incorrectos.');
    expect(humanError(err, en)).toBe('Wrong email or password.');
  });

  it('carries the numbers through', () => {
    const err = problem('validation-failed', 'PDF uploads are limited to 25 MB; this file is 31.2 MB.');
    expect(humanError(err, pt)).toBe('Esse arquivo é grande demais. O limite é 25 MB.');
  });

  it('never shows an unknown English sentence on a Portuguese screen', () => {
    const err = problem('not-found', 'MemorySummary not found', 404);
    expect(humanError(err, pt)).toBe('Isso não está mais aqui.');
    expect(humanError(err, en)).toBe('MemorySummary not found');
  });

  it('translates a quota message that arrives on the stream', () => {
    const message = 'The daily AI token budget is used up. It resets on a rolling 24-hour window.';
    expect(humanStreamError({ message }, pt)).toMatch(/^O orçamento de IA de hoje acabou/);
  });
});
