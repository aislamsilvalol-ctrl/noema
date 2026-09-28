/**
 * The one place a real, registered legal entity's identity would live.
 *
 * None of these values exist anywhere in this codebase today -- confirmed by
 * a broad grep across the whole repo (see NOEMA_WEB_READINESS_REPORT.md).
 * They are deliberately left `null`, not filled with a plausible-looking
 * placeholder: a fabricated company name or address on a real privacy/terms
 * page is worse than an honest gap, because nothing downstream would ever
 * flag it as fake.
 *
 * `stage` says which gap is acceptable. In `early-access` there is no company
 * yet, on purpose: the pages say so in plain words and point at the contact
 * channels that do exist (the in-app "Report a problem" dialog and the public
 * GitHub issues page). In `launched`, a missing identity field renders a
 * clearly-labelled "configuration required" notice, so a real launch cannot
 * ship a half-filled page.
 *
 * Fill the identity fields in and flip `stage` before general availability;
 * both legal pages already read from here.
 */
export type LegalStage = 'early-access' | 'launched';

export interface LegalConfig {
  stage: LegalStage;
  /** ISO date of the text currently published, not of the eventual launch. */
  lastUpdated: string;
  companyName: string | null;
  address: string | null;
  city: string | null;
  region: string | null;
  postalCode: string | null;
  country: string | null;
  contactEmail: string | null;
}

export const legalConfig: LegalConfig = {
  stage: 'early-access',
  lastUpdated: '2026-09-28',
  companyName: null,
  address: null,
  city: null,
  region: null,
  postalCode: null,
  country: null,
  contactEmail: null,
};

/** Where readers can actually reach us while there is no contact email. */
export const LEGAL_ISSUES_URL = 'https://github.com/aislamsilvalol-ctrl/noema/issues';

const IDENTITY_FIELDS = [
  'companyName',
  'address',
  'city',
  'region',
  'postalCode',
  'country',
  'contactEmail',
] as const;

export function legalConfigIsComplete(config: LegalConfig = legalConfig): boolean {
  return IDENTITY_FIELDS.every((field) => config[field] !== null);
}

/** True only when a launched deployment is missing part of its identity. */
export function legalConfigNeedsAttention(config: LegalConfig = legalConfig): boolean {
  return config.stage === 'launched' && !legalConfigIsComplete(config);
}
