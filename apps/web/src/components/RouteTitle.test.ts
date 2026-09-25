import { describe, expect, it } from 'vitest';

import { titleFor } from './RouteTitle';
import { en } from '@/locales/en';
import { pt } from '@/locales/pt';

describe('titleFor', () => {
  it('names each screen in the reader language, with one suffix', () => {
    expect(titleFor('/today', en)).toBe('Today — NOEMA');
    expect(titleFor('/graph', pt)).toBe('Mapa do conhecimento — NOEMA');
  });

  it('tells a notebook tool from the notebook itself', () => {
    expect(titleFor('/notebooks/abc/cards', en)).toBe('Flashcards — NOEMA');
    expect(titleFor('/notebooks/abc/professor', pt)).toBe('Aula — NOEMA');
    expect(titleFor('/notebooks/abc', en)).toBe('Notes — NOEMA');
  });

  it('leaves routes with their own server metadata alone', () => {
    expect(titleFor('/', en)).toBeNull();
    expect(titleFor('/privacy', en)).toBeNull();
    expect(titleFor('/terms', en)).toBeNull();
  });
});
