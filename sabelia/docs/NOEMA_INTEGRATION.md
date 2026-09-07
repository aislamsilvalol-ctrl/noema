# Sabelia ↔ NOEMA — Phase 0 audit and the integration plan

What the product records today, what a learner model needs, and the
smallest changes that close the gap. This is the boundary between the
open-source engine and the commercial product: everything here about
NOEMA's tables and routes stays in NOEMA; everything the engine needs is
expressed as the `LearningEvent` schema.

## What exists (audit of `apps/api`, 2026-09-06)

NOEMA has two parallel evidence trails.

**Trail A — study (rich, keyed by UUID).** `Review` (flashcard reviews:
rating 1–4, `elapsed_ms`, learner `confidence` 1–5, FSRS state before and
after, timestamp), `Answer` (graded questions: `is_correct`, partial
`score`, `confidence`, `elapsed_ms`, grader, timestamp), `Question`
(difficulty enum), `Card`/`CardSchedule` (FSRS-4.5: stability, difficulty,
due), `ConceptMastery` (a Beta-Bayesian projection with `model_version`),
and a real concept graph: `Concept` (per workspace, `difficulty_prior`,
embedding) and `ConceptEdge` (`prerequisite_of`, `part_of`,
`related_to`, `contrasts_with`, weight).

**Trail B — professor (poor, keyed by name).** `MasteryEvent`
(`concept_name` as free text, `kind` in {conversation, quiz, check,
flashcard, assessment}, `score` 0–1, `weight`, JSON `detail`, optional
`turn_id`, timestamp) and `StudentConceptState` keyed by
`(journey_id, normalized_name)`. The Professor Engine writes all its
evidence here through `StudentModel.record()`, and projects mastery with a
recency rule by *position* (`0.75^age`, weights per kind), not by time.

**Consequences for a learner model.**

| Signal | Trail A | Trail B (most of the volume) |
|---|---|---|
| Stable concept id | yes (`Concept.id`, per workspace) | **no** — free text per journey; the same concept in two journeys is two skills |
| Item id | `card_id`, `question_id` | only inside JSON `detail` for flashcards; none for quiz/check |
| Difficulty | `Question.difficulty`, `CardSchedule.difficulty` | **none** |
| Correctness | `is_correct`, rating | `score` 0–1 (scale differs by kind) |
| Latency | `elapsed_ms` | **none** (the recall route receives it and drops it) |
| Hints / attempts | `reps`/`lapses` on schedules | **none** |
| Stated confidence | yes | **none** |
| Session id | on assessments and usage | only `turn_id`, optional |
| Model version | `ConceptMastery.model_version` only | none |
| Pseudonymous id | **none** — every row has `owner_id → users.id` (email in clear) | same |

Two blockers stand out: **no stable concept id on `MasteryEvent`**, and
**no latency/difficulty/confidence on the conversational evidence**.

## The plan (product side, small)

1. **Resolve concepts to ids.** When the Professor Engine records
   evidence, resolve `concept_name` to a `Concept` row (create it in the
   journey's workspace if missing, status `candidate`) and store
   `concept_id` on `MasteryEvent` and `StudentConceptState`. One
   migration, one lookup in `StudentModel.record()`.
2. **Carry the signals that exist.** The recall route already receives
   `elapsed_ms`; write it to the event. Quiz blocks know which option was
   chosen and can carry a `difficulty` set by the block generator; check
   blocks can ask for stated confidence (the flashcard path already does).
   Add `elapsed_ms`, `difficulty`, `confidence`, `item_id` (the block id)
   and `session_id` to `MasteryEvent`. Make `kind` an enum.
3. **Version the projection.** Stamp `model_version` on
   `StudentConceptState` when `project()` runs, so a later Sabelia
   projection can be compared with today's rule on the same events.
4. **Export pseudonymously.** A job that emits `LearningEvent` JSONL with
   `student_id = HMAC(secret, user_id)`, one file per day, from both
   trails: `Review` → `recall` events, `Answer` and quiz/check
   `MasteryEvent`s → `answer` events, teaching turns that introduced a
   concept → `exposure` events. Identity never leaves the product.
5. **Consume, with a fallback.** The Professor Engine asks the Sabelia
   service for `state` and `recommend` before choosing a move; the
   recommendation and its reason codes are added to the turn's decision
   record (`TeachingTurn.decision`), and the existing rule-based router
   remains the path when the service is absent or slow (a 150 ms budget).
   The move stays the Professor's; Sabelia says *what the learner
   needs* ("REVIEW defense_mechanisms: recall_predicted 0.54,
   days_since_practice 8, prerequisite_weak unconscious"), the Professor
   says it ("Antes de continuarmos, quero testar uma coisa…").

## What must not cross the boundary

NOEMA keeps: users, e-mails, conversations, prompts, billing, its own
tables. Sabelia receives: pseudonymous events. Nothing in the engine
reads NOEMA's database; the adapter is a JSONL file the product writes.

## Status (2026-09-07)

- Steps 1–3: **done in the product** (migration `0022_learning_signals`):
  `MasteryEvent` carries `concept_id` (from the linked state), `item_id`,
  `elapsed_ms`, `difficulty`, `confidence`, `session_id`; the quiz, recall,
  flashcard and assessment paths fill what they know; `LearningEventIn`
  accepts `elapsed_ms` and `confidence` from the interface, and the web
  client measures time-to-answer from the end of Mino's reply;
  `StudentConceptState.model_version` is stamped `project-v1`. Resolving
  free-text names to `Concept` rows across journeys remains open.
- Step 4: **done** — `noema/services/learning_export.py` and
  `scripts/export-learning-events.py` emit LearningEvent v1 JSONL with HMAC
  pseudonyms and no text (`NOEMA_EXPORT_SECRET`, 16+ characters).
- Step 5: not started. The V1 gate (a gain over the logistic baselines on a
  public dataset) is met on Duolingo (2026-09-07, `benchmarks/README.md`),
  so the engine has earned a *shadow* integration: predictions logged next to
  the heuristic's, never shown, until NOEMA's own exported events (step 4)
  are numerous enough to run the same benchmark on them.

## Order of work

Steps 1–3 are a single migration plus small edits in `professor/student.py`,
`professor/engine.py`, `professor/flashcards.py`; step 4 is a worker job;
step 5 waits for V1 of the engine to show a gain over the heuristic on a
public dataset — the product does not integrate a model that has not
earned it.
