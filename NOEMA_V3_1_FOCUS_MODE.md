# NOEMA V3.1 — Focus mode (TDAH / ADHD-friendly learning)

An extension of the Professor Engine (`NOEMA_V3_PROFESSOR_ENGINE.md`), not a
separate product. A learner may prefer shorter sittings, more interaction,
clearer objectives and easy recovery when attention slips. Focus mode adapts
the **delivery** of the same lesson to that preference. It never diagnoses,
never infers a condition, never comments on the learner's attention, and
stores only educational preferences.

## What changed globally

- **Mino's voice** (`prompts/mino.persona.v1.md`, front-matter version 2):
  a young teacher who is good at talking — short lines, the interesting part
  first, natural rhythm in the lesson's language, no "certamente", no forced
  slang, no flattery. Depth stays; the delivery changed. This applies to
  every learner, not only Focus mode.
- **TeacherCharacter** (`components/mino/character.ts`): the interface reads
  the teacher's name and rig from one record. Mino is the default and the
  only one; a second character is a second entry, approved visually first.

## The preference

`PATCH /me/preferences` `{learning_mode: normal|focus, session_minutes}`
stored in `users.settings`; read by `GET /me/preferences`. Offered in
onboarding (`/learn/new`, step "Ritmo") and in Settings; switched at will.
Copy: "Mais interação, sessões menores e menos enrolação." No clinical
language beyond the mode's name.

## The engine (`noema/professor/focus.py`)

| Piece | What it does |
|---|---|
| `CognitiveLoad` | Per turn: max words (90 / 160 / 260 by chunk level), concepts (1 / 1 / 2), examples, and how often to ask (every explanation at levels 1–2). Sets the reply's token cap and forces a check after every teaching move. |
| Adaptive chunk size | Two quick right answers widen the chunks; a wrong answer, "não entendi", "me perdi" or a forgotten recall narrows them. Stored as `journey.profile.focus.chunk_level`; never stuck at five-word lines. |
| `Pulse` (AttentionPulseEngine) | Product signals only: hours since the previous turn, "me perdi", the welcome-back answer, side questions, long sittings. No webcam, no inference. |
| Router moves | `REORIENT` ("me perdi": one anchor sentence, where we were, one question — never a restart), `RETURN` (back after 6 h+: one `noema:recall` question with lembro · mais ou menos · esqueci), `PARK` (a side question in Focus mode: two-line answer, offer to keep it). The recall answer routes the next turn: forgot → CORRECT with a new strategy; partly → REVIEW; remember → ADVANCE. |
| CuriosityParkingLot | `learning_journeys.parked` (migration 0021). Kept topics are offered back when the lesson closes (MOTIVATE / EXAM / SUMMARIZE moves). |
| Recap | `GET /ai/journeys/{id}/recap`: YOU KNOW · NOW · NEXT · parked, from state, no model call. |
| Communication profile | `journey.profile.communication` (formality, verbosity, humour, depth, interaction, encouragement) nudged one notch per clear signal and read into the directive. |
| Focus limits | Cards 3 per concept; checkpoint papers 3 questions. Deep exams stay available. |
| Momentum | `JourneyOut.momentum`: showings today and concepts mastered today — a count, no streaks. |

The system prompt gains one identical `mino.focus` layer for every Focus
learner (still cacheable); everything per-turn rides in the `<FOCUS_MODE>`
part of the directive: the mission ("in about N minutes, understand X"), the
session map (● done ✓ · ● now · ○ next), pause offers, parked topics.

## The interface

- **Focus Stage** (`FocusStage.tsx`, on `/chat` when the mode is on): the
  mission of this sitting, the session map, "Me perdi", "Resume pra mim",
  an optional 5 / 10 / 15-minute timer that ends with "+5 min" or "Parar por
  hoje" — an offer, never pressure. The rail keeps only the wordmark and a
  way to adjust; the presence figure and secondary navigation step aside.
- **Blocks**: `recall` (three buttons) and `park` (guardar · ver agora) come
  from the server as events, like every other block.
- **Home** (`FocusHome.tsx`): "O que faço agora?" → Continuar ~N min ·
  Revisão rápida 2 min (the journey's due cards, inline) · Começar algo novo.
  Momentum as a plain line.
- **Landing**: the beat "Um professor que muda com você" toggles the same
  lesson between Normal and Focus (hook · concept · interaction · recall).
- **Language**: pt "TDAH / Modo Foco", en "ADHD / Focus Mode", es "TDAH /
  Modo Foco"; no hard-coded English in the Portuguese build.

## Verified (locally, mock providers, Postgres + pgvector)

| Persona | Test |
|---|---|
| A — loses focus quickly | "me perdi" → REORIENT, chunk level narrows, recovery recorded (`test_persona_a…`, `test_me_perdi_reorients_without_restarting`) |
| B — hyperfocuses | quick right answers widen chunks to level 3; slow ones do not count (`test_persona_b…`) |
| C — dislikes long text | Focus load: 90 words, one concept, ask every turn, reply cap < 700 tokens; directive carries mission and session map (`test_persona_c…`, `test_focus_mode_changes_the_delivery_not_the_content`) |
| D — advanced but wants chunks | "já sei" advances; level 3 keeps two concepts; the directive says "same depth, another rhythm" (`test_persona_d…`) |
| E — back two days later | RETURN with one recall question; forgot → CORRECT, partly → REVIEW, remember → ADVANCE; the answer is a `check` mastery event (`test_persona_e…`, `test_coming_back_days_later…`) |
| F — side questions | PARK in Focus mode only; topics kept, deduplicated, recapped and offered back at MOTIVATE (`test_persona_f…`, `test_a_parked_curiosity…`) |

A/B (same depth, another rhythm): the Focus directive never removes
concepts from the plan or the knowledge state; it caps words per turn and
asks more often. Verified by construction and by the directive tests above;
a real-model comparison needs the user's credentials (`scripts/eval-teaching.py`).

## Not done

- Notifications: none exist in the product yet; when they do, the rule is
  written here: "Tem uma revisão de 3 min pronta quando quiser", never guilt.
- A second Focus character: architecture only (`TeacherCharacter`).
- Break suggestions after long sittings are a one-line offer in the
  directive; there is no timer-driven interruption by design.
