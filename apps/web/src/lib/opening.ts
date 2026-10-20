/**
 * A sentence the learner already wrote as a request or a question goes as it
 * is; a bare subject ("Python") gets the one wrapper a person would use.
 */
const ALREADY_A_SENTENCE =
  /^(eu |i )?(quero|queria|gostaria|preciso|me ensin|ensina|como |o que|por que|porque|qual |want|i'd like|teach me|help me|how |what |why |which |quiero|necesito|ens[eé]ñame|c[oó]mo |qu[eé] |por qu[eé])/i;

export function openingLine(subject: string, wrap: (subject: string) => string): string {
  const text = subject.trim();
  return ALREADY_A_SENTENCE.test(text) ? text : wrap(text);
}
