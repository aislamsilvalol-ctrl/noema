import { describe, expect, it } from 'vitest';

import type { LessonSummary } from '@/lib/api';
import { journeyHref, lessonHref } from './lessonLinks';

function lesson(id: string, journey: string | null): LessonSummary {
  return {
    id,
    journey_id: journey,
    learning_goal: '',
    subject: '',
    current_topic: '',
    current_concept: '',
    turn_count: 1,
    last_turn_at: null,
    created_at: '2026-09-25T00:00:00Z',
  };
}

describe('lesson links', () => {
  it('opens a lesson by its id', () => {
    expect(lessonHref('abc')).toBe('/chat?session=abc');
  });

  it('continues a journey in its own lesson, never the newest one', () => {
    const lessons = [lesson('italian', 'j-italian'), lesson('python', 'j-python')];
    expect(journeyHref('j-python', lessons)).toBe('/chat?session=python');
  });

  it('falls back to the list of lessons when the journey has none open', () => {
    expect(journeyHref('j-calculus', [lesson('italian', 'j-italian')])).toBe('/chat');
  });
});
