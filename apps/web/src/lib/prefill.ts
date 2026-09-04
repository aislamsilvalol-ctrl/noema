/**
 * Carrying a sentence from one screen into the Professor's composer.
 *
 * The landing hero, Home and the create-learning flow all end with "start
 * learning X". Rather than each screen inventing a query string, they leave
 * the text here (per tab, so it does not outlive the visit) and the Professor
 * picks it up once — consumed on read, so a second visit starts clean.
 *
 * `autosend` is the create-learning flow's case: the learner already said
 * what they want and how far along they are; making them press Send again
 * would be a form asking to be confirmed. Everything else only prefills.
 */

export const PREFILL_KEY = 'noema.chat.prefill';
export const AUTOSEND_KEY = 'noema.chat.autosend';

export function rememberPrefill(text: string, autosend = false): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  try {
    window.sessionStorage.setItem(PREFILL_KEY, trimmed);
    if (autosend) window.sessionStorage.setItem(AUTOSEND_KEY, '1');
    else window.sessionStorage.removeItem(AUTOSEND_KEY);
  } catch {
    // storage blocked: the Professor simply opens empty
  }
}

export function takePrefill(): { text: string; autosend: boolean } | null {
  try {
    const text = window.sessionStorage.getItem(PREFILL_KEY);
    if (!text) return null;
    const autosend = window.sessionStorage.getItem(AUTOSEND_KEY) === '1';
    window.sessionStorage.removeItem(PREFILL_KEY);
    window.sessionStorage.removeItem(AUTOSEND_KEY);
    return { text, autosend };
  } catch {
    return null;
  }
}
