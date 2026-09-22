# Sabelia V3 — the audit, the target, and the shortest path

Audited 2026-09-22 against the code, not the docs. The finding that shapes everything:

> NOEMA already implements most of what an adaptive learning system needs. It implements it
> **twice**, in two halves that never exchange a fact, and the seam between them is where the
> learner's knowledge falls through.

This document is the map (A), the target (B), the models (C–H), the tutor contract (I), the ML
roadmap (J), and the order of work. It replaces nothing: `mastery-engine.md`,
`learning-engine.md`, `fsrs.md` and `data-model.md` stay the specification of their parts.

## A. Current architecture

**Evidence logs — three, all append-only, all real.**

| log | written by | carries |
|---|---|---|
| `reviews` | `study/review.py:118` `record_review` | FSRS rating, elapsed_ms, confidence, state before/after |
| `answers` | `study/questions.py:302` `answer_question` | score (partial credit), grader, difficulty, confidence |
| `mastery_events` | `professor/student.py:229` `StudentModel.record` | kind, score, weight, elapsed_ms, difficulty, confidence |

`explanations` is a fourth de facto log (feynman, socratic, conversation).
`services/learning_export.py` already merges the three into one pseudonymous stream — the
unified event shape exists and is used only by the export script.

**Projections — two, disjoint.**

| | graph side | journey side |
|---|---|---|
| table | `concept_mastery` | `student_concept_states` |
| key | `concepts.id`, canonical per workspace | `(journey_id, normalized_name)` |
| formula | Beta posterior, prior from prerequisites, × FSRS retrievability (`engines/mastery.py:102`) | recency-weighted mean of event weights (`professor/student.py:77`) |
| forgetting | FSRS-4.5, per-user fitted weights | none — a 7-day constant |
| version field | `model_version` int | `model_version` str |
| reader | `/mastery`, `/graph`, `/progress` | the Professor directive, `/today`, terrain map |

**The seam, with line numbers.** These are defects, not design:

1. `StudentConceptState.concept_id` is **never assigned** (verified: only read, at
   `professor/student.py:234`). Every `mastery_events.concept_id` is therefore NULL, and the
   index added for it in migration 0022 indexes nothing. The journey half cannot name a graph
   concept, so nothing it learns reaches `concept_mastery`.
2. Journey cards are created with `concept_id=None` (`professor/flashcards.py:149`), so an
   in-lesson recall runs `record_review` but skips `recompute_mastery` entirely.
3. `ConceptState.NEEDS_REVIEW` is unreachable: `reproject` passes `last_at=now`
   (`student.py:311`), so the `now - last_at > 7d` test in `stage_for` is never true. Three
   call sites read a state that is never written.
4. `POST /reviews/batch` (`api/v1/study.py:552`) omits `weights=fitted_weights(user)`, so an
   offline batch is scheduled with default FSRS weights while a live review is not.
5. No activity write is idempotent. A re-sent review batch double-counts evidence.
6. The `mastery` SSE event is emitted per concept and the web client registers no handler for
   it (`apps/web/src/lib/useLesson.ts`).
7. `POST /learning-session/start` and `/{id}/complete` exist and no client calls them, so
   `study_sessions` holds plans with no outcomes — the replay evaluation in
   `learning-engine.md` §8 has no data to run on.

**The Sabelia package** (`sabelia/`) is a research lab with a real result: the residual model
now beats every feature baseline it starts from, on every seed of both public datasets. In the
product it is a **shadow that never ran**: `professor/shadow.py` posts events to a service and
stores the answer in `turn.decision["shadow"]`, read by nobody; no service is deployed, no
checkpoint exists in or out of the repo, the loader falls back to a heuristic labelled
`fallback`, and the bridge sends `elapsed_ms`/`score` where the schema expects `response_ms`
and has no `score` — pydantic drops both in silence.

## B. Target

One evidence layer, one reader, one decision log. Concretely:

```
reviews · answers · mastery_events · explanations      (unchanged, append-only)
                    │
                    ▼
        concept identity resolution            ← the fix: names become ids
                    │
                    ▼
        LearnerState(user, concept)            ← one reader over both projections
         competence · retrievability · uncertainty · evidence · misconceptions
                    │
        ┌───────────┼───────────────┐
        ▼           ▼               ▼
   next action   review queue   TeachingContext → Mino
        │
        ▼
   decision log (what was chosen, and the reason in one sentence)
```

No third mastery table. `concept_mastery` stays the projection of record; the journey
projection becomes **an input to it** — one more evidence source, weighted like the others —
rather than a parallel truth.

## C. Data model — the minimum that closes the seam

Additive only, one migration:

- `student_concept_states.concept_id` — written at last, by resolving the journey's concept
  name against the workspace graph (`knowledge/resolution.py`), creating the concept when the
  journey is the first to name it. `mastery_events.concept_id` then stops being NULL.
  A journey grounded in a notebook inherits that notebook's workspace; one that is only a
  conversation lands in the account's first workspace, which every account gets at signup.
  An account with no workspace at all keeps the old behaviour — the link is skipped — because
  making a workspace appear in someone's library as a side effect of a chat turn is a product
  decision, not a repair.
- `evidence_key text unique` on `reviews` and `answers` (and the journey recall path): the
  client's idempotency key, so a replayed batch writes once (directive §150).
- `learning_decisions` — user, at, kind, chosen ref, candidates considered, reason, inputs
  (mastery/retrievability/urgency at decision time), engine version. This is directive §84 and
  the only way to answer "why did Sabelia do that" (§128, §334).
- index on `(journey_id, concept_name)` for `reproject`'s own query.

Not now: snapshot history of mastery rows (recomputable from the logs), a feature store, any
event bus.

## D. Event taxonomy

The taxonomy already exists in three dialects. Unify on the export shape
(`services/learning_export.py`), which is also the Sabelia `LearningEvent`:

`event_id · student_id · concept_id · item_id · timestamp · event_type(answer|recall|exposure)
· correct · score · difficulty · response_ms · hints · attempt · confidence · session_id ·
source · schema_version`

Two renames end the drift: the shadow bridge must send `response_ms` (not `elapsed_ms`), and
`score` must exist in the schema, since partial credit is real in NOEMA and the model should
see it. Evidence weight stays where it is — `KIND_WEIGHTS` in `student.py` and the grader
weights in `engines/mastery.py` — but both read from one settings object.

## E. Knowledge graph

`concepts` + `concept_edges` already carry `prerequisite_of / part_of / related_to /
contrasts_with`, a weight, an origin, DAG validation on write, and user edges that survive
re-ingestion. Soft and alternative prerequisites (§9) are expressible today as weights below 1.
What is missing is not the graph — it is that the conversational half never writes to it, and
that the learner-facing map (`ConceptTerrain`) draws curriculum order with no edges at all.

## F. Mastery V1

Keep `engines/mastery.py` exactly as specified in `mastery-engine.md`: Beta posterior with a
prerequisite prior, evidence weighted by recency × difficulty × grader trust × confidence,
competence × (λ + (1−λ)·retrievability), uncertainty from the posterior variance, calibration
tracked separately and never folded in. It already satisfies directives §12, §13 and §83.

The change: conversational evidence enters it as a graded event with grader kind `ai` and the
journey's own kind weight, once concepts have ids. The journey projection remains for the
lesson's own pacing, computed from the same events, and stops being a second answer to
"what does this learner know".

## G. Review V1

FSRS-4.5 is in place with per-user weight fitting and replay. The journey half gets
retrievability from the same engine instead of a 7-day constant, which is what makes
`NEEDS_REVIEW` — and the product's "review before you forget" — real rather than decorative.

## H. Next best action V1

`engines/scheduler.py` + `engines/path.py` already do candidate generation and greedy
selection under a time budget. What P1 adds is the part the directive insists on: every
returned block carries a `why`, and the choice, its rivals and its inputs are written to
`learning_decisions`. A recommendation that cannot be explained in one sentence is a bug.

## I. The Mino contract

The engine already builds a directive from typed parts (`<COURSE>`, `<KNOWLEDGE_STATE>`,
`<LEARNING_MEMORY>`, `<ACTIVE_SESSION>`, `<FOCUS_MODE>`). Formalise it as one object,
`TeachingContext`, built by one builder, with the fields the directive names (§230): concept,
mastery, confidence, weak prerequisite, recent errors, strategy, difficulty, max new concepts,
hint policy.

The rule that stays: **Mino proposes, Sabelia decides** (§232–233). The PEDAGOGY record is an
observation, not a mastery write — today a conversational turn grades itself from the same
generation that produced it, weighted 0.35 and trusted. It becomes a misconception *candidate*
and an `ai`-graded event, and it never resolves a misconception by itself.

## J. ML roadmap

1. **Now**: the export already produces sequences (`scripts/export-learning-events.py`). Log
   propensities (§199) as soon as any choice is made by a rule, so the policy can be evaluated
   later at all.
2. **Shadow**: fix the bridge's field names, give the service persistence and auth, deploy it,
   and *read* `decision["shadow"]` — offline, comparing the rule policy against the model on
   the same events (`scripts/shadow-eval.py` exists).
3. **Calibrate before believing**: the lab's own correction of 2026-09-09 is the precedent —
   a model that scores only on the events it finds easy is not better. AUC, log loss, ECE, and
   replay against history, or it does not ship.
4. **Then** the residual model, which is the first thing in this project to beat the feature
   table it starts from, behind a canary (§90) with the heuristic as fallback (§88, §158).

## Order of work

**P0 — close the seam (no new systems).** Every item is a defect with a line number, and
every fix is testable against the existing suites. Status as of 2026-09-22:

- **Done** — concept identity for journey states and their events (#175): a journey concept
  resolves against its workspace graph, so `mastery_events.concept_id` stops being NULL.
- **Done** — the displayed stage ages with the clock (#175): `current_stage` applies the
  staleness rule the router already used, so the map and the focus recap stop calling a fading
  concept "mastered".
- **Done** — batch reviews use the learner's fitted FSRS weights (#175).
- **Done** — the `mastery` stream event is consumed by the client (#176).
- **Done** — a review taken twice is one review: `client_event_id`, the unique constraint and
  the replayed answer (#177), and the client minting the key when the card is graded (#178).
- **Done** — journey recalls reach `concept_mastery` (#180). Giving the *state* an id was not
  enough: the card was still born with `concept_id=None`, so `record_review` skipped the
  projection. Cards now carry the id `StudentModel.ensure` resolves, and one written before
  that picks it up on its next recall, before the review is recorded.
- **Found on the way** (#180) — `TeachingSessions.history()` ordered a transcript by
  `created_at` alone. That column defaults to Postgres `now()`, which is transaction time, so
  turns written in one transaction shared a timestamp and came back in an arbitrary order: a
  returning learner's transcript, and therefore what the model is shown, could be scrambled.
  Fixed with the id tie-break `professor/memory.py` already used on the same table. It surfaced
  because linking a concept adds an insert, which was enough to disturb the arbitrary order —
  the test was right and the ordering was wrong.

**P1 — one reader, one decision log.** Status as of 2026-09-22:

- **Done** — `LearnerState` over both projections (#182): pure, in `engines/`, and deliberately
  not an average. The graph answers where it has evidence, the journey answers where the graph
  is silent, and where both speak the disagreement is reported rather than smoothed.
- **Done** — its first consumer, the tutor's `<KNOWLEDGE_STATE>` (#183). A learner who had
  drilled a concept to mastery on the review screen used to read to Mino as whatever that
  lesson's conversation happened to reveal.
- **Done** — its second, `/mastery` (#184), where concepts taught only in a lesson can now be
  surfaced. **Opt-in**: the default path is the previous query with an early return, because
  that screen has always meant "what the graph scored" and widening it silently would change
  what a learner sees without anyone choosing it.
- **Done** — sessions have outcomes: `start` returns the plan it stores (#179) and the review
  screen opens and closes one with what was actually answered (#181). The replay evaluation in
  `learning-engine.md` §8 finally has something to compare against.
- **Not built, deliberately** — the `learning_decisions` table this document asked for in §C.
  The data already persists: `build_plan` gives every block a `why` and the plan a `rationale`,
  `summarise()` stores them, and the move router's `reason` is already written to
  `teaching_turns.decision`. It was being computed and discarded, not missing, so #179 made the
  scheduler's half persist rather than opening a second home for facts already recorded. A new
  table remains the right answer only if a decision appears that neither surface stores.
- **Open** — `TeachingContext` as a typed object. The engine still assembles the directive from
  typed parts rather than one object with the fields §230 names. Nothing here addressed it.

**P2 — diagnostic and difficulty.** Adaptive placement by information gain (§14–§16), item
difficulty calibrated from real answers (§62), misconceptions escalated from confident errors
across turns rather than within one.

**P3 — models.** Shadow, replay, canary, and only then the trained predictor.

A correction to this plan as written: **most of P0 and P1 did not ship behind a flag, and this
document should not imply a rollback switch that does not exist.** Only the concept link is
gated, by `noema_sabelia_concept_link`. The rest were repairs to defects (an unordered
transcript, a double-applied review, a stage that could not age) or additions that change
nothing until called — a reader with no consumer, a field on a response, a session that is
opened where none was opened before. The one learner-visible widening, conversation-only
concepts on `/mastery`, is opt-in per request rather than per deployment, which is the finer
control of the two.

There is still no runtime flag system in either app, and this was not the work that should
introduce one.
