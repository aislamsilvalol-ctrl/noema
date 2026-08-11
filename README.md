<div align="center">

# NOEMA

### Learn anything. Remember everything.

An open-source adaptive learning platform that turns your documents, notes and questions
into a system that knows what you understand — and what you're about to forget.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-0E0E10.svg)](./LICENSE)
[![CI](https://github.com/aislamsilvalol-ctrl/noema/actions/workflows/ci.yml/badge.svg)](https://github.com/aislamsilvalol-ctrl/noema/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-architecture-2C4A7C.svg)](./docs/architecture.md)

[Quick start](#quick-start) · [Architecture](./docs/architecture.md) · [Roadmap](./ROADMAP.md) · [Contributing](./CONTRIBUTING.md) · [Self-hosting](./docs/self-hosting.md)

</div>

---

> **Project status: pre-alpha.** Phase 1 is complete — auth, the notebook hierarchy, the
> rich-text editor with slash commands and selection actions, the AI provider layer with BYOK,
> and streaming tutor chat. Phase 2 is in progress. Most of the Features table below still
> describes the system being built rather than what runs today. Nothing here is
> production-ready, and the
> [open issues](https://github.com/aislamsilvalol-ctrl/noema/issues) are genuinely open.

## What it is

Most study tools store what you put in. NOEMA models what you *know*.

You give it your material — PDFs, papers, lecture notes, textbook chapters, your own
writing. It extracts the concepts, works out which ones depend on which, and builds a
knowledge graph. Then it watches you: every review, every answer, every confident mistake
updates a per-concept estimate of your understanding and of how fast it's fading.

When you sit down with 30 minutes, NOEMA already knows what those 30 minutes should contain.

```
Material → Understanding → Practice → Assessment → Memory → Mastery
```

## Why it's different

**It models concepts, not cards.** A flashcard app knows you failed card #4,182. NOEMA knows
you're failing backpropagation *because* your chain rule mastery is 38%, and it reroutes you
there before you waste another week.

**It catches confident errors.** Answer wrong while certain you're right, and you've found a
misconception — the one failure mode spaced repetition never catches, because you'd never
flag it for review yourself. NOEMA detects it and generates questions specifically designed
to break the wrong model.

**It schedules with FSRS.** Real spaced repetition — stability, difficulty, retrievability —
with parameters fit to your own review history, not a 1987 heuristic.

**It only answers from your materials.** RAG with enforced citations: source, page, excerpt.
When the answer isn't in your documents, it says so instead of inventing one.

**It can run entirely on your machine.** Ollama plus local embeddings. Documents,
embeddings, conversations and progress never leave your laptop.

## Features

| | |
|---|---|
| **Notebooks** | PDF, DOCX, MD, TXT, CSV, URLs, transcripts — parsed, chunked, embedded, indexed |
| **Knowledge Graph** | Automatic concept extraction with typed prerequisite edges, interactive and editable |
| **Mastery Engine** | 0–100 per concept from correctness, difficulty, confidence, recency and retrievability — [with the math published](./docs/mastery-engine.md) |
| **FSRS scheduling** | Seven card types, per-user optimised parameters, workload forecasting |
| **Quizzes & exams** | Seven question types, dynamic difficulty, semantic AI grading with rubrics |
| **Mistake Bank** | Every error stored with its concept and your confidence; practise them as a session |
| **Adaptive sessions** | A time budget in, an explained study plan out |
| **Tutor modes** | Explain · Socratic · Examiner · Study Partner · Feynman Evaluator |
| **Semantic search** | Hybrid vector + full-text across notebooks, documents, notes, cards and chats |
| **BYOK & local mode** | Anthropic, OpenAI, Gemini, OpenRouter, Ollama — your keys, encrypted, never exposed |

## Quick start

```bash
git clone https://github.com/aislamsilvalol-ctrl/noema.git
cd noema
cp .env.example .env
docker compose up
```

Frontend at `http://localhost:3000`, API docs at `http://localhost:8000/docs`.

Fully local, no cloud provider, nothing leaves your machine:

```bash
ollama pull llama3.1 && ollama pull nomic-embed-text
NOEMA_MODE=local docker compose up
```

CI runs exactly these steps from a clean clone on every push, so if the quick start breaks,
the build goes red before you find out the hard way.

Local development without Docker is documented in [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Architecture

```
┌──────────────┐            ┌───────────────────┐
│  web         │  REST/SSE  │  api              │
│  Next.js 15  │ ─────────► │  FastAPI · Python │
│  TypeScript  │ ◄───────── │  OpenAPI 3.1      │
└──────────────┘            └─────────┬─────────┘
                                      │
         ┌────────────────┬───────────┴────────────┬──────────────────┐
         ▼                ▼                        ▼                  ▼
   PostgreSQL 16     Redis 7               Dramatiq worker      AI Gateway
   + pgvector        cache · broker        ingestion · jobs     multi-provider
```

Design documents:

- [Architecture](./docs/architecture.md) — topology, boundaries, and what we chose not to build
- [Data model](./docs/data-model.md) — schema, and why evidence is append-only
- [AI providers](./docs/ai-providers.md) — the abstraction, BYOK encryption, prompt versioning
- [Ingestion & RAG](./docs/ingestion-rag.md) — chunking, hybrid retrieval, grounded answering
- [Mastery Engine](./docs/mastery-engine.md) — the formulas, in full
- [FSRS](./docs/fsrs.md) — integration and parameter optimisation
- [Learning Engine](./docs/learning-engine.md) — how the next 30 minutes get chosen
- [API](./docs/api.md) · [Design system](./docs/design-system.md) · [Self-hosting](./docs/self-hosting.md)

## Configuration

| variable | default | purpose |
|---|---|---|
| `NOEMA_MODE` | `cloud` | `local` restricts to on-device models and blocks egress |
| `DATABASE_URL` | — | PostgreSQL 16 with the `vector` extension |
| `REDIS_URL` | — | cache and job broker |
| `NOEMA_MASTER_KEY` | — | 32-byte base64 KEK wrapping user API keys |
| `NOEMA_DEFAULT_PROVIDER` | `ollama` | `anthropic` · `openai` · `gemini` · `openrouter` · `ollama` |
| `NOEMA_EMBEDDING_MODEL` | `nomic-embed-text` | pinned per deployment; changing it re-embeds |
| `NOEMA_ALLOW_SIGNUPS` | `true` | set `false` for a single-user install |

Full list in [`.env.example`](./.env.example).

## Roadmap

| phase | scope | status |
|---|---|---|
| **1 — Foundation** | auth, schema, notebooks, notes, provider abstraction, AI chat | shipped |
| **2 — Knowledge** | ingestion, RAG, embeddings, semantic search, concept extraction, graph | in progress |
| **3 — Learning** | flashcards, FSRS, quizzes, exams, Mistake Bank, mastery | designed |
| **4 — Intelligence** | adaptive scheduling, prerequisites, misconceptions, Feynman, Socratic | designed |
| **5 — Platform** | plugin SDK, public API, integrations, community extensions | planned |

Detail in [`ROADMAP.md`](./ROADMAP.md).

## Contributing

Contributions are welcome, and the architecture was written to make them possible — engines
are pure functions, providers are one file plus a registry entry, document formats plug into
a shared intermediate representation.

Start with [`CONTRIBUTING.md`](./CONTRIBUTING.md) and the
[`good first issue`](https://github.com/aislamsilvalol-ctrl/noema/labels/good%20first%20issue) label.
If you're proposing something that changes the learning model, open a discussion first —
those decisions need evidence, and we'd rather argue before the code is written.

## Privacy

Your material is yours. Export everything at any time, delete your account and have the data
actually purged, run entirely offline, or bring your own keys so inference never touches our
infrastructure. **Documents are never used for model training.** See
[`SECURITY.md`](./SECURITY.md) for the threat model and disclosure process.

## License

[AGPL-3.0](./LICENSE). If you run a modified NOEMA as a network service, those modifications
have to stay open too. That's deliberate — the learning model is the point, and it should
stay inspectable by the people it's modelling.
