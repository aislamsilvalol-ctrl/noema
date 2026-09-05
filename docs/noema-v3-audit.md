# NOEMA V3 — Professor Engine audit (Phase 0)

Date: 2026-09-05. Read-only pass over the repository at `c3af2a2`, before any
V3 code. Every claim below is grounded in a file that was read in full or
measured; nothing here was inferred from a model call. Where the answer is
"we cannot know from the code", it says so.

The question this audit answers is the brief's: *why does Noema still feel like
a chatbot with a mascot, what is spent per turn, and what must be preserved
while the Professor Engine is built on top.*

---

## 1. What exists

### Architecture

| Layer | Where | State |
|---|---|---|
| Web | `apps/web` — Next 15, React 19, Tailwind tokens (`data-design="v2"` default), vitest + testing-library | Working, deployed (Railway `web`) |
| API | `apps/api/noema` — FastAPI, SQLAlchemy async, Alembic 0001–0018, structlog, dramatiq worker | Working, deployed (Railway `api`, stamped by `NOEMA_GIT_SHA`) |
| Data | Postgres 16 + pgvector (HNSW), Redis (rate limits, embedding cache, demo allowance) | Working |
| AI | `providers/` (anthropic, openai, ollama, gateway, mock), `prompts/` (versioned files), `services/professor*.py`, `services/teaching_*.py` | Working; see §3 |
| Learning | `engines/` (fsrs, mastery, scheduler, path, replay), `study/` (review, mastery, questions, grading, exam, correction, socratic, feynman) | Working, well tested |
| Knowledge | `knowledge/` (extraction, resolution, graph) — concepts extracted **from uploaded material** | Working, material-bound |

### The Professor today (`api/v1/ai.py`, 829 lines)

`POST /ai/professor`:

1. Entitlement gate (`EntitlementsService`), then the teaching session is
   started or resumed (`TeachingSessions.start_or_resume`), the learner turn
   written and **committed** before streaming (a real production fix, keep it).
2. One **economy-tier structured call** classifies the last message into six
   intents (`explain · deepen · summarize · quiz_me · create_flashcard ·
   create_exam`); `quiz_me/create_flashcard/create_exam` need a notebook with
   material and otherwise fall back to `explain`.
3. `_dispatch_stream` builds the prompt: `mino.persona` → mode prompt
   (`tutor.explain` or `rag.*`) → `teaching.principles` (arc, diagnosis,
   strategy switching, TEACHING TOOLS, PEDAGOGY record) as **one system
   message**, then **the whole transcript the browser sent**, then optional
   `<MATERIALS>`, `<STUDENT_MEMORY>` (notebook-only), `<ACTIVE_SESSION>`
   (the session's state).
4. The reply streams through `SidecarFilter` (strips the trailing
   `<PEDAGOGY>{json}</PEDAGOGY>`) and `CitationFilter`; the shown text is stored
   as a `TeachingTurn` on a separate DB session after `done`; validated
   PEDAGOGY fields fold into `TeachingSession` (`apply_pedagogy`) and, when
   the named concept exists in the graph, one `Explanation(kind=CONVERSATION)`
   row is written and mastery recomputed.

Sessions are real and remembered (`teaching_sessions`, `teaching_turns`,
`GET /ai/sessions/{id}`, `/ai/sessions/latest`); the client stores the id in
`sessionStorage` and resumes on reload.

### Mino

- `components/mino/machine.ts` — 13 states + 3 aliases, `EVENT_TO_STATE`,
  `TRANSIENT`, `POSES`. `MinoController.tsx` — provider, springs, idle life,
  quality tiers. `rig/MinoRig.tsx` — **provisional** layered SVG.
  `MinoPresence.tsx` — presence levels on Professor screens.
- `public/brand/mino/*.svg` — six hand-drawn placeholder poses from an
  earlier phase, still referenced by `src/brand/mino.ts` but by **no live
  component** (the landing V3 uses the rig). Dead weight, safe to remove or
  keep as history.
- **The reference art arrived with this brief** (the `@noemalearn` Instagram
  posts): a cream, soft, droplet-shaped body with a single curl on top, very
  large glossy black eyes with white highlights, a small mouth, stubby arms
  and feet, an orange hoodie carrying the white NOEMA mark, dark trousers in
  the standing pose. The current rig has the right palette and layer plan
  but the wrong silhouette (a round head on an egg body). §6 below.

### Flashcards, questions, exams, reviews

- Cards: `Card` (requires `notebook_id`), FSRS `CardSchedule`, append-only
  `Review`, AI cards inert until `approved_at` (`record_review` enforces it).
  Review UI at `/review`; ratings Again/Hard/Good/Easy already map to the
  brief's ERREI/DIFÍCIL/LEMBREI/FÁCIL.
- Questions: `Question` (requires `notebook_id`), seven types, deterministic
  grading for five (`study/grading.py`), AI rubric grading for open answers,
  `Mistake` rows with misconception flag and drills (`study/correction.py`).
- Exams: `Exam` over a notebook's questions, timed, graded at submit, per
  concept results.
- Mastery: `engines/mastery.py` — Beta-posterior competence × FSRS
  retrievability, uncertainty, calibration; `ConceptMastery` projection;
  `GET /study/mastery`; the progress page shows provisional numbers honestly.

All of it is **material-bound**: a card, a question and a concept only exist
under a notebook that had something uploaded. A learner who says "Quero
aprender Freud" and never uploads anything gets **no cards, no questions, no
concepts, no mastery** — `record_conversational_evidence` looks the concept
up by name and returns `None` when the graph does not have it, which is
always, for a fresh subject.

### Landing

`components/landing/v3/LandingV3.tsx` — five beats (ASK/LEARN/PRACTICE/
ADAPT/REMEMBER) + close, live demo through `POST /ai/demo` (rate-limited),
subject banks, one shared Mino. Missing the brief's second beat ("Eu
transformo em um caminho" — the curriculum appearing) and the sixth ("Eu
evoluo com você" — knowledge state), and the hero figure is the provisional
rig.

### Brand

`components/brand/Wordmark.tsx` is the only place the name is drawn:
"NOEMA" in Newsreader (the display face), tracked capitals. **There is no
logo file in the repository** — no SVG, no PNG, no symbol. The Instagram
posts show the marketing logo: an orange three-lobed mark and "NOEMA" in a
bold geometric sans. That asset does not exist here and, under the brief's
rule (no redesign, no re-creation, no AI generation), it cannot be redrawn
from a screenshot. `LOGO_LOCK = TRUE` therefore means: `Wordmark.tsx` is not
touched in V3; when the official SVG is added at
`apps/web/public/brand/logo.svg`, that component becomes an `<img>` of it in
one change. Nothing in V3 depends on which of the two it is.

---

## 2. What works and must be preserved

- **Session persistence and the commit-before-stream fix** (`ai.py`
  `professor_chat`, `_record_noema_turn`): hard-won, observed in production.
- **PEDAGOGY sidecar** (`teaching_policy.py`): metadata on the same
  completion, validated, never shown. V3 extends the record; it does not
  replace the mechanism.
- **Persona + principles as separate files** composed at request time.
- **Mastery engine** (`engines/mastery.py`) and FSRS: deterministic, tested,
  replayable. V3 must feed them, not fork them.
- **Append-only evidence** (`reviews`, `answers`, `explanations`): every
  derived number is rebuildable. The new student model follows the same
  rule (events → projection).
- **AI cards are inert until read** (`Card.approved_at`). Mino's own cards
  respect it: the first in-chat recall *is* the reading.
- **Gateway** (retry, per-task timeouts, budget guard, usage recording),
  **prompt caching** of the system block on Anthropic, the **mock provider**
  and the DB test fixtures (rolled-back transactions; `NOEMA_REQUIRE_DB=1`
  in CI).
- **Tenancy**: every table is `OwnedEntity`; every query scopes `owner_id`.
- **Design tokens, the black rail, the Wordmark, Mino's controller/machine
  contract** (UI emits product events; nothing names an animation).
- `POST /ai/chat` (manual modes), notebooks, notes, imports, exports,
  billing, admin — untouched by V3.

---

## 3. What is bad — the "chatbot" UX, traced

1. **The client is the memory.** `ChatIn.messages` (up to 100 × 32 000
   chars) is resent on every turn and forwarded whole to the model
   (`_dispatch_stream`: `messages += [... for m in payload.messages]`). The
   server stores the transcript but never *reads* it for the prompt. Context
   grows linearly with the conversation; there is no compaction, no summary,
   no archive. This is the single largest token cost and the reason a long
   lesson gets slower and more expensive every turn.
2. **One monolithic LLM turn decides everything.** Apart from the six-way
   intent classifier, the model itself decides whether to teach, ask, check
   or advance, and reports it afterwards in PEDAGOGY. There is no router that
   *chooses a move before the call* from the session state (error streak,
   checkpoint due, concept just confirmed), so the lesson has no arc the
   code can enforce — only one the prompt asks for.
3. **No curriculum.** `TeachingSession.plan` is a flat list of topics the
   model writes into PEDAGOGY. Nothing turns "Quero aprender Freud" into
   modules → lessons → concepts with prerequisites, and nothing tracks where
   the learner is against it. `learnNew` (the create-learning flow) shows a
   *drawn* path (`PathStrip`) that is not real.
4. **No student model without material.** Mastery lives on `Concept` rows,
   which only extraction from uploads creates. Conversation-only learning
   produces `understanding` notes (max 6) and `misconceptions` (max 4) on the
   session — and nothing per concept, nothing across sessions, nothing the
   review or progress screens can show.
5. **Flashcards, quizzes and exams are separate rooms.** `quiz_me` and
   `create_flashcard` generate items into a notebook and reply "3 perguntas
   criadas · Abrir quiz". The learner leaves the lesson to practise. The
   in-reply `noema:quiz` / `noema:flashcard` blocks exist but are parsed
   **client-side by regex on generated text**, the quiz result is not
   recorded anywhere, and the flashcard block never becomes a scheduled card.
6. **Nothing is ever generated for the learner unprompted.** No cards after a
   concept lands, no micro-check after an explanation unless the model
   happens to write one, no checkpoint. The product waits to be asked.
7. **Mino's state is inferred by the client from the stream** (thinking →
   teaching → idle) plus quiz clicks. The server, which knows whether it is
   correcting, questioning or celebrating, never says so.
8. **Quick actions after every prose reply** ("Me teste · Aprofundar …") are
   the chatbot tell: they are the same four buttons regardless of where the
   lesson is.

## 4. What is wasting tokens — measured

Measured with the prompt loader on this commit (chars ÷ 4 as the estimate the
codebase itself uses in `retrieval/grounding.py`).

| Component | Chars | ≈ tokens | Per turn? |
|---|---|---|---|
| `mino.persona` | 1 864 | 466 | yes |
| `tutor.explain` (+ identity clause) | 1 038 | 259 | yes |
| `teaching.principles` (tools + PEDAGOGY spec) | 5 196 | 1 299 | yes |
| **System block total** | **8 098** | **≈ 2 024** | yes — cacheable on Anthropic (`cache_control`), *not* measured as cached: `Usage` has no cache field |
| `professor.classify_intent` (economy call) | 1 307 | 326 | yes, second call |
| Transcript resent | grows | — | **all of it, every turn** |
| `<ACTIVE_SESSION>` | ≤ ~600 | ~150 | yes, bounded |
| `<STUDENT_MEMORY>` | ≤ ~900 | ~220 | notebook only |
| PEDAGOGY record (output) | ~500–700 | ~150 | yes, output tokens |

Real transcripts (`evals/teaching/*.json`): Mino's replies run 1 100–2 150
chars each on the V3 persona (≈ 300–540 tokens). With the learner's lines, a
lesson adds roughly **400–600 tokens of transcript per exchange**, all resent.
After 20 exchanges the transcript alone is ≈ 10 000 tokens per turn, after 50
≈ 25 000, after 100 the request approaches the 100-message cap and the
smaller providers' context windows. None of it is summarised.

Other waste and blind spots:

- `AIUsage` records prompt/completion tokens and cost per `task`, but **not
  cached tokens, not the feature, not the session**. Cache hit rate, cost
  per lesson and cost per active learner cannot be computed from what is
  stored; `admin_intelligence.py` says so itself (`not_yet_tracked`).
- `PricingService.cost_cents` ignores `cached_input_cost_per_million_usd`
  even though the column exists — cached input is billed at full price in
  the dashboard.
- The stream path (`gateway.stream`) has **no retry**; a transient failure
  costs a whole turn (already documented in `NOEMA_AI_ARCHITECTURE_AUDIT.md`).
- The eval script spends real model calls; there is **no mocked long-journey
  test**, so the cost of a 50-turn lesson has never been measured before or
  after any change.

## 5. What can be refactored (and how V3 will)

| Today | V3 |
|---|---|
| Client resends transcript; server forwards it | Server builds L0 from **stored, non-archived turns** under a token budget; the client sends only the new message (history accepted for compatibility, ignored beyond the last message once a session exists) |
| No summaries | `memory_summaries` (session → module → course), written by a `ContextCompactor` on an economy model when the active window crosses a threshold **or** a lesson boundary passes; archived turns stay in `teaching_turns` with `archived_at` set (L5), never deleted |
| Six intents, decided by one LLM call | `ProfessorRouter`: deterministic rules from session state first (checkpoint due, error streak, "não entendi", "já sei", quiz answered), then one economy classification into the brief's twelve moves; the move selects prompt layer, tier, block requirement and Mino state |
| Flat `plan` in PEDAGOGY | `learning_journeys` with a parsed `LearningGoal` and a `CoursePlan` (modules → lessons → concepts, macro + next steps only); the session points at the journey and its current lesson |
| Mastery only on material concepts | `student_concept_states` per journey, keyed by concept name, projected from append-only `mastery_events` (quiz, teach-back, flashcard, exam, conversation); linked to `Concept`/`ConceptMastery` when the graph knows the name |
| Blocks found by client regex | Server `BlockFilter` holds back `noema:` fences, validates the JSON against a per-tool schema, emits `event: block`; the client renders segments (text \| block) in arrival order. Malformed → dropped and logged, never raw |
| Cards need a notebook | `cards.notebook_id` nullable, `cards.journey_id` + `cards.concept_name`; Mino's cards arrive as an in-chat `FlashcardDeck`; the first recall approves the card and writes the FSRS review + a mastery event |
| Exams need a notebook | `assessments` per journey (micro-quiz / checkpoint), questions with answers server-side only, deterministic grading for closed types, AI grading for open, per-concept results feeding the student model |
| Mino state inferred client-side | `event: mino {state}` derived from the router's move (never from the model's text) |
| `AIUsage` without cache/feature | `cached_tokens`, `feature`, `session_id` columns; pricing uses the cached rate; admin dashboard gains tokens by feature, cache hit rate, compaction savings, cost per lesson and per active learner |

Nothing above deletes a table or an endpoint. `POST /ai/chat`, the notebook
Professor, `/review`, `/progress`, exams over notebooks all keep working.

## 6. Mino — what the reference settles

The Instagram posts are the visual source of truth. Against them, the current
rig (`rig/MinoRig.tsx`) gets these corrections in Phase 7, all inside the
existing layer contract (same props, same controller, same CSS hooks):

- **Silhouette**: one continuous soft body — wide at the base, narrowing to a
  rounded top with a single small curl pointing back-right — not a separate
  round head on a body. The face sits in the upper half.
- **Eyes**: very large, tall ovals (not circles), glossy black, two white
  highlights (a large one upper-left, a small one lower-right). Eyelids are
  body-coloured.
- **Mouth**: tiny, low, a short curve; open only as a small dark oval.
- **Cheeks**: a faint warm blush.
- **Limbs**: short rounded arms and stubby feet in the body colour.
- **Hoodie**: orange (`#f26b1d` family, lit to `#ff8f47`, shaded to
  `#c9500f`), covering the lower body, with the white NOEMA mark on the
  chest; dark trousers in the standing pose. The hoodie is the only garment.
- **Palette**: cream body (`#fbf6ec` → `#efe6d6` → `#d9ccb6`), black eyes,
  orange hoodie, white mark — matches the spec already written.

No new character, no extra props, no image-model frames. The rig is still a
drawing of the reference, not the reference itself; official vector renders
remain the right long-term replacement (see `MINO_CHARACTER_SPEC.md`).

## 7. Risks and constraints for the build

- **DB tests only run in CI** (no local Postgres). Everything that touches
  the schema is verified by the CI run, not locally; unit tests for the pure
  parts (router, compactor decisions, grading, budget) must not need a DB.
- **`alembic check` in CI**: every model change needs a migration that
  matches exactly; enum extensions use `ALTER TYPE … ADD VALUE` (0018's
  pattern).
- **`openapi.json` must be regenerated** (`scripts/openapi.sh`) for every
  schema change or CI fails.
- **Coverage gate 80 %** on the API.
- **No real model calls in tests**; the mock provider and scripted fakes are
  the pattern (`tests/test_db_professor.py`).
- **Provider text never reaches the learner** (`lib/errors.ts`); new events
  keep that rule.
- The brief's own priority order applies when time is short: teaching
  quality → memory/continuity → adaptive practice → Mino → token economy →
  landing.

## 8. Phase plan (what follows this document)

Status 2026-09-05: phases 1–10 shipped in `04fd01f` and `451bfb7`; see `NOEMA_V3_PROFESSOR_ENGINE.md` for what was verified and what is not done.

| Phase | Deliverable |
|---|---|
| 1 Professor Engine | `noema/professor/` package: `LearningIntentParser`, `CurriculumEngine`, `ProfessorRouter` (moves), prompt layers per move, structured SSE events (`mino`, `block`, `mastery`, `flashcards`, `checkpoint`, `memory`), server-side `BlockFilter` |
| 2 Student model | `learning_journeys`, `student_concept_states`, `mastery_events`; `MasteryEngine` projection; knowledge graph per journey; `GET /ai/journeys/{id}` |
| 3 Flashcards | `FlashcardEngine`: atomic cards after a consolidated concept; `cards.journey_id`; in-chat recall endpoint (approve + FSRS review + mastery event) |
| 4 Assessment | `assessments`: micro-quiz and checkpoint exams; grading; remediation loop into the router |
| 5 Memory | Server-built L0; `memory_summaries`; `ContextCompactor` with thresholds; hierarchical fold; retrieval of relevant state |
| 6 Token economy | `TokenBudget`, context report per turn, `AIUsage.cached_tokens/feature/session_id`, cached pricing, admin dashboard rows |
| 7 Mino runtime | New states (questioning, correcting, reviewing, exam, concerned), server `mino` events, rig redrawn to the reference |
| 8 Learning UI | Segmented turns, `QuizCard`, `FlashcardDeck`, `ExamView`, `ConceptCheck`, `ProgressCheckpoint`, curriculum strip, contextual actions |
| 9 Landing V3 | Six beats, the curriculum beat, knowledge-state beat, hero on the new rig; logo untouched |
| 10 Evaluation | Mocked 60-turn journey test (continuity after compaction), token comparison current vs V3 at 20/50/100 turns, pedagogical scenario tests, smoke against production |
