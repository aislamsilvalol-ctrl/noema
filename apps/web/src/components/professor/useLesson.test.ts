import { describe, expect, it } from 'vitest';

import { withMastery } from './useLesson';
import type { Journey } from '@/lib/api';

const journey = {
  id: 'j1',
  concepts: [
    { name: 'Photosynthesis', state: 'introduced', evidence: 1, misconceptions: [] },
    { name: 'Respiration', state: 'not_started', evidence: 0, misconceptions: [] },
  ],
} as unknown as Journey;

describe('withMastery', () => {
  it('updates the named concept in place, matching the name loosely', () => {
    const next = withMastery(journey, { concept: ' photosynthesis ', state: 'mastered', evidence: 4 });
    expect(next?.concepts[0]).toEqual({
      name: 'Photosynthesis',
      state: 'mastered',
      evidence: 4,
      misconceptions: [],
    });
    expect(next?.concepts[1]).toBe(journey.concepts[1]);
    expect(journey.concepts[0]?.state).toBe('introduced');
  });

  it('ignores a concept the journey never listed', () => {
    const next = withMastery(journey, { concept: 'Osmosis', state: 'learning', evidence: 1 });
    expect(next).toBe(journey);
    expect(withMastery(null, { concept: 'Osmosis', state: 'learning', evidence: 1 })).toBeNull();
  });
});
