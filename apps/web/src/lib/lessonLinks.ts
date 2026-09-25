/**
 * Where a "Continue" goes. Every learning link names the lesson it opens:
 * a lesson by its id, a journey by the open lesson that belongs to it. When
 * no lesson matches, the link goes to the list of lessons — never to
 * whichever lesson happened to be newest, which is how "Continue Python"
 * used to land in Italian.
 */

import type { LessonSummary } from '@/lib/api';

export function lessonHref(sessionId: string): string {
  return `/chat?session=${encodeURIComponent(sessionId)}`;
}

export function journeyHref(journeyId: string, lessons: readonly LessonSummary[]): string {
  const lesson = lessons.find((item) => item.journey_id === journeyId);
  return lesson ? lessonHref(lesson.id) : '/chat';
}

/** A new lesson, not a resumed one. */
export const NEW_LESSON = '/chat?new=1';
