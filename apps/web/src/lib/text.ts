/**
 * A sentence typed as a goal or a question, cut so it can stand as a title.
 *
 * Titles have a server-side limit and a list to fit on; a paragraph still
 * needs a name. The cut prefers a word boundary when one falls in the later
 * part of the allowance, so "…the French Rev…" does not happen when
 * "…the French…" would do; trailing punctuation goes so the ellipsis reads
 * as one mark.
 */
export function titleFrom(text: string, max = 72): string {
  const oneLine = text.replace(/\s+/g, ' ').trim();
  if (oneLine.length <= max) return oneLine;
  const cut = oneLine.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  const at = space > max * 0.55 ? space : cut.length;
  return `${cut.slice(0, at).replace(/[.,;:]$/, '')}…`;
}
