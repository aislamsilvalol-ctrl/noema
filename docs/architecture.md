# NOEMA — Architecture

> Status: design document, revision 1. Everything here is meant to be argued with.

## 1. What the system actually is

NOEMA is a **state machine over a learner's knowledge**. Documents, notes and chats are
inputs; the durable object is a per-user, per-concept belief about what they know, how
stable that knowledge is, and what depends on it.

Almost every product decision follows from that framing. The AI is an *extractor* and an
*interviewer*, not the product. If a feature does not either (a) improve the fidelity of
the knowledge state or (b) act on it to schedule better practice, it does not ship.

```
          ┌──────────── ingestion ────────────┐   ┌──── evidence loop ────┐
Sources → Parse → Chunk → Embed → Concepts →  Knowledge State  ← Reviews / Answers / Confidence
                                   │              │      ▲
                              Knowledge Graph     │      │
                                                  ▼      │
                                        Learning Engine ─┘
                                                  │
                                          Today's Session
```

Two subsystems, one shared object:

- **Ingestion / RAG** writes into the graph (concepts, prerequisites, provenance).
- **Learning Engine** reads the graph plus evidence, and decides what happens next.

## 2. Runtime topology

```
┌──────────────┐   HTTPS    ┌───────────────────┐
│  web (Next)  │ ─────────► │  api (FastAPI)    │
│  RSC + SPA   │ ◄───────── │  OpenAPI 3.1      │
└──────────────┘   SSE      └─────────┬─────────┘
                                      │
              ┌───────────────────────┼────────────────────────┐
              ▼                       ▼                        ▼
     ┌────────────────┐      ┌────────────────┐       ┌────────────────┐
     │ PostgreSQL 16  │      │ Redis 7        │       │ AI Gateway     │
     │ + pgvector     │      │ cache + broker │       │ (in-process)   │
     └────────────────┘      └───────┬────────┘       └───────┬────────┘
                                     ▼                        ▼
                             ┌────────────────┐    OpenAI │ Anthropic │ Gemini
                             │ worker (Dramatiq)│  OpenRouter │ Ollama │ local
                             └────────────────┘
```

Five containers, one `docker compose up`. No Kubernetes, no service mesh, no message bus
beyond Redis. Anything more is a scaling problem we do not have yet, and it would make the
project harder to contribute to — which is a real cost for an open-source project.

**Why FastAPI and not Next API routes for everything:** the heavy work is Python-shaped —
document parsing, embeddings, FSRS, the scheduling optimiser, eventually a trained
retention model. Splitting the AI/ML surface into a typed Python service keeps that code
testable in isolation and lets the graph/scheduling logic be imported by scripts, notebooks
and the worker without dragging a web framework along.

**Why one API service and not microservices:** the learning engine reads from nearly every
table. Splitting it prematurely would produce chatty RPC to reconstruct a single user's
knowledge state. It is a modular monolith: `engines/`, `ingestion/`, `providers/` talk to
each other through explicit interfaces and could be split later if a boundary ever proves
itself under load.

### Request paths

| Path | Transport | Notes |
|---|---|---|
| CRUD (notebooks, notes, cards) | REST/JSON | Fully typed, OpenAPI-generated client |
| AI chat / tutor | SSE stream | Token streaming; citations flushed as a final frame |
| Document upload | REST + presigned PUT | Then a job id the client polls or subscribes to |
| Ingestion progress | SSE | Per-stage: parsing → chunking → embedding → concepts |
| Review answers | REST, batched | Offline-tolerant; client queues and flushes |

## 3. Repository layout

```
noema/
├── apps/
│   ├── api/                    # FastAPI service + worker (same image, different cmd)
│   │   └── noema/
│   │       ├── core/           # config, security, errors, logging, rate limiting
│   │       ├── db/             # SQLAlchemy models, migrations, session
│   │       ├── domain/         # pure dataclasses / value objects, zero I/O
│   │       ├── engines/        # fsrs, mastery, scheduler, misconception, prerequisite
│   │       ├── providers/      # AI provider abstraction + implementations
│   │       ├── ingestion/      # parse, chunk, embed, extract concepts
│   │       ├── api/v1/         # routers, dependencies, schemas
│   │       └── workers/        # Dramatiq actors
│   └── web/                    # Next.js App Router
├── packages/
│   ├── schemas/                # OpenAPI-generated TS types (build artifact)
│   ├── ui/                     # design system primitives
│   └── plugin-sdk/             # Phase 5 — public extension contracts
├── docs/
└── examples/
```

**`domain/` is the important boundary.** Mastery scores, FSRS states, and scheduling
decisions are computed by pure functions over dataclasses. They never touch the database or
an AI provider. That is what makes them testable against fixture data and what will let us
swap the mastery model later without rewriting the API layer.

## 4. Data model

See [`data-model.md`](./data-model.md) for the full schema. The shape in one paragraph:

`User` owns `Workspace`s, which contain `Subject`s, which contain `Notebook`s. A notebook
owns `Source`s (uploaded material), `Note`s (user writing), and `Chunk`s (embedded slices
of sources). `Concept`s are extracted from chunks and linked to each other by
`ConceptEdge`s (typed: `prerequisite_of`, `part_of`, `related_to`, `contrasts_with`).

Evidence objects — `Review`, `Answer`, `Mistake` — are append-only. `ConceptMastery` and
`CardState` are *derived projections* that can be rebuilt from the evidence log. That
property is worth protecting: it means a bug in the mastery formula is recoverable, and it
makes offline experimentation on the scheduling model possible against real history.

## 5. AI provider abstraction

See [`ai-providers.md`](./ai-providers.md). Key constraints:

- One interface: `chat`, `stream`, `embed`, `structured` (JSON-schema-constrained output).
- Capability descriptors, not feature flags — a caller asks "does this provider support
  structured output?" and degrades explicitly rather than throwing at runtime.
- BYOK keys are encrypted at rest with an app-level KEK (AES-GCM via `cryptography`), never
  returned by any endpoint, never logged, and redacted in error paths.
- Every call goes through a gateway that handles retries, timeouts, token accounting and
  provider fallback. No feature code constructs a provider client directly.

## 6. Ingestion & RAG

See [`ingestion-rag.md`](./ingestion-rag.md). Highlights:

- Structure-aware chunking (headings/sections first, token windows second), because
  citation quality depends far more on chunk boundaries than on the embedding model.
- Hybrid retrieval: pgvector cosine + Postgres full-text, fused with Reciprocal Rank
  Fusion, then reranked. Pure vector search is bad at proper nouns and notation.
- Every generated artifact — flashcard, question, concept — stores its `source_chunk_ids`.
  No orphan claims. This is what makes "answer only from my materials" enforceable rather
  than a prompt suggestion.

## 7. Learning intelligence

Three layers, each documented separately:

| Layer | Doc | Question it answers |
|---|---|---|
| FSRS | [`fsrs.md`](./fsrs.md) | When should this *card* be shown again? |
| Mastery Engine | [`mastery-engine.md`](./mastery-engine.md) | How well is this *concept* known? |
| Learning Engine | [`learning-engine.md`](./learning-engine.md) | What should this *person* do in the next 30 minutes? |

They are deliberately separate. FSRS is a well-validated card-level algorithm and we should
not modify it. Mastery is a concept-level aggregate that FSRS knows nothing about.
Scheduling is a constrained selection problem over both.

## 8. Security posture

Detailed in [`SECURITY.md`](../SECURITY.md). Design-time decisions:

- Sessions: httpOnly + `SameSite=Lax` cookies, rotating refresh tokens, CSRF double-submit
  on cookie-authenticated mutations. Bearer tokens only for the public API (Phase 5).
- Uploads: content-type sniffing (not extension trust), size caps, per-user quota, parsing
  in the worker with resource limits. Parsers are the largest attack surface in this system.
- Prompt injection: retrieved document text is untrusted input. It is passed inside a
  delimited, clearly-labelled data block, and the model is never given tools during RAG
  answering. Generated flashcards/questions are structured output, validated against a
  schema before persistence.
- Rate limiting at the edge per user and per provider key, since BYOK means a runaway loop
  spends the *user's* money.

## 9. Privacy / local mode

`NOEMA_MODE=local` changes concrete behaviour, not marketing copy:

- Provider registry restricted to Ollama and local embedding models.
- Outbound network egress from the API container blocked at the compose network level.
- Telemetry disabled and the setting removed from the UI rather than defaulted off.
- Any feature requiring a hosted provider is disabled in the UI with an explanation.

## 10. Design system

See [`design-system.md`](./design-system.md). One sentence: editorial typography, generous
negative space, one accent colour, motion only where it communicates state change.

## 11. What we are explicitly not building

- Social feeds, leaderboards, streak-shaming, XP, badges.
- A general note-taking app. Notes exist to become questions.
- A chat product. Chat is a way to interrogate material, not the destination.
- Real-time collaborative editing (Phase 5 at the earliest, if ever).

## 12. Open questions

1. Concept identity across notebooks — is "gradient descent" in two notebooks one concept
   or two? Current lean: per-workspace canonical concepts with embedding-based merge and a
   user-visible merge/split action.
2. Mastery decay when a concept has no cards yet — currently modelled with a weak prior
   plus prerequisite propagation, but that is untested.
3. Whether AI grading of open answers should feed mastery at full weight. Initial answer:
   discount it (see `mastery-engine.md`, `w_source`) until we have calibration data.
