import { describe, expect, it } from 'vitest';
import { clozeBack, clozeFront, hasDeletions } from './cloze';

describe('cloze', () => {
  it('blanks every deletion on the front and reveals it on the back', () => {
    const text = 'The capital of {{c1::France}} is {{c2::Paris::city}}';
    expect(hasDeletions(text)).toBe(true);
    expect(clozeFront(text)).toBe('The capital of […] is […](city)');
    expect(clozeBack(text)).toBe('The capital of France is Paris');
  });

  it('leaves ordinary text alone', () => {
    expect(hasDeletions('house')).toBe(false);
    expect(clozeFront('house')).toBe('house');
  });
});
