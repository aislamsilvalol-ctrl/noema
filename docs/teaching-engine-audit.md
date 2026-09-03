# Teaching engine — Phase 0 audit

*How a tutor reply is produced today, and why it reads as a chatbot.*

This is the audit that precedes the Pedagogical Intelligence Engine work. Nothing
here is a proposal; it is a description of the code as it stands on `main` at
`97b63cc`, so the rebuild is aimed at what is actually there rather than at what
we imagine is there.

## 1. The path a reply takes

```
TutorPanel (React state)  ──POST /api/v1/ai/chat──▶  ai.chat()
  turns: Turn[] held in           payload: {notebook_id, mode, messages[], grounded}
  component memory only
                                    │
                                    ├─ if notebook: retrieve() ──▶ embed query ──▶ pgvector + tsvector
                                    │                              (sequential, before first token)
                                    ├─ _assemble(mode, grounded, results)
                                    │     grounded + hits   → prompts/rag.answer.v1.md   (tutor prompt DROPPED)
                                    │     grounded + none   → prompts/rag.no_context.v1.md
                                    │     not grounded      → prompts/tutor.<mode>.v1.md
                                    ├─ messages = [system] + client transcript + [<MATERIALS>]
                                    └─ gateway.stream(ChatRequest(task=TUTOR_CHAT))
                                          └─ registry.route(TUTOR_CHAT) → default provider
                                                └─ AnthropicProvider (raw httpx, /v1/messages)
                                                      model = claude-sonnet-4-5, max_tokens ≤ 8192
                                                      no thinking, no effort, no cache_control
                                    ◀── SSE: sources | token* | done | error
                                          CitationFilter buffers to sentence boundaries
                                          and drops sentences whose citation is invented
```

Nothing is written to the database during or after a chat turn except an
`AIUsage` row (token accounting).

## 2. Inventory against the spec's map

| Spec item | Exists? | Where | Verdict |
|---|---|---|---|
| Core system prompt | Partial | `prompts/tutor.explain.v1.md` (11 lines) | Tone guidance, no pedagogy |
| Professor prompt | No | — | "explain" mode is the closest thing |
| Socratic prompt | Yes | `prompts/tutor.socratic.v1.md` | A separate personality, not a strategy |
| Context builder | Yes, for RAG only | `retrieval/grounding.build_context` | Builds MATERIALS; injects zero learner context |
| Learning journey | No | — | No table, no concept |
| Learner model | Partial, unused by chat | `ConceptMastery`, `Mistake`, `Explanation`, `Goal` | Rich, and the tutor never sees any of it |
| Memory | No | — | Conversation lives in one React component; a refresh is amnesia |
| RAG | Yes | `retrieval/search.retrieve`, `grounding.py` | Solid; runs sequentially before first token |
| Anthropic provider | Yes | `providers/anthropic.py` | Raw httpx; `claude-sonnet-4-5`; no thinking/effort/caching |
| OpenAI provider | Yes | `providers/openai.py` | Same shape |
| Model router | Yes | `providers/registry.py` + `NOEMA_MODEL_TUTOR` | Per task class; tutor has no dedicated default |
| Response formatting | Minimal | `CitationFilter`, SSE | Text only |
| Tool calls | Structured-output only | `StructuredRequest` (grading, extraction) | None in the chat path |
| Mastery updates from chat | **No** | — | A whole conversation produces no evidence |

## 3. Why replies feel like a chatbot — root causes, not symptoms

The spec lists symptoms: short, generic, non-interactive, no progression, no
diagnostic questions, no depth. Each traces to a structural cause.

### 3.1 The tutor is stateless

`ChatIn.messages` is the entire transcript, resent by the client every turn. The
server keeps nothing between turns: no session goal, no current concept, no record
of what was explained, no misconceptions noticed. Every reply is generated from
"here is a transcript, say something" — which is the definition of a chatbot.
Continuity across a page refresh does not exist at all.

### 3.2 The learner model exists but is invisible to the tutor

`ConceptMastery` holds per-concept Beta posteriors with components. `Mistake`
holds confident wrong answers flagged as misconceptions. `Explanation` holds every
Feynman attempt and Socratic dialogue verbatim. `Goal` holds deadlines and
projected mastery. **None of it is in the prompt.** The tutor teaching "the
unconscious" does not know the learner scored 31 on it yesterday, or wrote an
explanation that confused it with the preconscious, or has an exam in nine days.
Adaptation is impossible without this, whatever the prompt says.

### 3.3 Chat produces no evidence

The mastery engine weighs evidence by grader and difficulty — but only from
reviews, graded answers and Feynman/Socratic submissions. A learner who explains
repression correctly in their own words mid-conversation moves nothing. The
richest signal in the product is discarded.

### 3.4 In a notebook, the pedagogy prompt is thrown away

`_assemble` swaps the *entire* system prompt for `rag.answer` when material is
found. The main surface — the tutor rail inside a notebook — is therefore a
citation Q&A engine with no teaching instructions at all. This alone explains most
of "responds but does not teach": the code path most people hit has the tutor
prompt removed by design.

### 3.5 The prompts are style sheets, not teaching policy

`tutor.explain.v1.md` is good prose about tone (lead with the idea, one analogy,
end with a question). It says nothing about: orienting before explaining,
intuition before terminology, one concept at a time, diagnostic vs. vague
questions, what to do with a partial answer, when to switch strategy, how depth
should follow the learner. The five modes are five personalities; the spec is
right that Socratic should be a *strategy* the professor chooses, not a costume.

### 3.6 No response planning

There is no decision step between "transcript arrived" and "generate". Intent,
current concept, learner state, strategy, whether to check understanding — none
of it is computed or passed. The model is asked to improvise all of it from the
transcript on every turn, with no memory of having done so before.

### 3.7 No domain awareness

A Freud question and a Python question hit the same 11-line prompt.

### 3.8 Model and request shape

`claude-sonnet-4-5` by default, `max_tokens` at the capability cap, no
`thinking`, no `effort`, no prompt caching (raw httpx builds the payload by hand;
the system prompt is re-billed in full every turn). The spec's Phase 2 (model
quality review) has real headroom: the teaching path is not routed to a
teaching-grade configuration.

### 3.9 Latency shape

Retrieval — an embedding call plus two index scans — runs to completion before
the model is even called. First-token latency is `embed + search + model TTFT`,
serialised. Nothing is cached across turns. Nothing is deferred.

## 4. What is *good* and must survive the rebuild

- **Citation enforcement** (`CitationFilter`) — sentence-buffered, drops invented
  citations before the learner reads them. This is a real differentiator; the
  professor must keep it.
- **"Not in your materials" refusal** with a labelled path to general knowledge —
  keep, and let the professor *teach around* the gap rather than just refuse.
- **Versioned prompt files** with front matter — the right substrate for
  `NOEMA_CORE / TEACHING_PRINCIPLES / DOMAIN_POLICY / ...` composition.
- **Per-task routing** in the registry — the hook for a dedicated teaching model.
- **The evidence-weighted mastery engine** — conversational evidence should feed
  it, not replace it.
- **Structured-output plumbing** (`StructuredRequest`, JSON schema validation) —
  the path for pedagogical metadata.

## 5. Blocker for Phases 1, 2, 15–17

**There is no real model behind the deployed tutor.** Production runs
`NOEMA_DEFAULT_PROVIDER=mock`; no `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` exists
locally or on the service. The mock provider returns deterministic text.

Consequences, stated plainly:

- Baseline conversations (Phase 1) recorded against the mock are meaningless.
- Model quality review (Phase 2) cannot run.
- The Freud golden test and the multi-turn eval suite (Phases 15–16) can be
  *written* now, but cannot be *passed or failed* until a model is configured.

Architecture phases (3–14) can proceed against the mock, with the plumbing tested
in CI as everything else is. But "conversations become better teachers" is not a
claim anyone can make from mock output, and this document will not pretend
otherwise.

The product already has the mechanism to fix this without anyone handling a key on
another's behalf: **Settings → AI providers → Add a key** stores it encrypted
(AES-256-GCM, write-only API). The moment a key is present, the tutor path uses
it. That is the unblock for everything above.

## 6. What the rebuild must therefore introduce

Derived from §3, in the order the spec's execution plan implies:

1. **A persisted `TeachingSession`** — goal, subject, current concept, depth,
   strategy, recent understanding, misconceptions — keyed to a learner and a
   journey, updated every turn. Kills §3.1.
2. **A learner-context block in the prompt** — mastery for the concepts in play,
   open misconceptions, recent explanations, active goal. Kills §3.2.
3. **Pedagogical metadata on every reply** — `concepts_taught`, `knowledge_check`,
   `mastery_evidence`, `misconception`, `next_action` — validated, never shown
   raw, fed to the mastery engine with conversational evidence weights. Kills
   §3.3 and gives §3.6 its `TeachingDecision`.
4. **Prompt composition**, not prompt replacement — `rag.answer` becomes a
   *policy layer* on top of the teaching core, never a substitute. Kills §3.4.
5. **A teaching policy** written as pedagogy (orient → explain → check → adapt →
   deepen), strategy selection and strategy *switching*, depth states, diagnostic
   questioning, response-to-wrong-answer — and modes demoted to strategies.
   Kills §3.5.
6. **Domain policies** — four or five short ones by macro-domain, chosen in-request.
   Kills §3.7.
7. **A teaching-grade model configuration** — dedicated route, thinking on,
   caching on the stable prefix, metadata via structured output alongside the
   streamed text. Addresses §3.8 and §3.9.
8. **Evals that judge lessons, not answers** — multi-turn, simulated students,
   a human review set, a saved baseline — with the Freud conversation as the
   golden path.
