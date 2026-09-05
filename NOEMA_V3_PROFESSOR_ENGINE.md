# NOEMA V3 — Professor Engine

Noema teaches. This document is the map of how, after the V3 program: what a
turn does before the model speaks, what the model is and is not allowed to
decide, how a lesson is remembered without resending it, what the interface
draws from structured events, and what was measured. The audit that preceded
it is `docs/noema-v3-audit.md`; the character and brand lock are in
`NOEMA_V3.md` and `MINO_CHARACTER_SPEC.md`.

## The shape of a turn

```
learner message (+ learning_event)
        │
        ▼
POST /ai/professor ─ entitlement gate ─ session found/started ─ learner turn stored (commit)
        │
        ▼
ProfessorEngine.prepare
   journey        goal parsed once (economy) → curriculum built once (economy) → stored
   event          quiz verdict / check / assessment handed in → student model, streaks
   signal         patterns first ("não entendi", "já sei", "me testa" …), else one economy call
   move           decide(signal, situation): 12 moves, strategy ladder, tier, Mino state
   pre-work       EXAM → checkpoint (compaction, cards, paper) · FLASHCARD → cards · KNOWS → skip lesson
   prompt         [system: persona + mode + principles]  ← identical every turn, cacheable
                  [stored turns fitted to the transcript budget]
                  [<MATERIALS> when a notebook has some]
                  [one directive: move layer · strategy · concept · course · knowledge · memory · session]
        │
        ▼
ProfessorEngine.stream
   events         session · journey · move · intent · mino · (memory · flashcards · checkpoint) · sources
   tokens         PEDAGOGY record split off → learning blocks held back and validated → citations checked
   block events   quiz · check · layers · steps · compare · flashcard (public form; rubrics stay server-side)
   done           usage (incl. cached tokens) + the context report per component
        │
        ▼
after done (own DB session, committed, every step optional in failure)
   turn stored with blocks, decision, pedagogy, token estimate
   PEDAGOGY → journey.current_concept, student model event (conversation, weakest weight), graph evidence
   lesson advances when every concept in it has been shown
   cards for a concept just shown understood (moderate/strong) and not yet carded → flashcards event
   compaction when the active window is large → memory event
   mastery · journey events, then mino idle
```

The model never chooses the move, the UI or the animation. It teaches inside
a directive the code wrote, and reports what it did in the PEDAGOGY record.

## The twelve moves (`noema/professor/moves.py`)

| Move | When the router picks it | Tier | Mino |
|---|---|---|---|
| TEACH | continue the lesson; first contact (ends with a check) | standard | teaching |
| QUESTION | three teaching moves without the learner showing anything | standard | questioning |
| CORRECT | "não entendi"; a wrong quiz/check answer; an assessment left weak concepts; the answer to last turn's question is being graded | premium | correcting (concerned after two wrong on the same concept) |
| REVIEW | (reserved for the router's review rule; prompt layer ready) | standard | reviewing |
| EXAMPLE | "dá um exemplo" | standard | teaching |
| PRACTICE | (router alias of QUIZ for practice requests) | standard | questioning |
| FLASHCARD | "cria flashcards" — cards written before the reply | economy | writing |
| QUIZ | "me testa"; a checkpoint that could not write a paper | standard | questioning |
| EXAM | checkpoint due (concepts since last ≥ N, at a boundary) or "quero uma prova" | economy | exam |
| MOTIVATE | "tô cansado" — close the loop | economy | happy |
| SUMMARIZE | "resume" | standard | teaching |
| ADVANCE | "já sei" (skips the lesson); a right answer; "aprofunda" | standard | teaching |

Order of authority: facts the code knows (event, last move) → unambiguous
phrasings (pt/en/es patterns) → one economy classification → lesson state
(remediation, checkpoint due, first turn, since_check). Strategy switching is
a ladder — definition → analogy → scenario → worked example → contrast →
prerequisite → socratic — that never returns to the rung that failed.

## The student model (`student.py`, migration 0019)

- `learning_journeys`: the goal in the learner's words, the parsed subject /
  objective / level / depth / prerequisites, the plan (modules → lessons →
  concepts, statuses), the current position and concept, the profile (L3),
  checkpoint counters, pending remediation.
- `mastery_events` (append-only): every showing — `conversation` 0.35,
  `quiz` 0.7, `flashcard` 0.8, `check` 1.0, `teach_back` 1.2, `assessment`
  1.1 — with a score 0..1.
- `student_concept_states` (projection): recency-weighted score, evidence
  counts, streaks, open misconceptions, the stage the learner sees:
  `not_started · introduced · learning · uncertain · mastered · needs_review`.
  Mastered needs three showings including one that is not the professor's
  own reading of a chat line. Reading is never showing.

Concepts are keyed by name within a journey, so a subject learned purely in
conversation has a state for every concept the lesson touched; when the
material graph knows the same name, the existing `Explanation` /
`ConceptMastery` path is also written (unchanged from V2).

## Memory (`memory.py`, `budget.py`)

| Layer | Where | Rides in the prompt as |
|---|---|---|
| L0 active context | `teaching_turns` with `archived_at IS NULL`, fitted newest-first to `noema_professor_transcript_budget` (3 500) | the chat messages |
| L1 session summary | `memory_summaries(level=session)` written by `ContextCompactor` when the window exceeds 4 500 tokens or 24 turns (6 newest kept) or at a lesson boundary | `<LEARNING_MEMORY>` |
| L2 learning memory | the summary's mastered / uncertain / misconceptions folded into the student model | `<KNOWLEDGE_STATE>` |
| L3 profile | `learning_journeys.profile.patterns`, deduplicated, six at most | one line in the knowledge block |
| L4 knowledge state | `student_concept_states` | `<KNOWLEDGE_STATE>` (current lesson's concepts first, then the weakest) |
| L5 archive | the turns themselves, `archived_at` set — never deleted | nothing |

Hierarchical: four session summaries fold into one module summary without a
model call (a union of the structured fields); older module summaries are
superseded, so the prompt reads at most one module summary plus the open
session summaries. After a compaction the directive carries the hand-off form
(WHO · WHAT · WHERE · KNOWS / STRUGGLES · JUST TAUGHT / NEXT).

Compaction is a technical decision; a checkpoint is a pedagogical one
(`checkpoint.py`). They can coincide. A large context alone never forces an
exam.

## Flashcards and assessments

- `flashcards.py`: 2–4 atomic cards per concept on the economy tier, stored
  as `cards` rows with `journey_id` and `concept_name`, unapproved. The first
  in-lesson recall approves the card (the reading the approval rule asks for),
  writes the FSRS review through the same `record_review` the review screen
  uses, and a `flashcard` mastery event. The in-chat deck and `/review` are
  one deck. Triggered when a concept is shown understood with moderate or
  strong evidence, when the learner asks, and at checkpoints for concepts
  that landed and have none.
- `assessment.py`: micro (≤3) or checkpoint (≤6) papers — mcq, true/false,
  short, ordering, open — with answers and rubrics server-side; `public_view`
  strips them. Closed types are graded with the notebook questions' own
  deterministic graders; open answers by the `grade.open` rubric prompt on
  the economy tier (0.5 when no grader is available, never wrong-by-default).
  Per-concept results feed the student model; concepts under 0.5 become
  `pending_remediation`, and the next turn is a CORRECT move with the results
  in the directive — the remediation loop.

## Events and endpoints

SSE events on `POST /ai/professor`: `warning` · `session` · `journey` ·
`move` · `intent` (legacy label) · `mino` · `memory` · `flashcards` ·
`checkpoint` · `sources` · `token` · `block` · `done` · `mastery` · `journey`
· `mino`. `flashcards`, `memory`, `mastery` and the second `journey` may
arrive after `done`; the client frees the composer at `done`.

`ChatIn.learning_event` (`kind: quiz | check | flashcard | assessment`,
concept, correct, question, chosen, assessment_id) reports what the interface
saw. The stored transcript is the server's; the client sends only the new
message.

New reads/writes (`noema/api/v1/journeys.py`): `GET /ai/journeys/latest`,
`GET /ai/journeys`, `GET /ai/journeys/{id}` (plan, position, concept states,
memory), `POST /ai/journeys/{id}/cards/{card}/recall`, `GET
/ai/assessments/{id}`, `POST /ai/assessments/{id}/submit`. Admin: `GET
/admin/professor-economy`.

## Token economy

- `AIUsage` gains `cached_tokens`, `feature`, `session_id`; Anthropic's
  `cache_read_input_tokens` is recorded; pricing bills cached input at the
  tier's cached rate. Every Professor call is tagged (`professor.teach`,
  `.parse_goal`, `.curriculum`, `.route`, `.compact`, `.flashcards`,
  `.assessment`, `.grade`).
- The system block is byte-identical on every turn of every lesson (persona +
  mode + principles); everything that changes rides in the final directive
  message — so the provider's prompt cache stays warm across turns and users.
- Model router: classification, routing, goal, curriculum, compaction, cards
  and papers on the economy tier; teaching on standard; correction on premium.
- The admin dashboard shows tokens and cost by feature, cache hit rate,
  compaction savings, cost per lesson and per active learner, from the rows.

Measured offline on the real prompt (`scripts/eval-economy.py`,
`evals/economy/v3-vs-v2.md`), prompt tokens per turn, chars ÷ 4:

| Exchange | V2 (resend all) | V3 (stored + memory) | Reduction |
|---:|---:|---:|---:|
| 1 | 2 155 | 2 305 | −7 % |
| 10 | 5 629 | 5 779 | −3 % |
| 20 | 9 489 | 5 855 | 38 % |
| 50 | 21 069 | 3 925 | 81 % |
| 100 | 40 369 | 5 855 | 86 % |

V3 is slightly more expensive for the first ten exchanges (the directive
costs ~150 tokens; the goal and curriculum calls are two extra economy calls
per journey) and bounded afterwards, where V2 grew linearly. The extra calls
per lesson are bounded and visible per feature; nothing is estimated in the
dashboard.

## Verified

Locally against Postgres 14 + pgvector 0.8 (`alembic upgrade head`,
`alembic check` clean) and the mock/scripted providers, no model called:

| Check | Where |
|---|---|
| First message → journey with parsed goal, plan, first concept; `session · journey · move · intent · mino` before the first token; system block starts with the persona; directive carries the move layer and the course | `tests/test_db_professor_engine.py` |
| Second turn is built from stored turns (system, learner, Mino, learner, directive) | same |
| A `noema:quiz` fence becomes a `block` event; no fence or PEDAGOGY in tokens; the turn stores its blocks; `last_move = question`; the record moves `current_concept`, introduces concepts, writes a `conversation` event, and cards for the concept that landed | same |
| A wrong quiz answer routes to CORRECT with the next strategy; a right one to ADVANCE; both are `quiz` mastery events | same |
| "Não entendi." and "Isso eu já sei." are routed without a model call; "já sei" skips the lesson | same |
| A long lesson compacts: summary row, turns archived not deleted, hand-off directive, ≤5 chat turns sent, profile and misconceptions folded in | same |
| Recalling a lesson card approves it and writes `conversation → flashcard` events | same |
| A checkpoint writes a paper with answers stripped; grading yields the weak list; the next turn is CORRECT with the results | same |
| Every call recorded with feature, session and cached tokens | same |
| Router, block filter, budget fit, projection, curriculum, memory validation, grading: 44 unit tests | `tests/test_professor_engine_units.py` |
| The rest of the API suite against the same database | 1 204 passed (Redis-only tests need a Redis) |
| Web: segmented replies, quiz → learning event, checkpoint paper drawn without answers, admin economy panel, landing path beat | vitest, 122 tests |

Not verified here: a real model's behaviour under the move layers (the
persona and principles evals from V2 still apply; the V3 eval script runs
against production once deployed), and the production migration.

## Not done

- REVIEW as a router rule from `needs_review` states (the prompt layer and
  the stage exist; the trigger does not).
- Teach-back as a scheduled move (the `check` block supports `kind:
  teach_back`; the router does not yet ask for one periodically).
- Semantic retrieval of memory (summaries are read newest-first within a
  budget; no embeddings — the structured rows made it unnecessary so far).
- Journeys on the home and progress screens (the API exists; the screens
  still read sessions).
- Voice input and attachments; Mino inside a diagram block; mobile keyboard
  choreography (carried over from `NOEMA_V3.md`).
- Official character renders (`MINO_CHARACTER_SPEC.md`).
