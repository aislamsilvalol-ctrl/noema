# Mino asset guide

Mino is NOEMA's learning companion, shown on the marketing landing page
(`apps/web/src/app/page.tsx`, via `apps/web/src/components/landing/MinoStage.tsx`).
The files in `apps/web/public/brand/mino/` today are **placeholders** — a
hand-drawn stand-in with real pose/expression per state (a held book while
reading, an arm to the chin while thinking, a pencil and flashcard while
studying, an extended arm while pointing, raised arms while celebrating),
not draft character art from an actual character designer. Replace them
with official art by dropping in files of the same name; nothing else
needs to change.

The AI-generated route (a Higgsfield character-sheet render, closer to the
"3D creature" the original brief describes) was tried first and blocked —
the workspace had no image-generation credits at the time. If that's since
been topped up, generating a proper reference render and re-deriving all
six poses from it is still the better long-term placeholder than these
hand-drawn SVGs; ask before assuming the credits situation is unchanged.

## Brand colour (confirmed)

Orange is the primary brand colour, always -- this was an open question when the
placeholder system was first built (the landing spec's Mino description called for an
orange sweatshirt while the app's then-current accent was blue); it's now settled.
Official art should use:

- **Primary / sweatshirt**: `#B5450C` in light contexts, `#F0954D` in dark contexts
  (`--accent` in `apps/web/src/styles/globals.css`) -- a deep terracotta, not a bright
  traffic-cone orange.
- **Secondary**: `#2C4A7C` light / `#7DA2E8` dark (`--secondary`) -- the app's own former
  primary accent, now a deliberate secondary colour. A logo detail, a shoe accent, a
  secondary shape in the background -- not the dominant colour.
- **Base**: the app's existing cream/off-white (`--surface`, `--ink-50`) -- unchanged,
  "talvez branco" was already true before this decision.

The current placeholder SVGs use a flat `#B5450C` shape as a colour cue for where the
sweatshirt goes -- it is not a garment design, just a stand-in so the placeholder isn't
colour-neutral while official art is pending.

## Where to put files

```
apps/web/public/brand/mino/
  mino-hero.svg
  mino-reading.svg
  mino-thinking.svg
  mino-studying.svg
  mino-pointing.svg
  mino-celebrating.svg
```

The map in `apps/web/src/brand/mino.ts` is the only place these paths are
named — swap the files, keep the filenames, and every component that
renders Mino updates automatically.

## What each state is used for

| State | Where it appears | Mino's role |
|---|---|---|
| `hero` | Landing page hero | First impression — curious, inviting, looking toward the visitor or the page's headline. |
| `thinking` | Pillars section (scroll-triggered) | Considering a question before answering — not a blank stare, an active "working on it." |
| `pointing` | Pricing section (scroll-triggered) | Directing attention to a concept or a plan. |
| `celebrating` | Closing section (scroll-triggered) | A real win — reaching mastery, not generic confetti-energy. |
| `reading` | (reserved for a future "content ingestion" section) | Absorbing a document/material. |
| `studying` | (reserved for a future practice section) | Engaged with a flashcard/question. |

Four of six states render today, driven by `useScrollMinoState` (an
`IntersectionObserver` over `MINO_SECTIONS` in `page.tsx` — no scroll
hijacking, disabled entirely under `prefers-reduced-motion: reduce`).
`reading`/`studying` are wired into the asset map and ready the moment a
future section needs them — no code change, just a new entry in
`MINO_SECTIONS`.

## Format

- **File type**: SVG preferred (crisp at any size, tiny file weight, matches
  what's there now). If official art is raster instead, use WebP — update
  `MinoStage.tsx` to drop `alt=""` down through a plain `<img>` unchanged
  (WebP needs no special Next.js handling); do not switch to `next/image`
  without also setting `images.dangerouslyAllowSVG: false` explicitly and
  confirming every remaining SVG is still served safely.
- **Dimensions**: square, minimum 480×480px source (the component renders
  at 480×480 today; a higher-resolution source scales down cleanly, a
  lower-resolution one won't scale up cleanly on a retina display).
- **Background**: transparent. Every placement sits on the app's own warm
  cream/`--surface` background (see `apps/web/src/styles/globals.css`), so
  a baked-in background will show a visible box.
- **Aspect ratio**: 1:1. `MinoStage` sets `width`/`height` to 480 to reserve
  layout space before the asset loads (avoids a layout shift) — a
  non-square asset will look stretched.

## Accessibility

Every current placement is decorative (`alt=""` + `aria-hidden="true"`) —
the surrounding copy already states everything a screen reader needs. If a
future section makes Mino carry information the copy doesn't already say
(e.g. Mino "speaking" a line with no text equivalent nearby), that
placement needs a real `alt` describing what's communicated, not an empty
one — update the call site, not `MinoStage` itself, since decorative is the
correct default for every placement built so far.

## Reduced motion

No placement animates yet. When motion is added (a later phase — see the
phased plan referenced above), gate it behind
`@media (prefers-reduced-motion: no-preference)` and provide the static
image as the reduced-motion fallback, matching
`apps/web/src/styles/globals.css`'s existing global reduced-motion rule.
