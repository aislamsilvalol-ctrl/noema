# NOEMA Memory Architecture Audit — Phase 10

Date: 2026-09-02
Scope: what "memory" means in the codebase today — `noema/services/professor_memory.py`
and what it draws on (`ConceptMastery`, `Mistake`, the concept graph, `engines/mastery.py`,
`engines/fsrs.py`) — mapped against the brief's own four-tier framework (transient /
session / learning / long-term), plus confidence and decay. Read-only, file:line-grounded
audit. No code changes, no LLM API calls were made while producing this document.

Files read in full: `noema/services/professor_memory.py` (148 lines), `noema/engines/mastery.py`
(243 lines), `noema/engines/fsrs.py` (166 lines), `noema/study/mastery.py` (`recompute_mastery`,
`recompute_for_review`, `_evidence`, `_store`), `noema/study/review.py` (`record_review`),
`noema/study/correction.py` (297 lines), `noema/db/models.py` (`ConceptMastery`, `Mistake`,
`Session`, `Review`, `Answer`, `Explanation`, full class list), `noema/api/v1/ai.py`
(`professor_chat`, `_dispatch_stream`, `_dispatch_action`, `_dispatch_exam`), `noema/api/v1/schemas.py`
(`ChatIn`, `ChatMessageIn`, `MasteryOut`, `MasteryComponents`), `noema/api/v1/study.py`
(`GET /mastery`), `noema/workers/__init__.py` (both actors, to check for any decay/refresh job),
`apps/web/src/app/progress/page.tsx`, `apps/web/src/components/ConceptGraph.tsx`,
`apps/web/src/app/notebooks/[id]/professor/page.tsx`, `apps/web/src/lib/api.ts` /
`api-schema.ts` (`Mastery` type), `docs/mastery-engine.md` (scale/precision statement),
and `tests/test_db_professor_memory.py` (to see what behaviour is locked in by a passing
test vs. only asserted in prose — this is where the headline bug below was actually found).

---

## 1. What "memory" actually means in this codebase today

`build_memory()` (`professor_memory.py:94-148`) is the entire implementation. It does two
queries, both scoped to one notebook and one owner:

- **Concepts** (`professor_memory.py:108-127`): finds concept IDs touched by this notebook
  via a `UNION` of `Card.concept_id` and `Question.concept_id` (`_notebook_concept_ids`,
  `professor_memory.py:71-91` — needed because `Concept` is workspace-scoped, not
  notebook-scoped, per the module's own docstring, `professor_memory.py:10-12`), then joins
  those IDs against `ConceptMastery` for `(name, mastery, evidence_count)`, ordered by
  `last_evidence_at DESC NULLS LAST`, capped at `MAX_CONCEPTS = 5` (`professor_memory.py:28`).
- **Misconceptions** (`professor_memory.py:129-146`): open (`resolved_at IS NULL`),
  flagged (`is_misconception IS TRUE`) `Mistake` rows joined to `Question.notebook_id`,
  ordered by `Mistake.created_at DESC`, capped at `MAX_MISCONCEPTIONS = 3`
  (`professor_memory.py:29`), each summary truncated to `MAX_SUMMARY_CHARS = 220`
  (`professor_memory.py:33, 145`).

Both queries filter `owner_id` explicitly (`professor_memory.py:119, 136`) — real tenancy
isolation, and it is the one thing this module has an adversarial test for
(`test_another_users_mastery_never_leaks_through_a_shared_concept_id`,
`test_db_professor_memory.py:263-310`).

What it does **not** assemble: no raw past chat messages (there is nowhere to pull them
from — see §5), no review-event history/timeline, no FSRS scheduling state, no concept-graph
structure (prerequisites/dependents are used by the mastery *engine*, §3-4, but never surface
here). It is a snapshot of two numbers per concept (`mastery`, `evidence_count`) and a list of
open-misconception summary strings — nothing else.

**Budget:** bounded by row count (5 concepts, 3 misconceptions) and by a per-string character
cap (220 chars), not by an actual token budget. Compare `noema/retrieval/grounding.py`'s
`build_context()`, which accumulates a running token cost and stops once
`used + cost > token_budget` (`grounding.py:48-63`, `DEFAULT_TOKEN_BUDGET`). `professor_memory.py`
has no equivalent — there is no token-cost accounting anywhere in this module. In practice the
row/char caps keep the rendered block small regardless (worst case: 5 short concept lines + 3
×220-char strings), so this is a real gap relative to the more rigorous pattern used elsewhere
in the codebase, not a practical risk today.

## 2. Classification against the brief's own four-tier framework

- **Transient (this turn only):** no real counterpart. There is no per-turn scratch state at
  all beyond the one HTTP request's own execution — nothing is written or read that lives only
  for the current turn and is then discarded. (The classifier call in `professor_chat`,
  `ai.py:218-220`, produces an `Intent` that is used and dropped within the same request, but
  that is ordinary request-scoped computation, not anything worth calling a memory tier.)
- **Session (this conversation):** no real counterpart, confirmed in both directions.
  Backend: no `Conversation`/`Message` table exists anywhere in `noema/db/models.py` (full
  class list checked, §5). Frontend: `professor/page.tsx:54` holds the transcript in a plain
  `useState<Turn[]>([])` with no `localStorage`/`sessionStorage` write and no history fetch on
  mount — the conversation is memory in the literal JS-heap sense only, gone on refresh or
  navigation. There is nothing today that matches "remembers this conversation."
- **Learning (this topic/notebook, spans sessions):** this is the one tier the codebase
  actually has a real implementation of, and it is what `build_memory()` returns: `ConceptMastery`
  scoped to a notebook's concepts, and open `Mistake` rows scoped to a notebook — both durable,
  both read back in later, unrelated sessions (§6). This is genuine cross-session,
  topic-scoped memory.
- **Long-term (durable facts about the learner across everything):** partially present but not
  what `professor_memory.py` uses. `ConceptMastery` is durable and cross-session (§3), but it is
  *concept*-scoped and workspace-bounded, not a store of durable facts about the learner as a
  person (preferences, goals, general strengths/weaknesses across subjects). `Goal`
  (`db/models.py:758`) and `AIUsage`/`PlanConfig` exist as durable per-account rows, but nothing
  in `professor_memory.py` reads any of them — the injected context is always one notebook's
  concepts, never an account-wide picture. So "long-term" exists as scattered durable tables
  or an account, but there is no unified "durable facts about this learner" memory that the
  Professor actually draws on.

Plainly: of the four tiers the brief names, one (learning/notebook-scoped) is genuinely
implemented, one (long-term/account-wide) has durable *tables* but no unifying construct that
`professor_memory.py` reads, and two (transient, session) have no counterpart at all today —
not "implemented poorly," simply absent.

## 3. Confidence

`ConceptMastery` carries three columns distinct from the `mastery` score itself:
`competence`, `uncertainty`, `calibration` (`db/models.py:522-526`), plus `evidence_count` and
`last_evidence_at`. These are not decorative — `engines/mastery.py`'s `compute_mastery`
(`mastery.py:102-145`) computes `uncertainty` as the posterior standard deviation of a
Beta-distributed competence estimate (`variance = alpha*beta / ((alpha+beta)^2*(alpha+beta+1))`,
`mastery.py:131`, `uncertainty=math.sqrt(variance)`, `mastery.py:143`) — a real
statistical dispersion measure, not `1 - mastery`. `calibration` (`mastery.py:237-243`)
separately measures whether the learner's *stated* confidence (1-5, from `Evidence.confidence`)
tracks their actual correctness — genuinely distinct from both `mastery` and `uncertainty`.
So confidence is **not** conflated with mastery level at the model layer: three separate,
well-defined signals exist (`uncertainty`, `calibration`, and the `evidence_count`-driven
`is_provisional` flag, `mastery.py:96-99`, `< 3.0` effective observations).

Where the two representations diverge is in what actually reaches each audience:

- **Human-facing UI is honest.** `GET /mastery` (`study.py:595-629`) returns the full
  `MasteryComponents` breakdown plus a `provisional: bool` and `last_evidence_at`
  (`schemas.py:140-158`). `progress/page.tsx:129, 142-149` rounds to a whole number and
  visibly labels a provisional score ("a number from two answers is a guess wearing a
  number's clothes," `progress/page.tsx:143-145` — the codebase's own reasoning, not this
  audit's). Expanding a row shows `competence`, `retrievability`, `prior_mean`, and
  `effective_observations` as separate lines (`progress/page.tsx:161-182`). This is a
  genuinely well-built anti-false-precision UI.
- **Model-facing context (the actual subject of this phase) is not.** `professor_memory.py`'s
  `render()` (`professor_memory.py:52-68`) outputs only `"{name}: {pct}% mastery"` — no
  `evidence_count`, no `is_provisional`/uncertainty, no staleness. A concept with a single,
  weak data point and a concept with fifty consistent reviews are presented to the LLM with
  the same bare-percentage confidence. This is real false precision, in exactly the place
  the brief asks about — it's just in the prompt, not the UI.

**Real, small, well-scoped bug found here — flagging, not fixing:** `professor_memory.py:62`,
`pct = round(concept.mastery * 100)`. `concept.mastery` is populated directly from
`ConceptMastery.mastery` (`professor_memory.py:115, 125`), and that column is stored on a
**0–100** scale everywhere else in the codebase: `docs/mastery-engine.md:11` ("The UI shows a
number between 0 and 100"), `noema/study/mastery.py:329` (`row.mastery = mastery.score`, where
`Mastery.score = 100.0 * competence * (...)`, `engines/mastery.py:135`), `study.py:614, 624`
(`ConceptMastery.mastery < 60`, `round(row.mastery, 1)`, no rescale), and
`study/session.py:50` (`WEAK_MASTERY = 60.0`). `professor_memory.py:62` multiplies that
already-0–100 value by 100 a second time, so a concept genuinely at 62% mastery would render
as `"Mitochondria: 6200% mastery"` in the `<STUDENT_MEMORY>` block injected into the
EXPLAIN/DEEPEN system prompt — nonsensical, and the opposite of the "no false precision" goal.
This is masked by `tests/test_db_professor_memory.py`'s own fixture: `make_mastery()`
(`test_db_professor_memory.py:117-134`) writes `ConceptMastery.mastery` directly as a raw
fraction (e.g. `mastery=0.62`, `test_db_professor_memory.py:178`) rather than going through
the real production write path (`study/mastery.py::_store`, which always writes a 0–100
`Mastery.score`), so the test's fixture data uses the same (wrong) scale convention as the
buggy `render()` code and passes green (`test_db_professor_memory.py:184-185`, asserting
`"Mitochondria: 62% mastery"` from a stored `0.62`) while never exercising the value shape
production actually writes. Every other consumer of `ConceptMastery.mastery`
(`study.py`, `study/session.py`, `study/goals.py`, `services/account.py`) treats the column as
already 0–100 and does not rescale. **This is a real production bug, not an architectural gap
— flagged for the orchestrating session to decide on a fix; not fixed here.**

## 4. Decay

Time-based decay does exist in the underlying math, but only as a **write-time**, not a
read-time or background, effect. `engines/mastery.py::_retrievability` (`mastery.py:209-234`)
and `engines/fsrs.py::retrievability` (`fsrs.py:82-90`, the FSRS-4.5 power forgetting curve)
both genuinely decay a probability of recall as a function of elapsed time since last review —
this is real, not decorative (`retrievability(state, elapsed_days) = (1 + FACTOR*elapsed_days/stability)^DECAY`).
`compute_mastery`'s final score multiplies competence by a retrievability term
(`mastery.py:135`, `score = 100.0 * competence * (lam + (1-lam) * r)`), so decay is baked into
the formula.

The problem is *when* that formula runs. `ConceptMastery` is a stored projection
(`db/models.py:511-514`, "A projection... rebuilt and compared rather than silently replacing
the old numbers"), and it is recomputed **only** from two triggers, both write events:
`record_review()` after a card review (`study/review.py:158-166`, calling
`recompute_mastery` + `recompute_for_review`), and the analogous calls in
`study/feynman.py`, `study/questions.py`, `study/socratic.py` after their own graded events
(confirmed by grep — all four call sites are event-triggered, none is a scheduled job).
`noema/workers/__init__.py` (checked in full) defines exactly two `dramatiq` actors — `ingest`
and `purge_accounts` — no third actor recomputes or decays mastery on a schedule; there is no
`cron`/`scheduler`/`periodic` decay job anywhere in the codebase.

**Consequence:** a concept a student reviewed 90 days ago and hasn't touched since keeps
exactly the `mastery`/`retrievability` value computed at that last review, forever, until the
next review event. It does not silently drift downward as staleness accumulates, contrary to
what the brief's "a concept not reviewed in 60 days should plausibly read as less certain"
expects. The retrievability *term* would be lower if recomputed today, but nothing recomputes
it. This is a genuine, real gap — decay is a property of the formula, not a property of the
stored data over time.

`professor_memory.py`'s injected context makes this worse in one respect: it selects
`last_evidence_at` only to `ORDER BY` (`professor_memory.py:121`) and never returns or renders
it (`ConceptSnapshot`, `professor_memory.py:36-40`, has no `last_evidence_at` field at all).
So even the (stale) stored score reaches the Professor's prompt with zero staleness signal —
no "last reviewed N days ago." A score frozen from three months ago is presented with exactly
the same textual confidence as one from this morning. Combined with §3's scale bug, the
`<STUDENT_MEMORY>` block the model actually sees carries neither the right number nor any
signal of how current it is.

## 5. Session/conversation continuity

Confirmed statelessness in both directions:

- **Backend:** `noema/db/models.py` was read in full (every `class` declaration, 39 total)
  — there is no `Message`, `Conversation`, `ChatTurn`, or equivalent table. The only class
  named `Session` (`db/models.py:108-127`) is an auth refresh-token family
  ("A refresh-token family. Rotation replaces rows; reuse revokes the family.") — unrelated to
  chat history. `ChatIn` (`schemas.py:190-193`) carries `notebook_id`, `mode`, `messages`
  (client-supplied, `list[ChatMessageIn]`, 1-100 items, each ≤32,000 chars) and `grounded` —
  no `conversation_id`, nothing that could look up prior turns server-side.
  `_dispatch_stream` (`ai.py:381-438`) builds its message list entirely from
  `payload.messages` (`ai.py:414`, `messages += [Message(...) for m in payload.messages]`) —
  the backend never reads or writes a turn anywhere; it only ever sees what the client
  replays in that one request.
- **Frontend:** `professor/page.tsx:54` (`const [turns, setTurns] = useState<Turn[]>([])`) —
  a plain in-memory React array. No `localStorage`/`sessionStorage` write for messages was
  found (grepped the whole `apps/web/src` tree), and no fetch of prior turns on mount besides
  loading the notebook itself. Closing the tab or reloading the page loses the transcript
  completely — not just server-side statelessness, the client owns nothing durable either.

So: **there is no session-memory tier today, full stop** — not "the frontend owns it," but
that neither side owns it past the current page's lifetime. This is the most literal
match to the brief's "is there any per-conversation state beyond the messages the frontend
already sends back each turn" question, and the honest answer is that even the frontend's own
copy doesn't survive a reload.

## 6. Misconception memory specifically

This is real, working learning-tier memory, not a same-turn mechanism. `Mistake`
(`db/models.py:629-651`) is a durable, owner-scoped row with no TTL: `is_misconception`,
`summary` (an AI-written belief statement, `study/correction.py:126-128`), and
`resolved_at` (nullable — stays open indefinitely until earned closure). `correction.py`'s
`build_drills` (`correction.py:75-136`) writes the belief and discriminating drill questions
once, at mistake time; `resolve_if_earned` (`correction.py:139-194`) only closes a mistake
after **two** correct, confident (`confidence >= 4`) answers **on different days**
(`REQUIRED_CORRECTIONS = 2`, `SPACING = timedelta(hours=20)`, `_spaced_enough`,
`correction.py:197-203`) — deliberately resistant to "the last explanation still echoing"
(`correction.py:11-13, 150`). Until that resolution fires, the misconception stays open, and
`professor_memory.py:129-146` reads it back into **any** later EXPLAIN/DEEPEN turn in that
notebook — a completely different conversation, potentially days or weeks later, with no
special triggering beyond "is this mistake still open." That is a genuine cross-session
learning-tier memory, correctly implemented and tenancy-scoped
(`test_another_users_mastery_never_leaks_through_a_shared_concept_id` also covers this path
indirectly by construction). The one caveat: it is scoped to the *notebook*
(`Question.notebook_id == notebook_id`, `professor_memory.py:135`), not the concept globally —
a misconception surfaced while studying one notebook stays invisible to the Professor in a
different notebook that happens to touch the same concept. That is a scoping choice consistent
with `build_memory`'s notebook-scoped design (§1), not a bug.

## 7. Confirming Phase 6's finding on injection scope

Confirmed by reading the actual call site, `ai.py:381-438` (`_dispatch_stream`) and
`ai.py:166-263` (`professor_chat`'s own dispatch):

- `professor_chat` routes `Intent.CREATE_EXAM` to `_dispatch_exam` (`ai.py:244-247`),
  `Intent.QUIZ_ME`/`Intent.CREATE_FLASHCARD` to `_dispatch_action` (`ai.py:249-252`), and
  everything else (`EXPLAIN`, `DEEPEN`, `SUMMARIZE`) to `_dispatch_stream` (`ai.py:254-257`).
- Neither `_dispatch_exam` (`ai.py:329-378`) nor `_dispatch_action` (`ai.py:266-327`) imports
  or calls `build_professor_memory` anywhere in their bodies — confirmed by reading both
  functions in full, not inferred from the import list. So **QUIZ_ME, CREATE_FLASHCARD, and
  CREATE_EXAM get zero memory context**, exactly as Phase 6 found.
- Inside `_dispatch_stream` itself, the call is explicitly gated:
  `if payload.notebook_id is not None and dispatch.intent in (Intent.EXPLAIN, Intent.DEEPEN)`
  (`ai.py:424-427`) — the comment directly above it states the reasoning ("SUMMARIZE condenses
  what's in front of it and doesn't need what the student already knows," `ai.py:420-423`).
  So **SUMMARIZE reaches `_dispatch_stream` (the same function that streams EXPLAIN/DEEPEN)
  but is explicitly excluded from the memory injection by this `if`** — a deliberate design
  choice, not an oversight, and worth stating plainly since SUMMARIZE's exclusion is easy to
  mis-read as "not implemented yet" when it is in fact "implemented and excluded on purpose."

The System Map's "injected only into EXPLAIN/DEEPEN" (`NOEMA_SYSTEM_MAP.md:83-84`) is
confirmed accurate at the line level.

---

## Headline findings

Ranked by importance, matching the rigor of the Phase 6 and Phase 9 audits:

1. **Real, small, well-scoped bug — the mastery percentage injected into the Professor's
   own prompt is wrong by a factor of 100 (§3).** `professor_memory.py:62`
   (`pct = round(concept.mastery * 100)`) treats `ConceptMastery.mastery` as a 0-1 fraction,
   but that column is stored and consumed as 0-100 everywhere else in the codebase
   (`docs/mastery-engine.md:11`, `study/mastery.py:329`, `study.py:614,624`,
   `study/session.py:50`). In production, a concept at 62% mastery would render as
   `"Mitochondria: 6200% mastery"` in the `<STUDENT_MEMORY>` block fed to EXPLAIN/DEEPEN. The
   unit test for this module passes only because its own fixture (`make_mastery`,
   `test_db_professor_memory.py:117-134`) writes the mastery column directly as a raw fraction
   instead of going through the real production write path, so the test's data and the buggy
   code share the same wrong scale convention and never surface the mismatch. Flagged for the
   orchestrating session to decide on a fix — not fixed here.

2. **No session-memory tier exists on either side of the wire (§5).** Not "the backend is
   stateless and the frontend compensates" — the frontend's own transcript lives in
   unpersisted React state (`professor/page.tsx:54`) with no `localStorage` write and no
   restore-on-mount. Closing the tab loses the conversation completely, and there is no
   `Message`/`Conversation` table anywhere in `db/models.py` for the backend to fall back on.
   Of the brief's four tiers, this one has no implementation at all, not a partial one.

3. **Mastery decay is a write-time effect, not a standing property of the stored score, and
   the model-facing context carries no staleness signal at all (§4).** The FSRS/mastery math
   genuinely computes time-decayed retrievability, but `ConceptMastery` only gets recomputed
   on the next graded event (review/answer/explanation) — there is no scheduled job (confirmed
   by reading both actors in `noema/workers/__init__.py`) and no read-time recompute. A score
   from 90 days ago sits unchanged until the student happens to study that concept again.
   `professor_memory.py` compounds this by never selecting or rendering `last_evidence_at`
   (`ConceptSnapshot` has no such field) — so even the honest UI (`progress/page.tsx`, which
   does surface `last_evidence_at` and a `provisional` badge) is more honest about staleness
   than what actually reaches the model.

4. **Confidence is real and well-modeled at the data layer, but is stripped before it reaches
   the model (§3).** `uncertainty` (posterior std-dev of competence) and `calibration`
   (stated-vs-actual confidence gap) are genuine, separately computed signals — not mastery
   re-labelled — and the human-facing `/mastery` endpoint and `progress/page.tsx` surface them
   honestly, including a visible "provisional" label for low-evidence scores. None of that
   reaches `professor_memory.py`'s `render()`, which outputs a bare percentage with no evidence
   count and no provisional flag. Bug #1 aside, this is the false-precision gap the brief
   specifically asked about, and it is architectural (missing fields in `ConceptSnapshot`/
   `render()`), not a one-line fix.

Of the brief's four memory tiers, one (learning/notebook-scoped: `ConceptMastery` +
open `Mistake`) is genuinely implemented and correctly cross-session (§2, §6); "long-term"
exists as scattered durable tables (`Goal`, `AIUsage`) with no unifying construct the Professor
actually reads; "transient" and "session" have no real counterpart today. This is an honest
architectural gap against an aspirational framework, not a codebase that is broken — the one
genuine bug found (#1) is narrow and specific, and the rest of the findings are gaps to weigh
for a later phase, not defects to fix reflexively.
