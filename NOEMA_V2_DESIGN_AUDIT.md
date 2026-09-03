# NOEMA V2 — Design Audit (Phase 1)

*What the product is today, screen by screen, judged against the V2 brief and
Nielsen's heuristics — before any component is touched.*

Written against `main` at `66796db` (2026-08-15). Phase 2 (screenshots of the
existing experience) follows in `NOEMA_V2_QA.md` once the current build is
served; this document is the written half of "understand Noema before touching
UI".

Two constraints frame everything below:

1. **Preserve all functional logic.** Nothing in this audit proposes changing
   prompts, the learning engine, FSRS scheduling, progress maths, schemas, auth,
   billing or API integrations. Where a UX change needs a backend change, it is
   called out with the technical reason.
2. **Another session is committing to `main` concurrently** and owns the SaaS
   pivot (billing, entitlements, admin, tiers) and the current landing V2 with
   Mino. The V2 redesign lands additively behind `NOEMA_DESIGN_V2`, rebases
   often, and does not rewrite files that session is actively touching without
   coordination.

---

## 1. Current product map

### Routes (23)

| Area | Route | What it is today |
|---|---|---|
| Marketing | `/`, `/terms`, `/privacy` | Landing V2 (hero + Mino, pillars, live pricing, closing), legal |
| Auth | `/login`, `/forgot-password`, `/reset-password` | Email/password, signups gated by `/meta`, reset via Resend |
| Learn | `/chat` | Notebook-independent Professor (general knowledge) |
| Learn | `/notebooks/[id]/professor` | Professor inside a notebook (grounded, memory, actions) |
| Home | `/today` | Session plan for a time budget; "Start session" → `/review` |
| Library | `/library`, `/notebooks/[id]` | Subjects → notebooks; notebook = notes + documents + Anki import |
| Practice | `/review` | FSRS review of due cards (offline queue) |
| Practice | `/notebooks/[id]/cards` | Draft/approve/discard cards |
| Practice | `/notebooks/[id]/quiz` | Generated questions, graded, confidence |
| Practice | `/notebooks/[id]/exam` | Timed paper, marked at hand-in |
| Practice | `/explain` | Feynman: write it, get findings |
| Practice | `/socratic` | Questioned until you say it |
| Progress | `/progress`, `/mistakes`, `/graph`, `/goals` | Mastery + calibration, mistake bank, concept graph, dated goals |
| Account | `/settings` | Providers/keys, language, export, delete; billing surfaces |
| Ops | `/admin` | Email-allowlisted: AI spend, economics simulator, users |

### Backend surfaces the UI depends on (unchanged by V2)

`POST /ai/professor` (classify → dispatch → SSE `intent | sources | token | done |
error | blocked | warning`), `POST /ai/chat` (manual mode), study routes
(cards, reviews + batch, questions, exams, sessions, mastery, forecast,
calibration, goals, mistakes, drills, explain, socratic), library CRUD, sources
+ ingestion progress stream, imports/exports, billing (plans, checkout, portal),
account, meta, admin.

### Design system as built

- **Tokens:** `--ink-50…900` warm neutral ramp; `--surface`, `--surface-raised`,
  `--line`; `--accent` terracotta `#B5450C` (light) / `#F0954D` (dark);
  `--secondary` ink-blue; `--positive/--caution/--critical`. Tailwind maps
  them 1:1. Nine-step type scale, `max-w-reading: 68ch`. Motion: 120 ms state,
  200 ms enter, one easing, one `fade-up` keyframe.
- **Type:** Newsreader (display + reading), Inter (UI), JetBrains Mono —
  vendored, loaded from disk.
- **Dark mode:** a designed palette, applied by `prefers-color-scheme` or
  `data-theme` — **but nothing in the app ever sets `data-theme`.** There is no
  toggle. Dark is system-only.
- **Components:** none shared beyond `Field`, `InlineCreate`, `Shell`,
  `CommandPalette`, `LanguageSwitcher`, `QuestionInput/Card`, `SourceList`,
  `AnkiImport`, `TutorPanel`, the editor. Buttons, selects, modals, toasts,
  tabs, progress bars are hand-written per screen with copied class strings.
  `docs/design-system.md` says "built on shadcn/ui primitives (Radix)" — **no
  such dependency exists in `package.json`.** The doc describes an intention,
  not the code.
- **Icons:** none. No icon library at all. (This is a strength to keep.)
- **i18n:** complete — every screen, including the ones added since, uses the
  typed dictionaries (PT/EN/ES). API-composed sentences remain English.
- **Mino:** six hand-drawn placeholder SVGs (≈4 KB each), one `<img>` swapped
  by scroll position (`useScrollMinoState`, IntersectionObserver on a centre
  band, off under reduced motion) plus a 2.5°/5 px cursor tilt on hover-capable
  devices. Landing only. `MINO_ASSETS.md` states plainly these are stand-ins
  for official art.
- **Offline:** review submissions queue to `localStorage` and flush in batch.
  The only offline-tolerant surface.

---

## 2. Findings by Nielsen heuristic (cross-cutting)

| # | Heuristic | Finding | Severity |
|---|---|---|---|
| 1 | Visibility of system status | Professor shows an intent-aware "thinking" line and a caret; nothing tells the learner *where they are in a lesson* (no session header: subject → topic → objective → progress). Reviews/notes autosave states exist ("Saved / Saving…") — good. Ingestion shows stage names — good. No global "what the AI is doing" language beyond the Professor. | High |
| 2 | Match with the real world | Learner-facing copy is clean of "embedding/vector/token" — verified across dictionaries; "AI Compute Units" is used for limits, deliberately. **Exception:** provider errors reach the screen verbatim via `ApiError.detail` (a 400 body from the provider can be shown). Internal names leak in a few places: "grounded", "notebook", "concept", "calibration". | High (error path), Low (naming) |
| 3 | User control | Stop generation exists. No regenerate, no "explain differently" (a chip that changes strategy). No way to leave a Socratic/Feynman dialogue except "Pick another". Exam timer hands in rather than discards — good. | Medium |
| 4 | Consistency | "Continue" means five things (`/today` Start session → review; `/library` Start reviewing; landing Continue learning → `/chat`; Professor Send; quiz Next). Primary button is `bg-ink-900` (near-black) everywhere; the brand accent is used for links and focus — **the primary action is not orange**. | High |
| 5 | Error prevention | Notes autosave; review queue survives offline; Professor transcript **does not survive a reload** (React state only); a half-written explanation in `/explain` is lost on navigation. | High (Professor) |
| 6 | Recognition over recall | `/today` shows a plan but not "where you left off"; nothing shows the last lesson, last topic, or a suggested next step tied to the learner's own journey. `/chat` starts empty every time. | High |
| 7 | Flexibility | Ten nav destinations for everyone from day one; power features (Socratic, Feynman, graph, goals, calibration fit) sit at the same level as "Today". Command palette exists (⌘K) — good. | Medium |
| 8 | Minimalism | Chrome is already restrained (no card soup, no icons, one accent). The problem is the opposite: **surfaces are so uniform they don't establish hierarchy** — every screen is an `h1` + list; nothing says "this is the one thing to do now". | Medium |
| 9 | Error recovery | Errors are one red line with the server's sentence; no retry affordance except where hand-added. | Medium |
| 10 | Help | Empty states are well-written prose (a real strength) but never offer the *action* in place — e.g. "No concepts yet" doesn't offer "start learning something". | Medium |

---

## 3. Screen-by-screen

Format: **CURRENT → PROBLEM → V2 SOLUTION → PRIORITY.** P0 = required for
"one product" and the core loop; P1 = required for definition-of-done; P2 =
polish.

### 3.1 Landing `/`

- **Current:** Hero (headline, lede, two buttons) with Mino at right that tilts
  with the cursor and changes pose per scroll section; three-column pillars;
  pricing fetched live from `/billing/plans`; closing principle; footer. Mino
  states used: hero → thinking → pointing → celebrating. No social proof (good
  — none invented). Reduced motion respected.
- **Problem:** It *tells*, it does not *demonstrate*. No "O que você quer
  aprender?" input, no learning-path reveal, no professor exchange, no
  flashcard, no adaptation beat. Mino changes pose but does not *react to the
  visitor*. Pillars are still a card grid. Primary CTA is near-black, not the
  brand signal. Background is flat cream — no ambient warmth. The Mino art is a
  placeholder by the repo's own admission.
- **V2:** Hero = headline + the interactive field (rotating examples; typing a
  subject moves Mino to *thinking* and reveals a prepared, clearly-labelled
  demonstration of a learning path — never presented as live AI unless it is).
  Seven scroll beats (goal → path → professor → practice → adapt → remember →
  progress), each a real UI fragment, entering with opacity/transform via
  IntersectionObserver, no scroll hijack. Mino enters, reacts, leaves per beat.
  Orange primary CTA. Warm-white ground with one subtle ambient light; deep
  graphite + one orange light in dark. Pricing restyled in-system.
- **Priority:** P0 (it is the product's face) — after tokens/components.

### 3.2 Authentication `/login`, `/forgot-password`, `/reset-password`

- **Current:** Centred form, `Field` component, signups hidden when the
  deployment closes them, language switcher, reset flow present.
- **Problem:** Functionally sound; visually anonymous. No Mino, no orange, no
  sense of entering a learning space. Errors are the server sentence.
- **V2:** Same logic; V2 tokens; a quiet Mino *idle* on the split (desktop) and
  none on mobile; orange primary; human error copy with retry.
- **Priority:** P1.

### 3.3 Onboarding / Create new learning

- **Current:** **Does not exist as a flow.** A new account lands on `/today`
  ("Nothing to do right now") or `/chat` (empty composer). Creating a
  "learning" means: Library → New notebook → upload/write → Professor. The
  spec's Step 1 question ("O que você quer aprender?") is asked nowhere.
- **Problem:** The single most important first-run moment has no design. The
  goal the learner has is never captured, so nothing downstream (dashboard,
  Professor, adaptation) can reference it.
- **V2:** A first-run flow: one open question → (optional, at most two)
  adaptive follow-ups → a learning path shown before starting. **Backend note:**
  this needs a persisted learning goal/journey. That object is the
  `TeachingSession`/journey the teaching-engine audit already calls for
  (`docs/teaching-engine-audit.md` §5.1) — one new table serves both programs.
  Until it exists, the flow can create a notebook + goal (both exist) and open
  the Professor with the stated goal as the first turn.
- **Priority:** P0.

### 3.4 Navigation shell

- **Current:** Desktop: 240 px sidebar with 11 links (chat, today, library,
  goals, review, explain, socratic, mistakes, graph, progress, settings) +
  palette + sign-out + language. Mobile: bottom bar with the first 4 + "More"
  (palette). Tutor rail moves under content below `xl`.
- **Problem:** Eleven peers, no grouping, no collapse. `/chat` and `/today`
  compete for "home". Explain/Socratic/Mistakes/Graph are *modes and views of
  learning*, not destinations.
- **V2:** Five areas — **Home, Learn, Review, Notes, Progress** — with the
  rest reachable inside them (Socratic/Feynman as Professor strategies and
  quick actions; Mistakes and Graph as tabs of Progress; Goals inside a
  subject's home). Sidebar collapsible to a rail; mobile bottom nav with the
  same five. Palette stays. Every current route keeps working (redirects, not
  deletions).
- **Priority:** P0 (Phase 9).

### 3.5 Dashboard `/today`

- **Current:** "I have [10/20/30/45/60]m" → a plan of blocks (warm up / repair
  / practice / wind down) with the engine's rationale, then "Start session".
- **Problem:** Answers "what should I do in 30 minutes" — not "where was I".
  No continue-learning, no recent topics, no reviews-due count (that's on
  `/library`), no suggested next step tied to a goal. Time-budget chips are the
  first thing on the screen.
- **V2:** Greeting (optionally Mino, not every time) → **Continue learning**
  (last subject/topic/objective, one orange action) → Reviews due (count +
  one action) → Your learning (subjects with a path position, not a %) →
  Progress (one honest signal) → the existing plan as "Plan a session" below.
  Reads existing data (`/mastery`, `/cards?due`, `/goals`, notebooks); the
  "where you left off" needs the persisted session (§3.3 backend note).
- **Priority:** P0 (Phase 12).

### 3.6 Professor `/notebooks/[id]/professor` and `/chat`

- **Current:** One centred column; turns labelled "YOU" / "NOEMA" in small
  caps; plain `whitespace-pre-wrap` paragraphs; a pulsing caret while
  streaming; intent-aware status text; three chips (Test me / Go deeper /
  Summarize) shown once there are turns; "Save to notes"; action cards for
  created cards/quiz/exam; sticky composer with Stop. `/chat` is the same
  without the notebook.
- **Problem:** This *is* the chatbot feel the brief names, minus the bubbles:
  transcript + composer, no lesson state (subject → topic → objective →
  progress), no Mino, replies rendered as one undifferentiated paragraph
  (markdown lists/code/tables are not even rendered — verified: `<p
  className="whitespace-pre-wrap">`), no inline educational blocks, chips are
  the same three every time, no "explain differently", no highlight-to-note,
  and the transcript dies on reload.
- **V2:** A **learning session** layout: quiet session header (breadcrumb of
  the journey + objective + progress), a reading-width lesson column where
  each Professor turn renders structured blocks — Concept, Example, Quick
  Check, Think About It, Definition, Mini Exercise, Flashcard, Diagram
  placeholder — from the metadata the teaching engine will emit
  (`docs/teaching-engine-audit.md` §5.5), Mino as a small contextual presence
  that moves thinking → teaching → listening, contextual quick actions
  (Explain differently / Example / Test me / Go deeper — chosen per turn, not
  all four always), highlight → Save / Ask / Flashcard, and a composer that
  does not shift layout on mobile keyboards. **Backend notes:** (a) markdown
  rendering is frontend-only; (b) inline blocks need the metadata sidecar from
  the teaching engine; (c) reload-survival needs persisted turns — the same
  table as §3.3. This screen is where the design V2 and the teaching-engine
  rebuild are literally the same work.
- **Priority:** P0 (Phase 13).

### 3.7 Subject home `/notebooks/[id]`

- **Current:** Notebook title, Exam/Quiz/Cards buttons, note list (left),
  editor (right), documents + Anki import below the note list, tutor rail.
- **Problem:** It is a notes editor with buttons, not a "learning home". No
  path, no progress, no recent lesson, no reviews due for this subject, no
  Professor entry as the primary action.
- **V2:** Learning home: current progress on the path, the next activity as
  the one orange action, recent lesson, notes, cards/reviews due, documents —
  progressive disclosure, no card grid. The editor becomes a page under Notes.
- **Priority:** P1 (Phase 15/16).

### 3.8 Notes editor

- **Current:** TipTap with slash commands, math, callouts, wiki-links, bubble
  menu (Explain / Simplify / Expand / Ask NOEMA), autosave with status.
- **Problem:** Solid. Feels like a document editor; the connection to the
  lesson (Save from Professor) exists but is one-way.
- **V2:** Keep the editor; restyle in-system; make "notes from this lesson"
  visible from the session. No logic change.
- **Priority:** P2.

### 3.9 Flashcards `/review` and `/notebooks/[id]/cards`

- **Current:** Review: front text, "Show answer (space)", four rating buttons
  with interval previews and keyboard numbers, then a six-button confidence
  row; honest microcopy; offline queue. Cards: approve/discard drafts with
  inline editing.
- **Problem:** Text-only "card" with no physicality — no flip, no card object;
  the confidence row of six tiny buttons on mobile is cramped; no Mino
  reaction to a right answer (brief, not confetti).
- **V2:** A card object with a natural (not exaggerated) flip; the *same*
  four ratings and confidence step (algorithm untouched); larger touch
  targets; a focused mode with the shell reduced; Mino small, contextual.
- **Priority:** P1 (Phase 17/18).

### 3.10 Quiz / Exam / Mistakes / Explain / Socratic

- **Current:** All consistent in structure (header, one-column content, prose
  empty states). Exam is well-designed functionally (fixed paper, timer hands
  in). Mistakes puts misconceptions first with "Break the belief". Explain and
  Socratic are concept lists → dialogue.
- **Problem:** Wrong answers are a red line ("Not quite") — no "why" from the
  teacher; test mode has no visible progress rail; Socratic/Feynman are
  separate destinations rather than ways to learn a concept.
- **V2:** Test mode: question centred, progress visible, feedback that
  explains (Mino: why). Mistakes and Explain/Socratic become reachable from
  Progress and from the Professor's quick actions; their pages stay (routes
  preserved) but leave the top-level nav.
- **Priority:** P1.

### 3.11 Progress `/progress`, `/graph`, `/goals`

- **Current:** Mastery list (weakest first, expandable components), 14-day
  forecast bars, calibration section with "Fit to my history"; SVG concept
  graph with keyboard navigation; goals with feasibility verdicts.
- **Problem:** Good honesty, poor orientation: no "what I learned / where I
  am / what's next" narrative; the graph is a separate page instead of the
  knowledge map the brief asks for.
- **V2:** Progress = knowledge map (the existing `ConceptGraph`, reframed as a
  tree/neighbourhood of what's learned) + mastery + honest calibration;
  Mistakes as a tab. Goals move into the subject home. No maths changes.
- **Priority:** P1.

### 3.12 Settings, billing, admin

- **Current:** Providers/keys, language, export, delete; plan/billing surfaces
  via Stripe (not live-verified per roadmap); admin dashboards.
- **Problem:** Consistent but plain; no theme control anywhere.
- **V2:** Add **Appearance: Light / Dark / System** (the only missing control
  in the whole app), restyle; billing surfaces in-system. Admin gets the
  tokens and nothing else.
- **Priority:** P1 (theme), P2 (rest).

### 3.13 Empty / loading / error states

- **Current:** Empty states are the product's best copy. Loading is
  "Loading…" everywhere. Errors are `<p role="alert">{err.message}</p>` —
  which can be a provider's own sentence.
- **Problem:** No retry pattern; provider/API wording can reach the learner
  (the brief's absolute prohibition); loading has no Mino and no specificity
  outside the Professor.
- **V2:** One `ErrorNotice` with human copy + retry, and a client-side map
  that never renders a provider's detail for AI failures (the backend already
  abstracts most; the UI must never trust `detail` for provider errors).
  Loading: Mino only where a wait is meaningful (creating a path, preparing a
  lesson). Empty: Mino + the action.
- **Priority:** P0 (error abstraction), P1 (rest).

### 3.14 Dark mode

- **Current:** A designed palette, applied only by OS preference. Accent lifts
  to `#F0954D`. No toggle, no transition, no Mino treatment.
- **Problem:** Unreachable by choice; no "dark room, one orange light"
  intent; ground `#0E0E10` is cooler than the brief's warm graphite.
- **V2:** Separate dark token set (warm black / graphite / charcoal ramp),
  orange reserved for active/focus/progress/primary/Mino light; a three-way
  toggle; class-based transition without white flash; Mino legible with a
  faint warm light, no glow.
- **Priority:** P1 (Phase 23), tokens in P0.

### 3.15 Mobile

- **Current:** Responsive throughout (verified at 375 in the i18n pass);
  bottom bar with four items; Professor composer sticky above the bar.
- **Problem:** Keyboard/viewport behaviour of the composer is unverified on
  a real device; confidence rows and rating grids are tight; no gestures.
- **V2:** Test matrix 320–1920 per the brief; composer pinned correctly with
  `100dvh`; touch targets ≥ 44 px; flashcard gestures optional with buttons
  always present.
- **Priority:** P1 (Phase 24).

### 3.16 Mino

- **Current:** Six static SVG placeholders, `<img>` swapped on scroll, cursor
  tilt, landing only. Reduced motion respected. Assets ≈ 24 KB total.
- **Problem:** Static poses swapping is not a state system; no presence
  inside the product (Professor, reviews, empty states); the art is an admitted
  placeholder.
- **V2:** A `Mino` component with a state machine (idle, thinking, teaching,
  listening, celebrating, curious, sleeping, confused, focused — implement
  what's used), driven by product events (streaming start/end, correct answer,
  review due, empty state), animating **efficient properties only** (opacity,
  transform, a few SVG path/opacity tweens), lazy where heavy, off under
  reduced motion. **The existing art is preserved** — same character, same
  files, same map; animation layers over it. Official art remains a swap-in.
- **Priority:** P0 (Phase 7).

### 3.17 Tokens, components, motion

- **Current:** Tokens exist and are good; the accent is a terracotta rather
  than an "intelligent orange" ramp; no orange scale (`50…900`); no radius or
  elevation scale; motion has two durations and one easing; components are
  per-screen class strings.
- **Problem:** Consistency is by discipline, not by system — the moment a
  second person edits a screen, it drifts (and the doc already describes
  primitives that don't exist).
- **V2:** `--noema-orange-50…900` (light and dark sets), warm-white/cream
  surfaces, charcoal text, radius scale (sm/md/lg/full), elevation (0/1/2, dark
  via surface not shadow), motion tokens (fast/normal/slow/spring), and a small
  primitive library — Button (primary orange / secondary / ghost /
  destructive), Input, Select, Modal, Popover, Tooltip, Progress, Tabs, Toast
  — replacing the copied strings screen by screen behind the flag.
- **Priority:** P0 (Phases 3–8).

### 3.18 Accessibility and performance

- **Current:** Focus never removed (ring restyled); keyboard support in
  review, graph, palette; `aria-label`s present; reduced motion respected in
  the landing hooks. No audit of contrast for the accent (terracotta on cream
  passes; `#F0954D` small text on `#0E0E10` needs checking). Performance not
  measured; no icon library, vendored fonts — a good baseline.
- **Problem:** Unverified rather than wrong.
- **V2:** WCAG pass per screen (Phase 25); Lighthouse/CWV on the landing
  before and after (Phase 26); orange ramp chosen with measured contrast at
  each step.
- **Priority:** P1.

---

## 4. What must not change (and why)

- **Prompts and the teaching engine** — their rebuild is a separate program
  with its own audit; the UI consumes its metadata, never edits its behaviour.
- **FSRS, mastery, calibration, exam grading** — the review screen's four
  ratings + confidence are the algorithm's inputs; V2 changes their clothes.
- **Schemas** — except one addition both programs need: persisted session /
  turns (a new table, no migration of existing data).
- **Auth, billing webhooks, entitlements, admin** — owned by the other session.
- **The honesty in copy** — empty states, calibration wording, "not in your
  materials", import reports. V2 restyles; it does not soften.

## 5. Migration order (the brief's, mapped to this codebase)

1. **Tokens** — `globals.css` + `tailwind.config.ts`, additive: the orange
   ramp, surfaces, radius, elevation, motion; `NOEMA_DESIGN_V2` flag switches
   the root token set.
2. **Core components** — `components/ui/` primitives; adopted screen by screen.
3. **Shell** — five-area navigation, collapsible rail, theme toggle.
4. **Landing** — hero interaction + scroll beats, on the existing landing V2
   scaffolding (keep `useScrollMinoState`, `useHeroTilt`, `MinoStage`).
5. **Mino** — state machine + product presence, over the existing art.
6. **Dashboard** → **Professor** (with the teaching engine's session/metadata)
   → **Create learning** → **Subject home / path** → **Flashcards / Reviews /
   Tests** → **Notes / Progress** → **Settings / Auth / Billing**.
7. **Dark, mobile, a11y, performance, regression, production QA.**

Visual regression: the current build is being served locally for the "before"
capture; "after" is compared per screen in `NOEMA_V2_QA.md`.
