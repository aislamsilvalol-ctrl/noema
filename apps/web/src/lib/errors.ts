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
 *
 * The API writes those sentences in English. The ones a learner meets are
 * recognised here and said in their language (`KNOWN`); anything else under a
 * human slug is shown as-is only in English, and replaced by the slug's own
 * sentence otherwise. A Portuguese screen never shows "Session expired."
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

type Known = Dict['errors']['known'];

/** API sentences a learner can meet, matched loosely so a reworded tail still lands. */
const KNOWN: [RegExp, (k: Known, match: RegExpMatchArray) => string][] = [
  [/^Invalid email or password/i, (k) => k.wrongLogin],
  [/^(Session (expired|revoked)|Invalid session|No session|Not authenticated)/i, (k) => k.sessionEnded],
  [/^Registration is disabled/i, (k) => k.signupsClosed],
  [/^An account with that email already exists/i, (k) => k.emailTaken],
  [/uploads are limited to (\d+(?:\.\d+)?) MB/i, (k, m) => k.tooLarge(m[1] ?? '')],
  [/^No text could be extracted/i, (k) => k.noText],
  [/^Delete this \w+'s \w+ first/i, (k) => k.notEmpty],
  [/^This sign-in expired/i, (k) => k.signInExpired],
  [/^That code is not right/i, (k) => k.wrongCode],
  [/^That lesson has ended/i, (k) => k.lessonEnded],
  [/already (been )?handed in/i, (k) => k.handedIn],
  [/^This reset link is invalid/i, (k) => k.resetLinkInvalid],
  [/^Could not send email/i, (k) => k.emailNotSent],
  [/^Your account is closed/i, (k) => k.accountClosed],
  [/daily AI token budget/i, (k) => k.dailyBudget],
  [/exceed your (\d+(?:\.\d+)?) MB storage/i, (k, m) => k.storageFull(m[1] ?? '')],
];

/**
 * An API sentence in the learner's language: a known one translated, an
 * unknown one kept in English, replaced by `fallback` elsewhere.
 */
export function humanDetail(detail: string, t: Dict, fallback: string): string {
  for (const [pattern, say] of KNOWN) {
    const match = detail.match(pattern);
    if (match) return say(t.errors.known, match);
  }
  return t.errors.apiLanguage ? detail : fallback;
}

/** Slugs that mean "the AI could not answer" — never show the upstream text. */
const AI_SLUGS = new Set(['provider-unavailable', 'provider-error', 'ai-timeout']);

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
    if (HUMAN_DETAIL.has(slug) && err.problem.detail) {
      return humanDetail(err.message, t, t.errors.bySlug[slug] ?? fallback);
    }
    if (err.problem.status >= 500) return fallback;
    return err.message ? humanDetail(err.message, t, t.errors.bySlug[slug] ?? fallback) : fallback;
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
  event: { message?: string; provider?: string | null; retryable?: boolean },
  t: Dict,
): string {
  // `retryable: false` means every configured provider refused for a reason
  // waiting will not change (a key, a balance, a malformed request). Telling
  // the learner to try again in a moment would be a promise nobody keeps.
  if (event.retryable === false) return t.errors.aiDown;
  // Upstream text can name the deployment's own billing state or its keys.
  if (event.provider) return t.errors.aiUnavailable;
  return event.message ? humanDetail(event.message, t, t.errors.aiUnavailable) : t.errors.aiUnavailable;
}

/** A step-up password that did not match — told apart from any other 403. */
export function passwordError(err: unknown, wrong: string, fallback: string): string {
  return err instanceof ApiError && err.problem.type?.endsWith('/wrong-password') ? wrong : fallback;
}
