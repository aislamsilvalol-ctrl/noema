/**
 * Cloze text, rendered for one side of a card — the client half of
 * `noema.engines.cloze`, same syntax, same blank.
 *
 * Cards made through `/cards/cloze` and (now) the Anki importer arrive
 * already rendered, so this is only for cards that were stored raw before
 * the importer learned to expand them: a review should never show
 * `{{c1::France}}` as the question with an empty answer. When the front has
 * deletions and the back is empty, the page renders both sides from the text.
 */

const PATTERN = /\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}/gs;
const BLANK = '[…]';

export function hasDeletions(text: string): boolean {
  return /\{\{c\d+::/.test(text);
}

/** Every deletion blanked (with its hint, if any). */
export function clozeFront(text: string): string {
  return text.replace(PATTERN, (_all, _n, _answer, hint: string | undefined) =>
    hint ? `${BLANK}(${hint})` : BLANK,
  );
}

/** Every deletion revealed. */
export function clozeBack(text: string): string {
  return text.replace(PATTERN, (_all, _n, answer: string) => answer);
}
