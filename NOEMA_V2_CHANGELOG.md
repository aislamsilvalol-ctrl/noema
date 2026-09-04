# NOEMA V2 — Changelog

Running log of what V2 changed, per phase, with the commit. Newest first.

## 2026-09-03

- **Phase 11 — Scroll storytelling.** The six pillar cards become six beats
  after the hero (`components/landing/Beats.tsx`): one claim each, with a
  small in-system illustration beside it — a lesson block rendered through
  the real markdown component, mastery bars, a confident-wrong verdict, a
  citation with "not in your materials", a generated question, a review
  card. Each beat drives the companion Mino (pointing, thinking, studying,
  reading…); reduced motion keeps everything still. The hero's "Show me" is
  the page's one orange primary; "Start learning" is the secondary.
- **Phase 19 — Tests.** `QuestionCard`/`QuestionInput` (shared by quiz, exam
  and mistakes): raised options, orange when chosen, `aria-pressed`; one
  orange Answer, confidence as secondary buttons, the verdict on a
  green/red rule, Mino reacting to it. Quiz and exam pages use `Notice`,
  `Button`/`ButtonLink` and `humanError`. Grading, timer and hand-in
  logic unchanged.
- **Phase 20 — Notes.** `/library` is titled as the shell names it (Notes),
  with one line of what it holds, "New learning" as the primary beside the
  manual New notebook, subject groups on the reading measure, and an empty
  state that points at the create-learning flow. Editor prose already
  resolves through the V2 tokens (`.noema-prose` uses `accent`/`accent-soft`,
  which the token layer maps to orange); no editor logic touched.
- **Phase 21 — Progress as one place.** `/progress` opens with Mino and one
  sentence of where you are (concepts measured, solid, needing work), a bar
  per concept under the weakest-first list, the forecast in orange, and a
  tab row — Overview · Map · Mistakes — shared with `/graph` and `/mistakes`
  (`components/progress/ProgressTabs`). Routes and maths unchanged.
- **Phase 22 (auth) — entering a learning space.** `components/auth/AuthFrame`:
  on wide screens a quiet panel with Mino at rest and one sentence beside
  the form, on phones just the form; the language control in one place.
  Sign-in, sign-up, forgot and reset use the orange primary and the V2
  field focus. Logic untouched. Settings and billing surfaces still to do.
- **Phases 17–18 — Reviews.** `/review`: the card is an object that turns
  over (a Y rotation, none under reduced motion), Mino small and reviewing
  with one short spring on Good/Easy, a thin progress line, thumb-sized
  targets, `Notice` empty/complete states. Ratings, interval previews,
  confidence step, keyboard and offline queue are byte-for-byte the same
  logic. **Fix:** the Anki importer stored cloze notes raw, so they reviewed
  as `{{c1::…}}` with no answer; it now renders one card per deletion
  (`noema.engines.cloze`, chosen by Anki's `ord`), and the page renders any
  raw card already stored (`lib/cloze.ts`).
- **Phase 15 — Subject home.** `/notebooks/[id]` leads with *Where you are*
  (the open lesson for this notebook, last-lesson time, one orange
  Continue/Start), then *Practice* (cards due here; cards/quiz/exam as quiet
  links), then *Notes* — the list, with the editor appearing when a note is
  chosen instead of swallowing the page on load — and *Material* folded.
  Autosave, selection actions, Anki import, sources and the tutor rail are
  unchanged.
- **Phase 14 — Create learning.** `/learn/new`: one open question (prefilled
  from the landing hero), two skippable follow-ups (where are you with it;
  what is it for), the shape of a path — labelled as an illustration — and
  one action. Start creates a subject and a notebook with the existing
  endpoints and opens the Professor with the learner's goal, in their own
  words, as the first turn (`lib/prefill.ts`, autosend), so the teaching
  session records it as `learning_goal`. Hero and Home enter the flow;
  sign-up lands on it; sign-in lands on Home. No dated goal is created — the
  flow does not ask for a deadline, and the goals screen refuses to pretend.
- **Phase 13 — the Professor as a learning session.**
  `components/professor/Lesson.tsx`: `LessonHeader` (Mino following the
  stream: thinking → teaching → idle, confused on error; "Aprendendo X · em Y"
  once the session names them), `LearnerTurn`, `LessonBlock`, `Composer`
  (one orange Send, Stop while streaming, quick actions incl. **Explain it
  differently**). `lib/markdown.tsx`: the Professor's light markdown rendered
  as React elements — never an HTML string — so bold terms, lists, headings,
  quotes and code read as a lesson instead of raw asterisks. Both Professor
  screens use the pieces; request/session/save-to-notes/created-items logic
  unchanged. New turns scroll into view. Strings in PT/EN/ES.
- **Phase 12 — Home answers "where was I".** `/today` now leads with
  *Continue learning* (the open lesson from `/ai/sessions/latest`), then
  reviews due, then the learner's notebooks; the time-budget planner is kept,
  logic untouched, as the last section. Panels load with `Promise.allSettled`
  so one failing endpoint cannot blank the others; plan errors go through
  `humanError`. New `today.*` strings in PT/EN/ES.

## 2026-08-15

- **Teaching engine — the lesson, remembered.** `teaching_sessions` +
  `teaching_turns` (migration 0017); every Professor message belongs to a
  session; learner and Noema turns are written down; an `ACTIVE_SESSION`
  block carries the lesson's state into the prompt; `GET /ai/sessions/{id}`
  and `/latest`; both Professor screens send the id back and resume the
  transcript on reload. Prerequisite for design Phases 12–14.
- **Phases 7–8** (`03b1205`) — `Mino` component with ten states over the
  existing art; `Button` and `Notice` primitives; `lib/errors.ts` so provider
  text never reaches the learner; the mobile bar's wrapping label fixed.
- `df4f7c7` — **Phase 4: the design-token layer and the theme control.** Orange ramp
  50–900, warm-white / warm-black grounds, semantic tokens, radius/elevation/
  motion scales, all behind `data-design="v2"`. `ThemeProvider` +
  pre-hydration script; Settings → Appearance: Light / Dark / System in PT/EN/ES.
  V1 renders unchanged without the flag (verified from the same build).
- **Phases 3–6 — visual system** (`3ddbe77`). `NOEMA_V2_DESIGN_SYSTEM.md`:
  colours chosen by WCAG measurement (light primary stays `#B5450C` — the only
  step passing as text and as a button; `#F26B1D` is the large-signal orange;
  dark lifts to 400/500), typography kept, space/radius/elevation/motion,
  iconography rule, primitives list, Mino state system, one-orange-action rule,
  learner vocabulary.
- **Phase 1 — audit** (`5f73e2f`). `NOEMA_V2_DESIGN_AUDIT.md`: product map,
  Nielsen findings, every screen as CURRENT / PROBLEM / V2 / PRIORITY, what must
  not change, migration order.
- **Phase 2 — before-screenshots**. Observed and recorded in
  `NOEMA_V2_QA.md`; one mobile defect found (bottom-bar label wrapping).

## Related, same day (teaching engine — the other open program)

- `66796db` `docs/teaching-engine-audit.md` rewritten against the Professor
  path; `evals/teaching/baseline/freud-before.md` captured against production.
  The Professor redesign (Phase 13) and the teaching engine's persisted
  session + lesson metadata are one piece of work.
