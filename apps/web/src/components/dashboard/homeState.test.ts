import { describe, expect, it } from 'vitest';

import type { Journey, Mastery, NextActivity } from '@/lib/api';
import {
  dayPart,
  firstName,
  heroPlate,
  placeIn,
  plateFor,
  recommend,
  remembered,
  weakConcept,
} from './homeState';

const journey: Journey = {
  id: 'j-1',
  subject: 'Matemática',
  objective: '',
  level: 'beginner',
  status: 'active',
  session_id: null,
  focus_level: 0,
  checkpoints: 0,
  parked: [],
  current: { module: 1, lesson: 1, concept: 'Discriminante' },
  plan: [
    { title: 'Álgebra', status: 'done', lessons: [{ title: 'Expressões', status: 'done', concepts: [] }] },
    {
      title: 'Equações quadráticas',
      status: 'current',
      lessons: [
        { title: 'Forma geral', status: 'done', concepts: [] },
        { title: 'Bhaskara', status: 'current', concepts: [] },
        { title: 'Soma e produto', status: 'planned', concepts: [] },
      ],
    },
  ],
  concepts: [
    { name: 'Expressões', state: 'mastered', evidence: 6, misconceptions: [] },
    { name: 'Discriminante', state: 'learning', evidence: 2, misconceptions: [] },
    { name: 'Bhaskara', state: 'uncertain', evidence: 4, misconceptions: [] },
    { name: 'Forma geral', state: 'needs_review', evidence: 1, misconceptions: [] },
  ],
  memory: [],
  momentum: { events_today: 0, mastered_today: 0 },
};

function activity(over: Partial<NextActivity>): NextActivity {
  return {
    kind: 'learn',
    title: 'Matemática',
    concept: 'Discriminante',
    journey_id: 'j-1',
    session_id: 's-1',
    due_count: 0,
    overdue_count: 0,
    minutes_estimate: 10,
    reason_code: 'continue',
    reason: '',
    ...over,
  };
}

function score(name: string, mastery: number, observations: number): Mastery {
  return {
    concept_id: `c-${name}`,
    concept_name: name,
    mastery,
    provisional: false,
    last_evidence_at: null,
    source: 'graph',
    components: {
      calibration: 0,
      competence: 0,
      effective_observations: observations,
      prior_mean: 0,
      provisional: false,
      retrievability: 0,
      uncertainty: 0,
    },
  };
}

describe('dayPart', () => {
  it('splits the day where a greeting changes', () => {
    expect([4, 5, 11, 12, 17, 18, 22, 23].map(dayPart)).toEqual([
      'night',
      'morning',
      'morning',
      'afternoon',
      'afternoon',
      'evening',
      'evening',
      'night',
    ]);
  });
});

describe('heroPlate', () => {
  it('follows the learner, not chance', () => {
    expect(heroPlate({ firstDay: true, journey: null, next: null })).toBe('horizon');
    expect(heroPlate({ firstDay: false, journey, next: activity({}) })).toBe('trail');
    expect(heroPlate({ firstDay: false, journey: null, next: null })).toBe('terraces');
    expect(
      heroPlate({ firstDay: false, journey, next: activity({ kind: 'review', reason_code: 'overdue' }) }),
    ).toBe('valley');
  });

  it('brings Mino close on a day something was mastered', () => {
    const today = { ...journey, momentum: { events_today: 4, mastered_today: 1 } };
    expect(heroPlate({ firstDay: false, journey: today, next: activity({}) })).toBe('mino');
  });
});

describe('plateFor', () => {
  it('always gives a subject the same place, and never the hero close-up', () => {
    const subjects = ['História', 'Inglês', 'Python do zero', 'Filosofia estoica', 'Química'];
    for (const subject of subjects) {
      expect(plateFor(subject)).toBe(plateFor(subject));
      expect(plateFor(subject)).not.toBe('mino');
    }
  });
});

describe('placeIn', () => {
  it('says where the learner is once, with the counts behind the ring', () => {
    expect(placeIn(journey)).toEqual({
      module: 'Equações quadráticas',
      lesson: 'Bhaskara',
      concept: 'Discriminante',
      done: 2,
      total: 4,
      mastered: 1,
      concepts: 4,
    });
  });

  it('drops a title that only repeats the subject or the lesson', () => {
    const young: Journey = {
      ...journey,
      current: { module: 0, lesson: 0, concept: 'Matemática' },
      plan: [{ title: 'Matemática', status: 'current', lessons: [{ title: 'Matemática', status: 'current', concepts: [] }] }],
    };
    const place = placeIn(young);
    expect([place.module, place.lesson, place.concept]).toEqual([null, null, null]);
  });
});

describe('weakConcept', () => {
  it('trusts the graph only with enough evidence', () => {
    const scores = [score('Guess', 10, 2), score('Bhaskara', 41, 5), score('Fine', 90, 9)];
    expect(weakConcept(scores, journey)).toEqual({ name: 'Bhaskara', score: 41 });
  });

  it('falls back to the stage the lesson found shaky, most evidenced first', () => {
    expect(weakConcept([], journey)).toEqual({ name: 'Bhaskara', score: null });
    expect(weakConcept([], null)).toBeNull();
  });
});

describe('recommend', () => {
  const weak = { name: 'Bhaskara', score: null };

  it('puts the engine’s reviews first', () => {
    const next = activity({ kind: 'review', due_count: 6, overdue_count: 2, minutes_estimate: 4 });
    expect(recommend({ next, weak, due: 6, hasLesson: true })).toEqual({
      kind: 'review',
      due: 6,
      overdue: 2,
      minutes: 4,
    });
  });

  it('prefers a concept that went wrong to the continue the hero already offers', () => {
    expect(recommend({ next: activity({}), weak, due: 0, hasLesson: true })).toEqual({
      kind: 'weak',
      name: 'Bhaskara',
      score: null,
    });
  });

  it('then reviews due, then the engine’s continue, then a start', () => {
    expect(recommend({ next: activity({}), weak: null, due: 6, hasLesson: true })).toMatchObject({
      kind: 'review',
      due: 6,
      minutes: 3,
    });
    expect(recommend({ next: activity({}), weak: null, due: 0, hasLesson: true })).toEqual({
      kind: 'continue',
      concept: 'Discriminante',
      minutes: 10,
    });
    expect(recommend({ next: null, weak: null, due: 0, hasLesson: false })).toEqual({ kind: 'start' });
    expect(recommend({ next: null, weak: null, due: 0, hasLesson: true })).toBeNull();
  });
});

describe('remembered', () => {
  it('reads the newest memory fold: the agreed next step, else the last topic', () => {
    const fold = (summary: Record<string, unknown>) => ({
      ...journey,
      memory: [{ created_at: '', level: 'session', summary, turn_from: 1, turn_to: 2 }],
    });
    expect(remembered(fold({ next_step: ' three strips ', last_taught: 'P wave' }))).toEqual({ next: 'three strips' });
    expect(remembered(fold({ last_taught: 'P wave' }))).toEqual({ last: 'P wave' });
    expect(remembered(fold({}))).toBeNull();
    expect(remembered(null)).toBeNull();
  });
});

describe('firstName', () => {
  it('greets by first name, never by an address', () => {
    expect(firstName('Aislam Camarini')).toBe('Aislam');
    expect(firstName('  ')).toBe('');
    expect(firstName(null)).toBe('');
    expect(firstName('someone@example.com')).toBe('');
  });
});
