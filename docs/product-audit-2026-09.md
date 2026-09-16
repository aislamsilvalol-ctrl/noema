# NOEMA — Product audit, 2026-09-16

The audit that precedes the rebuild. Three read-only passes over the
repository (authenticated product, API and learning engine, landing and
front-end performance), the production site viewed in a browser, and the
baseline checks (typecheck, lint, 129 tests: all green at `0157185`).

Where this document says "verified", it was read in the code or seen on the
deployed site. Where it says "reported", it comes from a pass that read the
code but did not run it. Nothing here is a design proposal; the direction
lives in `docs/brand-os.md` and the backlog at the end is the plan.

## NOEMA status

Described, not scored — scores would be arbitrary.

| Dimension | Where it stands |
|---|---|
| **Product completeness** | Deep. Six phases of engine work exist end to end: FSRS with per-user fitting, two mastery models, a Professor with moves, memory, focus mode, assessments, flashcards, journeys, imports/exports, billing code, admin. What does not exist: a diagnostic, a cross-subject learner model, a composed daily session, any connection between the two mastery systems, and the academic pipeline behind any route. |
| **UX maturity** | Uneven. The lesson (`/chat`, study rail, Focus Stage) and the rail are considered; the rest carries an older density and five entrances to the same act (Professor ×2, TutorPanel modes, `/explain`, `/socratic`). The first-run path is broken (see blockers). |
| **Visual maturity** | The identity is real and its own — cream ground, Newsreader display, one orange word, the character lit like an object — and it survives on the deployed hero. Inside the product: 1 px mastery bars, off-token colours, three duplicated flip-card implementations, `text-xs` everywhere. |
| **Learning-system maturity** | Strong on evidence, weak on adaptation. Reviews, answers, mistakes, mastery events and memories are recorded carefully; adaptation is prompt directives whose compliance nobody checks, and the production student model is a weighted mean with hard-coded constants. Sabelia is not in the loop (shadow only, off by default). |
| **Mobile readiness** | Not yet. No safe-area handling anywhere; fixed tab bar and composer sit on the home indicator; the landing headline overflows at 320–430 px; the hero poster is 396 KB of PNG for a 128 px figure. |
| **Launch readiness** | Blocked by five things, each fixable this week (P0 below). After them the product is usable; "memorable" is the work of the phases that follow. |

## Top blockers (verified)

1. **Onboarding cannot finish.** `/learn/new` step 4 ("Normal or Focus") has no Continue, Skip or Back — `apps/web/src/app/learn/new/page.tsx:185-212`. Every new account is routed here from registration. The wizard's `start()` — which creates the subject and notebook and opens the first lesson — is unreachable from the UI.
2. **"Continue" opens an empty lesson.** Home and Progress link to `/chat`; `/chat` resumes only a session id kept in this tab's `sessionStorage` under its own key, which the notebook Professor never writes. In a new tab, or after onboarding, the learner's lesson looks gone.
3. **Mino renders with a black band across the face.** The stage set the mouth node's scale to absolute values (1.1 for a smile) on a node whose authored scale is 0.036 — the mouth became a black disc thirty times too large. Fixed in `three/MinoStage.tsx` (scale is now a multiplier of the authored scale); waiting for deploy. On dark ground the same disc read as a ghosted figure.
4. **Legal pages ship placeholders.** `/privacy` and `/terms` render a red "configuration required" banner and `[razão social a definir]` to end users because `lib/legal-config.ts` is all `null`. This needs the owner's legal identity; nothing in the repository can invent it.
5. **Home contradicts itself for a new account.** With nothing in the library it says "Start learning", then "nothing due — cards are scheduled for when you are about to forget them", then calls the planner and reports "add material, or come back when something is due".

## Top product gaps (reported by the engine pass, spot-checked)

- No cross-subject learner model: profile, concept states and memories are keyed by journey; the second subject starts from zero.
- No diagnostic: level is a one-shot inference from the learner's sentence; the wizard's answers are pasted into the first message, not stored.
- Two mastery systems that do not talk (graph `concept_mastery` for the planner, journey `student_concept_states` for the Professor).
- "Today" does not compose the day: the plan ignores journeys, `needs_review`, preferences and goals; the web never calls `start`/`complete`, so the planner never learns.
- No time-based maintenance (no nightly decay, no weekly FSRS fit, no reminders).
- Focus mode reaches `/chat` and Home only; the notebook Professor — where onboarding lands — ignores it; the mobile tab bar stays in focus.
- `noema/academic` is reachable from no route; "sources from universities" is not a product claim the code can back yet.

## Top UX problems

- Five entrances to AI dialogue across three backends; Mistakes and Graph appear twice in navigation; the command palette duplicates Home.
- No route guard: every authenticated page paints the shell, then bounces on 401.
- Error policy is inconsistent: `lib/errors.ts` exists, nine screens show raw `err.message`.
- Empty states without a next action on `/explain`, `/graph`, `/mistakes`, `/goals`.
- Textareas without accessible names (Composer, Explain, Socratic, TutorPanel); focus rings removed on three flip cards; toggles without `aria-pressed`.
- Untranslated strings in goals, settings, AuthFrame, TutorPanel, the notebook action heading; inert "Phase 2/3" slash-menu entries.

## Top visual problems

- Landing: `text-5xl/6xl` headline and rotating subject overflow the column at 320–430 and 768–1024 (`tailwind.config.ts:86-87`, `LandingV3.tsx:260-266, 647`).
- Hero poster `<img>` without dimensions or preload → layout shift and a poor LCP; the sized `Mino3D` component is unused.
- `text-signal` (2.9:1) and `ink-400` (2.4:1) used for small copy against the token file's own "large only" rule.
- 1 px mastery bars invisible on dark; forecast bars in raw `bg-orange-200/300`; TutorPanel on V1 `accent` tokens.
- Only one breakpoint (`md`) on the landing; header does not wrap at 320 px.

## Performance

- Three WebGL contexts on the landing at load (hero `priority`, always-intersecting fixed companion, the close); the companion renders at 30 fps while `opacity-0`; reduced-motion users still download three + the GLB.
- `public/brand` is 2.1 MB: four 396 KB PNG posters with alpha, no WebP/AVIF, no `srcset`.
- The landing is one client tree importing all of `api.ts` and all three locale dictionaries — including two dead copy generations (`landing`, `landing3`, ~130 lines × 3 files).
- `katex.min.css` (≈23 KB, 60 `@font-face`) on every route.
- SSR is English-only with `lang="en"` for PT/ES visitors; the language switches on hydration.

## Opportunities

- The live demo in the hero (the real tutor answering the visitor's subject) is the strongest thing on the page. Keep it, make everything after it as honest.
- The character system is already a state machine with poses shared by the WebGL stage and the SVG rig — the "Mino as a system of states" the brief asks for is mostly a documentation and tuning job, not a build.
- Journeys, concept states and memories already exist per subject: a Knowledge Map is a view over data the engine writes today.
- `GET /billing/plans` is public and Stripe is configured (test mode) in production: pricing can be real, not typed.
- `session_minutes`, due cards, the latest journey and weak concepts are all available to Home: a composed "today" is a client composition first, an engine change second.

## Funnel

```
VISITOR      landing, English first paint for PT visitors; hero demo works (POST /ai/demo)
  ↓          CTA "Start" → /login, which opens on "Welcome back" (sign-in), one click to register
SIGNUP       name/email/password; no verification step
  ↓          → /learn/new with the landing subject prefilled            ← good handoff
ONBOARDING   subject → level → purpose → mode ✗ dead end                ← P0
  ↓          (if fixed) → /notebooks/{id}/professor, first turn autosent
DIAGNOSTIC   does not exist; level inferred from the sentence
FIRST LESSON the Professor; Focus mode not applied on this route        ← P1
FIRST VALUE  the first check/verdict, cards generated on "understood"
RETURN       Home "Continue" → /chat opens empty                        ← P0
SUBSCRIPTION Stripe test mode; only AI units gated
```

## North star (from what is already recorded)

Not time-in-app. The tables already support: **meaningful learning sessions** (turns with a verdict in `teaching_turns.decision`), **concepts mastered** (`student_concept_states` reaching `mastered`), **weekly consistency** (distinct days with a review or a turn), **review retention** (`analytics/calibration`). None of these is computed as a product metric today; `analytics.ts` tracks three landing events. This document does not invent numbers — it names the four the data can already answer.

## What should be removed or merged

- Locale blocks `landing` and `landing3` (dead).
- `components/mino/Mino3D.tsx` (unused) — or use it as the sized poster.
- The four inert "Phase 2/3" slash-menu entries; `CommandPalette.available` (never set).
- `/explain` and `/socratic` as peer destinations: they are modes of the lesson (the Professor already has a Socratic rung and teach-back). Keep the routes working; take them off the rail.
- Mistakes/Graph from the rail's secondary list (they are tabs under Progress).
- `titleFrom()` ×3 → one; flip-card markup ×3 → one; `STAGE_TONE` ×2 → one.
- The V1 token block in `globals.css` once no screen depends on it.

## Backlog

Effort: S (hours), M (a day), L (days). Order within a tier is the order of work.

### P0 — blockers

| Title | Why | Impact | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| Onboarding step 4 can continue | every new account dead-ends | activation | S | — | test walks all five steps and reaches the Professor |
| `/chat` resumes the latest session | "Continue" is the retention loop | return | S | — | Home → Continue shows the last turns in a new tab |
| Mouth scale fix deployed | the character is the brand | trust | S | deploy | production hero shows no band, light and dark |
| Legal identity filled in | placeholders on public pages | trust, legal | S (owner) | owner's CNPJ/razão social | `legalConfigIsComplete()` true, banner gone |
| Home first-run state | the first screen after signup contradicts itself | activation | S | — | empty account sees one lead, no planner call |

### P1 — critical

| Title | Why | Impact | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| Landing rebuilt on the storytelling structure | the current page is one demo and eight steps; overflow bugs; no atmosphere shift | clarity, conversion | L | Brand OS | checklist §72 of the brief passes |
| Fluid type scale | display sizes overflow phones | mobile | S | — | no horizontal scroll at 320–1728 |
| Poster pipeline (WebP/AVIF, sizes, dimensions, preload) | LCP/CLS | performance | S | — | hero poster ≤ 60 KB on phones, no shift |
| One WebGL context at a time on the landing; none under reduced motion | battery, INP | performance | M | — | companion mounts only when shown; reduced-motion gets stills |
| Focus mode on the notebook Professor + tab bar hidden in focus | onboarding lands there | ADHD promise | S | — | a Focus learner sees the Focus Stage after onboarding |
| Safe-area insets | iOS home indicator over the bar | mobile | S | — | bar and composer clear the indicator |
| Error policy through `humanError` everywhere | raw messages | trust | S | — | no `err.message` in JSX |
| Accessible names, focus rings, `aria-pressed` | keyboard and screen-reader users | a11y | S | — | axe clean on the audited screens |
| "Explain differently" as a visible action in the lesson | the clearest proof of adaptation | learning value | M | — | one control, six modes, the reply changes |
| Route guard for authenticated pages | shell flashes before bounce | polish, trust | S | — | `/today` signed out redirects before paint |

### P2 — important

| Title | Why | Impact | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| Home as "what is most useful now" | decision fatigue; four sections competing | activation, return | M | P0 Home | ordered: continue, review, weak concept, start; one primary |
| Today session composition (client-side, honest) | reduces "what now" | consistency | M | Home | "Today · 12 min" from real due count and session_minutes |
| Knowledge Map over journey concept states | the brief's central feature; data exists | clarity of progress | L | — | `/progress` shows concepts by state with connections and next |
| Rail: five places, modes under Learn | five entrances to one act | clarity | M | — | Explain/Socratic reachable inside the lesson, off the rail |
| Mino state library (doc + dev sheet) | the character as a system | brand | M | mouth fix | every state has expression, posture, motion, context, intensity; a dev page renders them |
| Pricing from `/billing/plans` | real plans exist | conversion | S | — | landing pricing reads the API, hides when unavailable |
| Empty states with a next action | dead ends | activation | S | — | explain/graph/mistakes/goals each offer one action |
| Remove dead copy, dead components, duplicate helpers | weight and drift | maintenance | S | — | see "remove" list |
| Learner profile persisted from onboarding answers | level/purpose are thrown away | adaptation | M (API) | — | `users.settings` holds level/purpose; the Professor reads them |

### P3 — polish

Microinteractions on completion and Mino reactions; dark-theme mastery bars; `aria-live` on the stream tuned to sentences; sticky discreet nav; skip link; `lang` per locale at SSR; katex CSS only where math renders; three families → subset the mono to the glyphs used; motion tokens documented as FAST/NORMAL/SLOW/AMBIENT.

## V1 completion

**Must have before launch:** the five P0s; the landing rebuild; fluid type and the poster pipeline; focus mode reach; safe-area; error policy; accessible names and focus rings; Explain differently; route guard; pricing from the API.

**Should have:** Home as "what now"; Today composition; Knowledge Map; rail simplification; Mino state library; empty states; dead-code removal; learner profile persisted.

**Post-V1:** a real diagnostic (adaptive items, not a sentence); a cross-subject learner model; the two mastery systems unified; time-based maintenance workers; Sabelia in the loop (after it earns it on the benchmarks); the academic pipeline behind a route (licence permitting); project-based learning; a workspace for pasted text and files beyond the notebook.

## Method and limits

- The deployed site was viewed at 1440×900 and 800×500 in the desktop app's browser pane; the pane does not paint while hidden, so only the first viewport of each load could be captured. Everything below the fold was verified in code, not pixels.
- The WebGL Mino was inspected through the GLB's node table (`gltf-transform`), which is how the mouth-scale bug was found; the fix is type-checked and will be verified on the deployed hero.
- Reported items from the three passes were spot-checked where they drove a P0/P1; the rest are cited with file and line so they can be checked in a minute each.
