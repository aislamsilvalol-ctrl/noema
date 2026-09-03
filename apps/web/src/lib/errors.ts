/**
 * What a learner is told when something fails.
 *
 * The API already wraps most failures in problem details with a slug, and the
 * backend abstracts provider errors behind `provider-unavailable`. This is the
 * last line: no matter what arrives — a provider's own sentence relayed through
 * an SSE `error` event, a network failure, a 5xx — the words on screen are
 * ours, in the learner's language, and say what to do next.
 *
 * The API's own sentence is kept only when it is *about the learner's data*:
 * validation ("Invalid email or password."), conflicts ("This file is already
 * in this notebook…"), import reports, quota messages written for people. Those
 * are written to be read. A model's 400 body is not.
 */

import { ApiError } from '@/lib/api';
import type { Dict } from '@/locales/en';

const ERROR_TYPE_PREFIX = 'https://noema.dev/errors/';

/** Slugs whose `detail` was written for a person and may be shown as-is. */
const HUMAN_DETAIL = new Set([
  'validation-failed',
  'unauthorized',
  'forbidden',
  'conflict',
  'not-found',
  'quota-exceeded',
  'rate-limited',
  'feature-unavailable',
  'unreadable-import',
]);

/** Slugs that mean "the AI could not answer" — never show the upstream text. */
const AI_SLUGS = new Set(['provider-unavailable', 'provider-error']);

export function slugOf(problemType: string | undefined): string {
  if (!problemType) return '';
  return problemType.startsWith(ERROR_TYPE_PREFIX)
    ? problemType.slice(ERROR_TYPE_PREFIX.length)
    : problemType;
}

/**
 * The sentence to show for `err`.
 *
 * `context` picks the fallback: 'ai' for anything a model was asked to do,
 * 'load' for reading the learner's own data, 'save' for writing it.
 */
export function humanError(
  err: unknown,
  t: Dict,
  context: 'ai' | 'load' | 'save' = 'load',
): string {
  const fallback =
    context === 'ai'
      ? t.errors.aiUnavailable
      : context === 'save'
        ? t.errors.couldNotSave
        : t.errors.couldNotLoad;

  if (err instanceof ApiError) {
    const slug = slugOf(err.problem.type);
    if (AI_SLUGS.has(slug)) return t.errors.aiUnavailable;
    if (HUMAN_DETAIL.has(slug) && err.problem.detail) return err.message;
    if (err.problem.status >= 500) return fallback;
    return err.message || fallback;
  }

  if (err instanceof TypeError) {
    // fetch rejects with a TypeError when the network is gone.
    return t.errors.offline;
  }

  return fallback;
}

/**
 * For SSE `error` events, which carry `{message, provider}` straight from the
 * stream. If a provider is named, the message is the provider's, not ours.
 */
export function humanStreamError(
  event: { message?: string; provider?: string | null },
  t: Dict,
): string {
  if (event.provider) return t.errors.aiUnavailable;
  return event.message || t.errors.aiUnavailable;
}
