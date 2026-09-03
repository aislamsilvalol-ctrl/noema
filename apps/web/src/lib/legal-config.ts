/**
 * The one place a real, registered legal entity's identity would live.
 *
 * None of these values exist anywhere in this codebase today -- confirmed by
 * a broad grep across the whole repo (see NOEMA_WEB_READINESS_REPORT.md).
 * They are deliberately left `null`, not filled with a plausible-looking
 * placeholder: a fabricated company name or address on a real privacy/terms
 * page is worse than an honest gap, because nothing downstream would ever
 * flag it as fake. `/privacy` and `/terms` read this object and render a
 * clearly-labelled "configuration required" notice wherever a value is
 * missing, instead of silently omitting it or inventing one.
 *
 * Fill these in before launch, then this file's job is done -- nothing else
 * needs to change, both legal pages already read from here.
 */
export const legalConfig = {
  companyName: null as string | null,
  address: null as string | null,
  city: null as string | null,
  region: null as string | null,
  postalCode: null as string | null,
  country: null as string | null,
  contactEmail: null as string | null,
} as const;

export function legalConfigIsComplete(): boolean {
  return Object.values(legalConfig).every((value) => value !== null);
}
