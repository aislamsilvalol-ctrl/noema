# Teaching engine — Phase 0 audit and Phase 1 baseline

*How a Professor reply is produced today, what the baseline conversation shows,
and what that means for the rebuild.*

Written against `main` at `7fd8a97`. A first version of this document was
written against `97b63cc`, before the Professor Noema orchestrator (#108–#145)
landed; that version described a code path that is no longer the primary one and
claimed a blocker (no model configured) that no longer holds. This replaces it.

Three audits by another session already cover the surrounding machinery in depth
and are not repeated here: `NOEMA_AI_ARCHITECTURE_AUDIT.md` (gateway, retries,
budget, tiering, failure modes), `NOEMA_MEMORY_ARCHITECTURE_AUDIT.md` (what
"memory" is, tier by tier), `NOEMA_RAG_AUDIT.md` (chunking, retrieval,
citations, injection). This one is about **pedagogy**: does the path teach, and
if not, why not.

## 1. The path a Professor turn takes

```
professor/page.tsx  ──POST /api/v1/ai/professor──▶  professor_chat()
  turns: Turn[] in React state       payload: ChatIn {notebook_id?, mode, messages[], grounded}
  (no localStorage, no restore)         │
                                        ├─ EntitlementsService.check_ai_usage()     (DB SUM, before anything)
                                        ├─ tiered_gateway(ECONOMY) → classify_intent()   ← serial model call #1
                                        │     professor.classify_intent.v1.md → {intent} ∈ 6 values
                                        │     no notebook + quiz/card/exam → forced back to EXPLAIN
                                        ├─ plan(intent) → DispatchPlan{task, mode ∈ {explain, summarize}, tier}
                                        │     EXPLAIN → STANDARD tier, DEEPEN → PREMIUM, both use mode "explain"
                                        └─ _dispatch_stream()
                                              ├─ if notebook & grounded: retrieve()       ← embed + 2 index scans, serial
                                              ├─ _assemble(): grounded+hits → rag.answer  (teaching prompt DROPPED)
                                              │               else           → tutor.explain.v1.md (+ identity clause)
                                              ├─ messages = [system] + full client transcript + [<MATERIALS>]
                                              ├─ if notebook & intent∈{EXPLAIN,DEEPEN}: build_professor_memory()
                                              │     → <STUDENT_MEMORY>: ≤5 concepts as "name: NN% mastery",
                                              │        ≤3 open misconception summaries. Notebook-scoped.
                                              └─ gateway.stream(ChatRequest)                ← serial model call #2
                                                    AnthropicProvider: raw httpx, no thinking, no effort,
                                                    no cache_control; full transcript re-billed every turn
                                        ◀── SSE: intent | sources | token* | done | error
```

Persisted during or after a turn: one `AIUsage` row. Nothing else. No turn, no
session, no "what was taught", no evidence.

## 2. Phase 1 — the baseline conversation

`evals/teaching/baseline/freud-before.md` holds the spec's §119 sequence, run
against production on 2026-08-15 (`/ai/professor`, no notebook, provider
anthropic). Read it before reading this section; the judgement below is only
worth as much as the transcript.

### What is already good — and must not be lost

The raw explanations are strong. Concrete example first, then Freud's own
horse-and-rider analogy; a precise, well-argued correction of "everything I
forgot is unconscious" (banal vs. motivated forgetting, three marks); an exact
diagnosis of the wrong test answer (preconscious vs. unconscious, with the
browser-tabs analogy); every turn ends with a genuinely diagnostic question, never
"did you understand?". Natural Brazilian Portuguese throughout. **The model can
teach a concept. What it cannot do is run a lesson.**

### Where it fails the spec, turn by turn

| Turn | Learner said | What happened | Spec rule broken |
|---|---|---|---|
| 1 | "Me ensine Psicologia segundo Freud." | Straight into id, ego and superego — three concepts, named up front, with a "isso vira clichê" opener. No who-was-Freud, no problem he was solving, no plan, no "vamos por partes", no theory-vs-consensus framing. | ORIENT (§8), ONE CONCEPT AT A TIME (§11), INTUITION BEFORE TERMINOLOGY (§10), TEACHING PLAN (§31), CRITICAL FRAMING (§26), FREUD GOLDEN BEHAVIOR (§27: start with the unconscious) |
| 2 | "Não entendi o que é inconsciente." | A good first explanation of the unconscious (it had only been mentioned in passing). 380 words to someone who just said they are lost. | CHUNK SIZE ADAPTATION (§34) |
| 3 | "Então qualquer coisa que eu esqueci…?" | Excellent correction. | — (this is the bar) |
| 4 | "Agora entendi." | Did not advance. Asked one more check on the same concept, then listed four options for the learner to pick from. Silently dropped the unanswered question from turn 3. | RESPONSE TO CORRECT/ADVANCE (§16), NO ENDLESS OPTIONS (§81), TEACHING AUTHORITY (§82). Verifying before advancing is defensible; not advancing after, and handing the choice back, is not. |
| 5 | "Me testa." | Classifier returned `explain` (and without a notebook `quiz_me` is forced back to `explain` anyway). The model then improvised **five questions at once**, one of them on defence mechanisms, which had never been taught. | ONE AT A TIME, KNOWLEDGE CHECKS (§37), CONCEPT DEPENDENCIES (§36) |
| 6 | wrong answer | Exact diagnosis of the confusion, reframe, targeted follow-up. | — (this is the bar) |
| 7 | "Eu volto amanhã." | **Impossible.** The transcript lives in one React component. Reload the page and the lesson never happened. | STATEFUL PEDAGOGY (§30), REENTRY (§85), the whole of §119's last paragraph |

The pattern is exact: **every turn is a good answer; no turn is part of a
lesson.** There is no arc, no plan, no memory of the previous turn beyond the
transcript the browser happens to resend, and no adaptation that survives the
page.

### Latency and cost, measured

| turn | first token | total | prompt tokens | completion |
|---|---|---|---|---|
| 1 | 10.9 s | 22.5 s | 341 | 1528 |
| 2 | 6.8 s | 18.5 s | 1298 | 1110 |
| 3 | 11.5 s | 23.1 s | 2228 | 1237 |
| 4 | 3.4 s | 5.5 s | 3175 | 163 |
| 5 | 4.7 s | 11.8 s | 3345 | 630 |
| 6 | 9.5 s | 17.0 s | 3954 | 1085 |

First token takes 3–12 seconds. Two model calls run in series before any text
(classification, then the reply), with retrieval in between when a notebook is
attached. Prompt tokens grow linearly with the transcript and are re-billed in
full each turn — there is no `cache_control` on the stable prefix. The spec's
bar ("the experience must feel instant") is not close.

## 3. Root causes

### 3.1 Nothing persists across turns except what the browser resends

Confirmed on both sides by the memory audit (§5): no conversation table, no
`conversation_id` in `ChatIn`, no localStorage. "Where did we stop, what did you
understand, what did you get wrong" cannot be answered tomorrow because it was
never written down today. This is the single largest gap and the first thing to
build.

### 3.2 One teaching voice, and it is a style sheet

`plan()` maps every streaming intent to `mode = "explain"` (or `"summarize"`).
`tutor.explain.v1.md` is eleven good lines about tone. It contains no policy for
orienting, sequencing, checking, adapting, switching strategy, or choosing depth
— which is why the baseline reads as a series of well-written answers. The
examiner/socratic/feynman/study-partner prompts exist but are **unreachable
from the Professor**; only the manual `/ai/chat` mode picker can select them.
Strategies are not a concept in the orchestrator.

### 3.3 Inside a populated notebook, the teaching prompt is discarded

`_assemble()` still replaces the whole system prompt with `rag.answer` when
retrieval finds material. The `has_material` fallback (#145) fixed the *empty*
notebook; a notebook with content — the main product surface — gets citation
Q&A instructions and no teaching instructions at all.

### 3.4 The learner is almost invisible to the model

`professor_memory.build_memory` is the right seed, and the memory audit confirms
it is real and correctly scoped. But it reaches the prompt only when a notebook
is attached (the baseline had none: **zero learner context**), only for
EXPLAIN/DEEPEN, and carries only a mastery percentage and open misconception
summaries. Not: the goal, the current concept, what was already explained this
session, the depth the learner asked for, prior Feynman/Socratic explanations,
evidence counts or staleness (memory audit #3, #4). Adaptation cannot exceed
what the model is told.

### 3.5 Conversation produces no evidence

`_dispatch_stream` writes nothing. A learner who correctly separates
preconscious from unconscious in their own words (turn 6's follow-up would elicit
exactly that) moves no mastery, records no misconception, resolves nothing. The
richest signal in the product is thrown away, and §49–52 (conversational
mastery, evidence weights) have nothing to attach to.

### 3.6 Intent is action-shaped, not pedagogy-shaped

The six intents answer "which subsystem do I call" — a good question for
routing cost. They do not answer "what is happening pedagogically": the learner
is confused / gave a wrong answer / gave a partial answer / agreed / wants to
move on / went off-topic / wants depth. Turn 4 and turn 5 both landed on
`explain`, and the model had to guess the situation from the transcript alone.
The `TeachingDecision` the spec describes (§45) has no counterpart.

### 3.7 Model configuration is not teaching-grade

The tiers (migration `0014`) are economy = Claude Haiku 4.5, standard = Claude
Sonnet 5, premium = Claude Opus 5. Every EXPLAIN turn — i.e. every teaching
turn in the baseline — ran on Sonnet 5; Opus 5 is reached only when the
classifier says `deepen`. The payload the Anthropic provider builds by hand
(raw httpx) sends no `thinking`, no `effort`, and no `cache_control`, so the
teaching model runs with reasoning off and the stable prefix re-billed every
turn. The other session's tiering is the right shape and should stay — the gap
is what the teaching tier *sends* and which tier teaching *deserves* (the spec
is explicit: do not route the core teaching path to the cheap model by default),
not how tiers are resolved.

### 3.8 No domain awareness

Freud and Python get the same eleven lines.

## 4. What survives the rebuild unchanged

- **Citation enforcement** and the honest "not in your materials" refusal
  (RAG audit §6) — the professor must keep both and *teach around* the gap.
- **The orchestrator's shape** — classify cheaply, dispatch at the right tier —
  and the entitlement gate before any model call. The rebuild adds pedagogy
  *inside* `plan()` and `_dispatch_stream`, it does not replace them.
- **`professor_memory`** as the seed of `LEARNER_CONTEXT`.
- **Misconception persistence** with earned closure (`correction.py`) — real
  cross-session learning memory, already correct.
- **Versioned prompt files with the identity clause injected at load** — the
  substrate for `NOEMA_CORE / TEACHING_PRINCIPLES / DOMAIN_POLICY / ACTIVE_SESSION
  / LEARNER_CONTEXT / OPTIONAL_MATERIAL` composition.
- **Structured-output plumbing** — the path for pedagogical metadata.
- **The evidence-weighted mastery engine** — conversational evidence joins it.

## 5. What the rebuild introduces, in the spec's phase order

1. **`TeachingSession`** (persisted; goal, subject, current concept, depth,
   strategy, recent understanding, open misconceptions, what-was-taught) and
   **conversation turns** (persisted; the transcript stops being the browser's
   problem). Reentry tomorrow becomes possible. — §3.1
2. **`TeachingDecision` per turn**: pedagogical situation (confused / wrong /
   partial / correct / agreed / move-on / off-topic / depth request) + strategy +
   whether to check understanding + next concept. Computed from the session
   state and the last message, cheaply, alongside the existing intent. — §3.6
3. **Prompt composition**: `NOEMA_CORE` + `TEACHING_PRINCIPLES` (the arc,
   diagnostic questioning, response-to-wrong/partial/correct, chunking, depth) +
   `DOMAIN_POLICY` + `ACTIVE_SESSION` + `LEARNER_CONTEXT` + `OPTIONAL_MATERIAL`.
   `rag.answer` becomes a *material policy layer*, never a replacement. — §3.2,
   §3.3, §3.8
4. **Strategies as a first-class choice with switching rules** (definition failed
   → analogy → scenario → prerequisite), selected in `plan()`; the existing mode
   prompts fold into strategies. — §3.2
5. **Pedagogical metadata sidecar** on every reply (`concepts_taught`,
   `knowledge_check`, `mastery_evidence`, `misconception`, `next_action`),
   validated, never shown raw, persisted after the first token without delaying
   it, and fed to mastery with conversational evidence weights. — §3.5
6. **Teaching-grade request shape** for the teaching tier: thinking on, stable
   prefix cached, classification and decision folded to avoid a serial round
   trip where possible. — §3.7, latency table
7. **Evals that judge lessons**: the Freud golden path, failed-explanation,
   advanced, beginner, contrarian, multi-turn simulated students, a human review
   set, and this baseline as BEFORE.

## 6. Coordination note

Another session is committing to `main` concurrently and owns the SaaS pivot
(billing, entitlements, admin, tiering). This program layers on `/ai/professor`
additively and rebases often. Two of that session's findings are prerequisites
here and should be fixed there or here, whichever comes first: `QuotaExceeded`
now reaches the stream (#137, done), and the mastery ×100 rendering bug in
`professor_memory` (#142, done).
