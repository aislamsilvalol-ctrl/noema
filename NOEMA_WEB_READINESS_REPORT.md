# NOEMA Web Readiness Report

Phase 1 (below) was a read-only audit. Everything after "## Implementation (same day)" is the
real follow-up work done against that audit's own findings — implemented, tested, and verified
against a real production build, not just planned.

---

## Implementation (same day)

| Item | Status | Notes |
|---|---|---|
| SEO metadata (root) | DONE | `layout.tsx`: `metadataBase`, title template (`%s — NOEMA`), OG, Twitter card, canonical |
| Per-page metadata | PARTIAL | `/login`, `/privacy`, `/terms` have real distinct titles; the ~13 authenticated app routes still inherit the root default (see robots.txt note below) |
| Open Graph image | DONE | `opengraph-image.tsx`, server-rendered via `next/og` from real brand tokens, not a generated asset |
| Favicon / apple-icon | DONE (placeholder art) | `icon.tsx`/`apple-icon.tsx`, a letterform mark in the real accent colour — no standalone icon mark exists in the brand yet, documented as placeholder the same way `MINO_ASSETS.md` documents Mino's own placeholders |
| `manifest.webmanifest` | DONE | name/icons/theme_color/background_color, `display: browser` (not a full PWA) |
| `robots.txt` | DONE | Allows `/`, `/privacy`, `/terms`; disallows every authenticated route |
| `sitemap.xml` | DONE | Public URLs only (`/`, `/privacy`, `/terms`) |
| Canonical URLs | DONE | Root + both legal pages |
| 404 page | DONE | `not-found.tsx`, on-brand (Mino "thinking" pose, subtle `animate-float`, respects `prefers-reduced-motion` via the existing global rule), auth-aware CTA, confirmed via a real production server that an unmatched route still returns **HTTP 404** (not 200) |
| Error boundary | DONE | `error.tsx` (segment-level, retry + home) and `global-error.tsx` (root-layout-level fallback, no i18n dependency by necessity) |
| Legal pages | DONE (structure + real practice description; entity identity blocked) | `/privacy`, `/terms` — real, product-specific content in Portuguese (see rationale below), reading company name/address/email from `legal-config.ts`. Every value there is `null` and the pages render a visible "configuration required before launch" notice until it's filled in — **nothing was invented** |
| Cookie consent | NOT BUILT, deliberately | Plausible sets no cookies and collects no personal data — under the standard GDPR/LGPD reading, a consent banner isn't required for it. Building one anyway would be exactly the item-117 overengineering the brief warns against for a mechanism with nothing to consent to |
| Analytics | DONE | Plausible, production-only (`RAILWAY_ENVIRONMENT_NAME === 'production'`, so local/preview never pollutes real numbers), plus a real, deliberately small event set: `cta_clicked` (header/hero/pricing, tagged by location), `signup_started`, `signup_completed`. Deeper in-app funnel events (`learning_path_created`, `subscription_started`) are out of this task's own stated scope (item 118) |
| Mobile responsiveness | ALREADY GOOD (§7 below) | No changes needed — confirmed real breakpoint-scoped Tailwind throughout the existing landing page |
| Sticky mobile CTA | NOT BUILT | Deliberately deferred: this repo's own environment has no working local browser to visually verify a sticky element doesn't cover the footer/cookie-adjacent content on a real small viewport (see `noema_no_local_browser.md`), and shipping a mis-positioned sticky CTA would be worse than the current already-above-the-fold hero CTA. Flagged as a real, named follow-up, not silently dropped |
| JSON-LD structured data | NOT BUILT | No fabricated ratings/review counts (confirmed correct per the brief's own concern), but no `Organization`/`WebSite` schema either — low priority, real follow-up |
| Per-route `noindex` beyond `/login` | NOT BUILT | The ~13 authenticated app routes rely on `robots.txt`'s Disallow list only, not individual `noindex` meta tags — a proportionate first pass per item 117 rather than 13 new boilerplate layout files, since every one of those routes requires real auth and shows a crawler nothing anyway |

**Why the legal pages are Portuguese-only, not the app's usual 3-locale i18n**: this session's own
pricing is in BRL and the brief itself used "CNPJ" as its own example of company info to look
for — both point at Brazil as the real jurisdiction. Machine-translating a legal document into
Spanish and English carries real accuracy risk a missing translation doesn't; writing one
correct version now and translating deliberately later (once a human reviews the legal content
company info fills in) is the more honest choice than three languages of unreviewed legal text.

**Verification performed, not just claimed**: `npm run build` (full production build, all new
routes — `/icon`, `/apple-icon`, `/opengraph-image`, `/manifest.webmanifest`, `/robots.txt`,
`/sitemap.xml`, `/privacy`, `/terms`, `/_not-found` — generated without error); `npx next start`
against the real production build, then curled every new route directly: `robots.txt`/
`sitemap.xml` content confirmed correct, `icon`/`opengraph-image` confirmed `image/png`,
`manifest.webmanifest` confirmed valid JSON, `/privacy`/`/terms` confirmed `200`, and — the one
the brief called out explicitly as a common failure (item 85) — a genuinely unmatched route
confirmed returning real **HTTP 404**, not a pretty page silently serving 200. 110 frontend
tests passing (was 103 before this pass), `tsc`/`next lint` clean.

---

## Phase 1 audit (original, unmodified below)

Read-only investigation, zero code changes, as instructed. Scope is the production-hardening
layer around the already-shipped landing page (Mino/scroll story from PR #126-131), not the
landing page's own content or design.

---

## 1. SEO metadata — PARTIAL (one generic entry, nothing per-route)

- Next.js's native metadata API is used, but only once, at the root:
  `apps/web/src/app/layout.tsx:42-46` — `export const metadata: Metadata = { title: 'NOEMA —
  Learn anything. Remember everything.', description: '...' }`.
- **No per-route metadata anywhere.** `grep -rn "export const metadata\|generateMetadata"
  apps/web/src/app` matches only that one line in `layout.tsx`. Every route (`/`, `/login`,
  `/chat`, `/settings`, etc.) inherits the exact same `<title>` and description — there is no
  `/pricing` route (pricing is a section inside `page.tsx`), and there are no `/privacy` or
  `/terms` routes to have metadata at all (see §5).
- `apps/web/src/app/page.tsx` is `'use client'` (line 1) and has no `generateMetadata` export of
  its own — it can't; metadata exports require a server component. So even the homepage's
  visible content (Mino story, pricing) is invisible to the metadata layer; only the root
  layout's static strings are indexed.
- **Open Graph: MISSING.** No `openGraph` key anywhere (`grep -rn "openGraph" apps/web/src` —
  no matches). No `og:title`/`og:description`/`og:image`/`og:type`/`og:url`/`og:site_name`.
- **OG image file: MISSING.** No file under `apps/web/public` matching an OG-image convention
  (`opengraph-image.*`), and no image asset built for this purpose. `apps/web/public/` contains
  only `brand/mino/*.svg` (the six Mino state illustrations used by `MinoStage.tsx`).
- **Twitter/X card tags: MISSING.** No `twitter` metadata key anywhere.
- **Canonical URL handling: MISSING.** No `alternates.canonical`, no `<link rel="canonical">`.
- **JSON-LD structured data: MISSING** (not merely absent-and-therefore-safe — worth stating
  since the brief specifically asked to check for fake ratings). `grep -rn "ld+json"
  apps/web/src` — no matches anywhere. No structured data of any kind exists, so there is no
  fabricated rating/review count to worry about, but also no legitimate `Organization`/
  `SoftwareApplication` markup.

## 2. robots.txt / sitemap.xml — MISSING (both)

- No `apps/web/src/app/robots.ts` or `sitemap.ts` (Next's file-convention route handlers).
- No static `apps/web/public/robots.txt` or `apps/web/public/sitemap.xml`.
- Confirmed via `find apps/web -iname "robots.txt" -o -iname "sitemap.xml"` (excluding
  `node_modules`/`.next`) — zero results. Nothing crawls-in, nothing blocks-out; there is no
  signal at all today for `/admin`, `/settings`, `/chat`, etc. being private vs. `/` and
  `/login` being public.

## 3. Favicon / manifest — MISSING (nothing present, nothing wired)

- `apps/web/public/` contains exactly one subtree: `brand/mino/*.svg` (six illustrations). No
  `favicon.ico`, no `favicon.svg`, no `apple-touch-icon.png`, no PNG icon set.
- No file-convention icons under `apps/web/src/app/` either (`icon.tsx`/`icon.png`,
  `apple-icon.png`) — `find apps/web/src/app -iname "icon*" -o -iname "favicon*" -o -iname
  "apple-icon*"` returns nothing.
- No `manifest.webmanifest` / `site.webmanifest` / `manifest.json` anywhere in the project
  (excluding build output).
- Nothing to "wire up" in `layout.tsx`'s `metadata.icons` because nothing exists — and indeed
  `metadata.icons` is not set (see `layout.tsx:42-46`, only `title`/`description` keys present).
  This means the site currently falls back to the browser/Next.js default favicon behavior —
  effectively no favicon at all in most browsers for a project with zero icon files.

## 4. 404 / error pages — MISSING (no custom 404, no error boundary at all)

- **`apps/web/src/app/not-found.tsx`: does not exist.** Confirmed with `find apps/web -iname
  "not-found*"` (excluding `node_modules`/`.next`) — zero results. An unmatched route today
  falls through to Next.js's built-in default not-found page (framework default styling, no
  Mino, no brand tokens) — it does still return a real HTTP 404 (that's Next's default routing
  behavior, not something this app configured), but the *page* itself is 100% unbranded.
- **`error.tsx` / `global-error.tsx`: both MISSING.** Same `find` sweep for
  `*global-error*`/`error.tsx` under `apps/web` (excluding build output) — zero results. There
  is no React error boundary anywhere in the App Router tree, so any client-render exception in
  `page.tsx`, `login/page.tsx`, etc. currently has no app-level catch — it will surface as
  Next's raw dev/prod error overlay or a blank screen, not a designed error state.
- No dedicated 500 treatment of any kind.

## 5. Legal pages — MISSING (no routes exist; no company/address info anywhere)

- **No `/privacy` or `/terms` route exists.** Full directory listing of `apps/web/src/app`
  shows only: `admin`, `api`, `chat`, `explain`, `goals`, `graph`, `library`, `login`,
  `mistakes`, `notebooks/[id]/{cards,exam,professor,quiz}`, `progress`, `review`, `settings`,
  `socratic`, `today`, plus the root `page.tsx`. No `privacy`, `terms`, or `legal` directory
  anywhere. There is therefore no placeholder/lorem-ipsum text to grade either — the pages are
  simply absent, not present-but-weak.
- **Company identity / physical address / CNPJ: none found anywhere in the repo.** Broad greps
  across `apps/web/src`, `apps/api/noema`, `.env.example`, and top-level docs
  (`README.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`) for CNPJ, "physical address", legal-entity
  suffixes (`Ltda`, `LLC`, `Inc.`, `S.A.`) and similar terms returned zero matches. There is no
  registered company name or mailing address on file in this codebase, full stop.
- **Contact emails that do exist** (both real, both currently living only in GitHub-facing docs,
  not the product):
  - `security@noema.dev` — `SECURITY.md:8` ("or email `security@noema.dev` (PGP key in
    `docs/security-pgp.asc`)").
  - `conduct@noema.dev` — `CODE_OF_CONDUCT.md:40` (community-conduct reports).
  - Neither address appears anywhere under `apps/web/src` or `apps/api/noema` — they exist only
    in root-level markdown docs aimed at contributors/researchers, not in any user-facing page
    or in `apps/api/noema/core/config.py`.
- Per the brief's explicit instruction: no placeholder legal values are suggested here — this
  section reports only what is/isn't present.

## 6. Cookie consent / analytics — MISSING (both; and they'd be mismatched if only one existed)

- **No analytics integration of any kind.** Grepped `apps/web/src` for Plausible, PostHog,
  gtag/Google Analytics, googletagmanager, Segment, Mixpanel, Vercel Analytics — all misses.
  `apps/web/package.json` has no dependency matching any of those names either. The only hits
  for the bare word "analytics" were unrelated: `apps/web/src/app/api/v1/[...path]/route.ts`,
  `apps/web/src/lib/api.ts`, `apps/web/src/lib/api-schema.ts` — these are the app's own
  learning-analytics API types/routes (progress tracking, etc.), not a third-party tracking SDK.
- **No cookie-consent banner component.** Grepped for `cookie.?consent`, "consent banner",
  `CookieBanner`, `useCookieConsent` across `apps/web/src` — zero matches.
- Net: nothing to reconcile — there is no analytics-without-consent gap and no
  consent-without-analytics gap; both are simply absent. Whichever gets built first, the other
  needs to ship alongside it.

## 7. Mobile responsiveness / sticky CTA — PARTIAL (landing page itself is responsive; no sticky mobile CTA exists)

- The memory note's earlier finding ("very sparse responsive/mobile CSS") does **not** describe
  the current landing page. `apps/web/src/app/page.tsx` uses real breakpoint-scoped Tailwind
  classes throughout: hero grid `md:grid-cols-[1.2fr_1fr] md:items-center md:pt-32` (line 101),
  heading `md:text-4xl` (line 104), Mino stage sizing `max-w-xs md:max-w-sm` (line 132), pillars
  grid `md:grid-cols-2 lg:grid-cols-3` (line 142), pricing grid `sm:grid-cols-2 lg:grid-cols-4`
  (line 163), nav gap `sm:gap-6` (line 85). This is a genuine mobile-first layout with explicit
  tablet/desktop overrides, not the single fixed-width layout the earlier note flagged.
- `MinoStage.tsx` (`apps/web/src/components/landing/MinoStage.tsx:34-35`) renders the mascot SVG
  with explicit `width={480} height={480}` but scales visually via the parent's responsive
  `className`, so it isn't a fixed-pixel layout trap on its own.
- **No sticky mobile CTA exists on the landing page or anywhere public-facing.** `grep -rn
  "sticky" apps/web/src` finds exactly two hits, both in authenticated in-app chat/tutor
  surfaces, not marketing: `apps/web/src/app/chat/page.tsx:156` and
  `apps/web/src/app/notebooks/[id]/professor/page.tsx:319,324` — both are the sticky message
  composer bar (`sticky bottom-24 ... md:bottom-0`), unrelated to a marketing "Start
  learning"-style persistent CTA. If the brief wants a persistent mobile signup/CTA affordance
  on `/`, it does not exist today.

## 8. Loading/error/success states for forms — EXISTS (login/signup form is solid)

There is exactly one public-facing form in the app: `apps/web/src/app/login/page.tsx` (combined
login/register). It has all four things the brief asks about:

- **Real loading state during submission**: `busy` state (`login/page.tsx:17,40,50`) flips true
  before the `api.login`/`api.register` call and false in a `finally` block
  (`login/page.tsx:37-53`); the submit button label switches to `t.login.working` while busy
  (`login/page.tsx:103`).
- **Disabled during submit (no double-submit)**: `disabled={busy}` on the submit button
  (`login/page.tsx:100`).
- **Field-level structure exists** via the shared `Field` component (`login/page.tsx:134-163`)
  with labeled inputs and `required`, but there is no *per-field* validation message (e.g. "this
  field is required" inline under a specific input) — only a single form-level error region.
- **Friendly (not raw HTTP status) error messages**: `catch (err) { setError(err instanceof
  ApiError ? err.message : t.common.somethingWrong) }` (`login/page.tsx:48-49`) — a recognized
  `ApiError` shows its message, anything else falls back to a translated generic string, so a
  raw `500 Internal Server Error` string is never shown verbatim (contingent on `ApiError`'s
  `.message` itself being friendly, which is outside this file — not verified here since that
  crosses into `apps/web/src/lib/api.ts`, out of this audit's read scope for this pass).
- No other public-facing forms (no contact form, no waitlist form) exist in `apps/web/src/app`.

## 9. Auth-aware CTA — EXISTS, confirmed accurate

Read directly from `apps/web/src/app/page.tsx` (not taken on memory's word):

- `signedIn` state starts `false` and is set `true` only on a successful `api.me()` resolution
  (`page.tsx:49, 64-72`).
- `const primaryHref = signedIn ? '/chat' : '/login';` and `const primaryLabel = signedIn ?
  t.landing.continueLearning : t.landing.start;` (`page.tsx:78-79`) — confirms the `/chat`
  redirect (not `/dashboard` or elsewhere) for signed-in visitors.
- Used consistently in three places: header nav CTA (`page.tsx:92-94`), hero primary CTA
  (`page.tsx:113-118`), and every pricing-card CTA (`page.tsx:173-178`) — so a signed-in visitor
  sees "Continue learning" pointed at `/chat` everywhere the CTA appears, not just in the hero.
  Memory note confirmed accurate.

## 10. noindex on private/auth routes — MISSING (no mechanism exists at all)

- No route has any `noindex` directive. `grep -rn "noindex" apps/web/src` — zero matches
  anywhere, including `/login`, `/admin`, `/settings`, `/chat`, `/today`, `/progress`, etc.
- Consistent with §2: since there is no `robots.txt`/`sitemap.xml` at all, there's also no
  sitemap-based inclusion/exclusion signal to fall back on — this isn't "absent from sitemap but
  otherwise fine," it's a complete absence of any indexing signal for any route, public or
  private. Every route (including `/admin`) is exposed to crawlers exactly the same way, with
  nothing currently telling a crawler to skip the private surface.

---

## Bottom line — items that read as real launch blockers under the brief's own definition

1. **No `/privacy` or `/terms` route exists at all** — not weak content, no route. If this is a
   paid SaaS collecting payment/AI-provider data, shipping without any legal page is a hard
   blocker, and there is no company name/address/CNPJ on file anywhere in the repo to put on one
   once it's written.
2. **No `robots.txt`/`sitemap.xml`/`noindex` mechanism of any kind** — `/admin` and `/settings`
   are exposed to crawlers identically to `/` and `/login`; nothing currently distinguishes
   public from private surface for search engines.
3. **Zero favicon/manifest files** — the site ships with no icon assets whatsoever, not even a
   default `favicon.ico`, and nothing in `layout.tsx` references icons.
4. **Zero OG/Twitter-card metadata and no OG image** — a shared link to the landing page today
   renders as a bare, generic browser bookmark card with no image, no per-page title.

Nothing found in this pass qualifies as **BROKEN** (e.g. a 404 route silently returning 200, or
plaintext secrets in a public file) — the pattern throughout is consistently **MISSING**
(mechanism absent) rather than present-but-malfunctioning. The one exception worth flagging as
partial-not-full-credit: the default Next.js not-found page does return a real 404 status, it is
just entirely unbranded.
