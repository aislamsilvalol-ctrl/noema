import { describe, expect, it } from 'vitest';

import { math } from './LearningBlocks';

describe('math', () => {
  it('writes powers as superscripts', () => {
    expect(math('f(x) = x^5')).toBe('f(x) = x⁵');
    expect(math('5x^4')).toBe('5x⁴');
    expect(math('x^(-2) + x^10')).toBe('x⁻² + x¹⁰');
  });

  it('leaves text without powers alone', () => {
    expect(math('Qual é a capital?')).toBe('Qual é a capital?');
  });
});
