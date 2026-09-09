# NOEMA Guard — re-audit against current `main` (2026-09-09)

Read-only, produced against `origin/main` at commit `9d69ae0` (a git worktree,
not the `claude/sabelia-guard` branch — that branch is untouched by this
audit). The prior audit (`NOEMA_SABELIA_READINESS_AUDIT.md`) ran against
`7fd8a97`; hundreds of commits landed in between (V3 Professor Engine, V3.1
Focus Mode, the Mino persona/character system, the standalone `sabelia/` ML
package, the Academic Knowledge Engine). This file answers, against the real
current tree, the questions that prior audit's baseline can no longer answer
correctly.

## 1. Safety / moderation / risk-classification layer — still does not exist

`grep -rniE "moderation|risk_level|risk_classif|safety_event|content_filter"
noema/` (backend, all of it): **zero hits** beyond `content_filter` as the
existing provider-refusal pass-through literal already found by the first
audit. `grep -rni "guard" noema/`, excluding `BudgetGuard`/CSRF-guard/token
"budget guarding" prose: **zero hits**. The V3 Professor Engine, the Academic
Knowledge Engine, and Focus Mode add no such layer. `sabelia/sabelia/policy/
rules.py` (the name that looked suspicious) is a *pedagogical* next-action
policy — `DIAGNOSTIC/REVIEW/LEARN/EXPLAIN/PRACTICE/CHALLENGE`, scored from
the learner's mastery state — not a content-safety policy; it shares no
vocabulary or purpose with input/output moderation. **Verdict unchanged from
the first audit: NOT BUILT anywhere in the current tree.**

## 2. Feature-flag infrastructure — same mechanism as before, confirmed still current

`noema/core/config.py` still uses plain typed booleans directly on `Settings`
— e.g. `noema_demo_enabled` (`config.py:114`), `noema_professor_flashcards_
enabled` and `noema_professor_assessments_enabled` (`config.py:185-186`).
No dedicated flags table, service, or targeting-rule mechanism was built in
the V3 work. The Guard branch's own `noema_sabelia_guard_enabled` (soon to be
renamed) followed the *correct*, still-current convention — nothing to
change there except the name.

## 3. Focus Mode (`NOEMA_V3_1_FOCUS_MODE.md`) — genuinely equivalent to the brief's TDAH ask, not cosmetic

This is real, and materially stronger than the original brief's own spec in
several places:

- **Persisted, cross-session preference**: `PATCH /me/preferences` /
  `GET /me/preferences` (`noema/api/v1/account.py:54-87`) stores
  `learning_mode: normal|focus` in `users.settings` (a real column), read
  back on every session — not a client-side toggle that resets.
- **A real backend engine**, not a frontend-only skin: `noema/professor/
  focus.py` (346 lines) implements `CognitiveLoad` (per-turn word/concept
  caps by chunk level, forces a check after every teaching move — this *is*
  the brief's Hint-Ladder-adjacent "how much to teach before checking"
  idea), an adaptive chunk-size controller (widens on quick correct answers,
  narrows on "não entendi"/wrong answers — persisted as `journey.profile.
  focus.chunk_level`), an `AttentionPulseEngine` reading only product
  signals (time since last turn, "me perdi", side questions — explicitly
  documented as never inferring a diagnosis), and dedicated router moves
  (`REORIENT`, `RETURN`, `PARK`) with their own tested behavior.
- **Reaches the model's actual output**: the `<FOCUS_MODE>` directive block
  (mission, session map, pause offers) rides in every turn's prompt when the
  mode is on — this is real prompt-injection plumbing already built, the
  exact machinery the Guard PR's own scope-cut deferred for its
  `ALLOW_WITH_CONTEXT`/`RESTRICTED` behavior. **A future Guard phase that
  wants to inject a softened system note has a proven pattern to copy.**
- **Tested with named personas** (A–F: loses focus quickly, hyperfocuses,
  dislikes long text, advanced-but-wants-chunks, returns after days, asks
  side questions), each with a named test asserting the *directive* changes,
  not just that a flag is set.

Documented gaps, honestly stated in the source doc itself, not found by this
audit: no notifications yet, no second character, no timer-driven
interruption (all explicitly out of scope by design, not missed).

**Verdict: genuinely equivalent to the brief's TDAH Engine ask — a real,
tested, cross-session, model-output-changing feature. The first audit's
"zero code anywhere" finding was accurate for its own commit and is now
obsolete.**

## 4. Mino persona (`mino.persona.v1.md`) — genuinely equivalent to the Personality Engine ask

`noema/prompts/mino.persona.v1.md` (front-matter `layer: persona`, version
2) is a real, detailed tone/personality instruction that reaches the LLM's
system prompt on every turn — not a visual-only character. It independently
arrives at several of the brief's own named rules almost verbatim: "Do not
flatter. A basic question gets a normal answer, not 'great question'" (the
brief's §8/§25 "NÃO BAJULAR"), "change the approach... never the same
paragraph again" (scaffolding/strategy-ladder adaptation), explicit
before/after examples contrasting stiff corporate phrasing ("Certamente.
Vamos explorar os fundamentos...") against the wanted voice. `mino.focus.v1.md`
layers Focus Mode's own delivery rules on top, additively.

**Verdict: genuinely equivalent to the Personality Engine ask, arguably more
specific and better-calibrated than a first attempt at the brief's own
`SabeliaPersonalityState` numeric-dial design would have produced. Not
cosmetic, not visual-only.**

## 5. `/ai/professor` route — restructured internally, but the Guard's wiring point still exists in the same place

`noema/api/v1/ai.py:173` still defines `@router.post("/professor")` /
`async def professor_chat(...)`. Internally it is a real rewrite: intent
classification (`classify_intent`/`professor.plan`) is gone, replaced by
`ProfessorEngine.prepare()` → `ProfessorEngine.stream()`
(`noema/professor/engine.py`, 1235 lines) built around `journey`/`move`/
`signal` and a 12-move router (`noema/professor/moves.py`).

Critically for re-wiring Guard: the route's own opening shape is unchanged
in the one place that matters. In order: the entitlement gate returns early
with its own comment — *"Checked before anything is stored or called -- a
blocked turn should cost the platform nothing"* (`ai.py`, right where the
Guard PR's own comment said almost the same thing) — then `question =
payload.messages[-1].content` is read, then (new) a `TeachingSession` is
found-or-started and the learner's turn is committed to its own transaction
*before* the engine is ever built. Guard's own check belongs **right after
`question = payload.messages[-1].content` and before
`sessions.start_or_resume(...)`** — earlier than before, since now there is
a real DB write (the session turn) between that line and where the engine
used to be reached, and a blocked message should not be journaled into a
learning session's transcript either.

The Guard's original economy-tier gateway resolution (`professor.
tiered_gateway(ModelTier.ECONOMY, ...)`) is no longer available at that
point the same way — `professor.py`'s `classify_intent`/`plan`/
`tiered_gateway` functions were the V2 orchestration Guard was built
against, and the V3 rewrite may have removed or relocated that module.
**Confirming whether `noema.services.professor` still exists and in what
shape is the first thing the next Guard PR must check before writing any
code** — this audit did not trace that far since it is implementation work,
not audit scope.

## 6. `sabelia/` naming collision — confirmed cosmetic only, zero code coupling

`sabelia/pyproject.toml` declares an independent project (`name = "sabelia"`,
its own dependencies, own `requires-python`, Apache-2.0, no relationship to
`apps/api`'s `pyproject.toml`). `grep -rn "import sabelia\|from sabelia"
apps/api/noema/`: **zero hits** — nothing in the product imports the research
package. The collision is real but shallow: it is a name shared between two
unrelated things (a learner-modeling ML research package vs. a proposed
safety layer), not an architectural conflict. Renaming the Guard work away
from "Sabelia" (as already decided) fully resolves it; no further
`sabelia/`-side change is needed or implied.

## 7. Closing verdict

**NOEMA Guard is still real, non-duplicated, valuable work and should be
adapted and merged — nothing in this drift covers input safety.** Three
things must change before it can land, all mechanical, none invalidating the
design:

1. Drop every "Sabelia" name (module, flag, docstrings) — plain "NOEMA
   Guard" naming, per the user's own decision, to stop colliding with the
   real ML package of that name.
2. Re-wire the block-before-generation check into the current
   `professor_chat()` shape (`ai.py:173`), which has moved earlier in the
   function (before `TeachingSessions.start_or_resume`/`db.commit()`, not
   after a `tiered_gateway`/`classify_intent` call that this route no longer
   makes) — the entitlement gate right above it already establishes and
   comments on the exact "before anything is stored" principle Guard needs.
3. Confirm what `noema/services/professor.py`'s current role is (if any) and
   how `ProfessorEngine` resolves an economy-tier gateway now, since Guard's
   LLM escalation needs *a* cheap gateway+model pair and the one it used to
   borrow may no longer be built the same way at that point in the route —
   this needs a direct read of `engine.py`/`professor.py`'s current state,
   not a guess.

Everything else about Guard's own design (heuristic-first, LLM-escalation-
only-on-ambiguity, `RiskLevel`/`SafetyAction` schema, `SafetyEvent` logging,
fail-safe-to-SENSITIVE-not-SAFE-or-HIGH_RISK) is orthogonal to all of this
drift and needs no rethinking.

**Addendum, resolving point 3 above**: `noema/services/professor.py` still
exists, unchanged in shape (`Intent`, `classify_intent`, `TieredCall`,
`tiered_gateway`, `DispatchPlan`, `plan`, `needs_notebook_material` — all
still defined, `professor.py:52-236`). It is no longer called from
`ai.py:173`'s route directly, but `ProfessorEngine` itself imports and calls
`tiered_gateway` internally (`noema/professor/engine.py:66,204`) to resolve
its own economy-tier calls. **Guard can call `professor.tiered_gateway(
ModelTier.ECONOMY, ...)` exactly the way the original implementation did** —
the function, its signature, and its fallback behavior are all unchanged;
only the call site around it moved.
