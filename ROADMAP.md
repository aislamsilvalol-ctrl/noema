# Roadmap

Phases are ordered by dependency, not by ambition. Each ends with something usable — no
phase exists purely as scaffolding for the next.

Dates are deliberately absent. This is an open-source project built in the open; the order is
a commitment, the timing is not.

---

## Phase 1 — Foundation *(complete)*

Goal: **you can put material in and talk to it.**

- [x] Monorepo, tooling, CI (lint, typecheck, test, build on every PR)
- [x] PostgreSQL 16 + pgvector schema, Alembic migrations
- [x] Auth: argon2id, cookie sessions, refresh rotation, CSRF
- [x] Workspace → Subject → Notebook hierarchy
- [x] Markdown note editor with slash commands and selection actions
- [x] `AIProvider` abstraction + Anthropic, OpenAI, Ollama implementations
- [x] AI gateway: retries, timeouts, fallback, token accounting, redaction
- [x] BYOK credential storage (AES-GCM, write-only endpoints)
- [x] Streaming AI chat scoped to a notebook
- [x] Design system tokens, shell layout, dark/light
- [x] `docker compose up` works from a clean clone — verified in CI on every push

**Exit criterion:** a new contributor clones, runs `docker compose up`, creates a notebook,
and chats with a local Ollama model without editing a config file.

---

## Phase 2 — Knowledge *(in progress)*

Goal: **the system understands the material, and never makes things up about it.**

- [x] Upload pipeline with validation, quotas, checksum dedupe
- [x] Parsers: PDF (+OCR fallback), DOCX, MD, TXT, CSV, URL, transcripts → shared IR
- [x] Structure-aware chunking with heading paths and page anchors
- [ ] Embedding pipeline — batched embedding and the HNSW index are in; the cache is not
- [x] Hybrid retrieval (vector + full-text, RRF) — reranking still open
- [x] Grounded answering: enforced citations, refusal when unsupported
- [x] Concept extraction + deterministic resolution/merge
- [ ] Knowledge graph storage and DAG validation done; the interactive visualiser is not built
- [x] Global semantic search
- [ ] Eval harness for extraction and citation accuracy

**Exit criterion:** upload a textbook chapter, ask a question, get an answer with a page
citation you can verify — and get an honest "not in your materials" when it isn't.

---

## Phase 3 — Learning *(in progress)*

Goal: **practice, and a number that means something.**

- [ ] Flashcards — basic, definition, concept and code work; cloze, reverse and image do not
- [x] AI card generation with mandatory human review before activation
- [x] FSRS implementation with parity tests against the reference
- [ ] Review session UI, keyboard-first, offline-tolerant queue
- [ ] Question generation — five types generate; matching and code do not
- [x] Semantic AI grading with rubrics, partial credit, missing-concept feedback
- [x] Confidence capture
- [ ] Mistake Bank — mistakes are recorded and listed; the practice session is not built
- [x] Mastery Engine with stored component breakdown
- [ ] Exam mode: assisted-free, timed, with concept-level results
- [ ] Analytics dashboard

**Exit criterion:** a month of daily use produces mastery scores a user agrees with when
they read the breakdown.

---

## Phase 4 — Intelligence *(in progress)*

Goal: **you stop deciding what to study.**

- [x] Adaptive Learning Engine: candidate generation, utility, constrained selection
- [x] Explained session plans (`rationale` on every block)
- [ ] Prerequisite Engine — blocking prerequisites are detected and prioritised; the explicit reroute message is not written
- [ ] Misconception detection works and drills are scheduled; generated correction questions are not
- [ ] Study goals, deadlines, generated learning paths
- [ ] Feynman Mode (explain-back evaluation)
- [ ] Socratic Mode
- [ ] Per-user FSRS parameter optimisation
- [x] Counterfactual replay harness for scheduler changes

**Exit criterion:** "Start Session" is the primary action on the dashboard, and users take it
without second-guessing the plan.

---

## Phase 5 — Platform

Goal: **other people extend it.**

- [ ] Plugin SDK: providers, importers, exporters, question generators, themes
- [ ] Public REST API with scoped tokens
- [ ] Import from Anki, Obsidian, Notion, Readwise, Zotero
- [ ] Export to Anki and Markdown
- [x] Data export (zip: Markdown + original files + JSON) and account deletion with purge
- [ ] Hardened self-hosting: backups, upgrades, single-user mode
- [ ] Local mode as a fully supported, tested configuration
- [ ] Community extension registry

---

## Explicitly out of scope

Social feeds, leaderboards, XP, badges, streak guilt. Real-time collaborative editing.
Being a general note-taking app. Being a chat product.

Every proposal is measured against one question: **does this help someone actually learn and
remember?** If the honest answer is no, it doesn't ship — however good the demo looks.
