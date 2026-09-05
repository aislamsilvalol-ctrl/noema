# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.0 onward.

Entries are written by hand as phases ship, grouped to match `ROADMAP.md`. This file
previously claimed to be generated from [Conventional Commits](https://www.conventionalcommits.org/);
it never was — commit messages here are prose, not that format — and the claim just let
this file stop mattering once nobody was checking it against the code. It stopped after
Phase 1 while Phases 2 through 5 shipped underneath it. What follows is that gap closed,
against `ROADMAP.md` as it stands today, not against memory of what was planned.

## [Unreleased]

### Added

- **Professor Engine (V3)** — `noema/professor/`: a learning journey per goal
  (parsed goal → curriculum), a router that decides each turn's move before
  the model speaks, a per-journey student model projected from append-only
  mastery events, layered memory with a context compactor (summaries, archive,
  hand-off), flashcards written when a concept lands, checkpoint assessments
  with a remediation loop, server-validated learning blocks emitted as SSE
  events, and usage recorded per feature with cached tokens. Migration 0019.
  Web: segmented replies, in-chat flashcard deck and exam view, course strip,
  contextual actions, Mino move states, admin professor-economy panel,
  landing PATH beat. See `NOEMA_V3_PROFESSOR_ENGINE.md`.

- Architecture design documents: topology, data model, AI provider layer, ingestion/RAG
  pipeline, Mastery Engine formulas, FSRS integration, Adaptive Learning Engine.
- Monorepo skeleton (`apps/api`, `apps/web`, `packages/`).
- Reference implementations of the FSRS scheduler and Mastery Engine as pure functions,
  with unit and property tests.
- `AIProvider` protocol, capability descriptors and provider registry.
- Docker Compose stack: web, api, worker, postgres+pgvector, redis.
- CI: lint, typecheck, tests, build, evals, dependency and secret scanning.
- Open-source project files: contributing guide, code of conduct, security policy,
  issue and pull request templates, roadmap.

#### Phase 1 — Foundation

- FastAPI service: RFC 9457 problem details, structured logging with request ids and
  secret redaction, security headers, `/health` and `/health/ready`.
- PostgreSQL schema and the initial Alembic migration, including the pgvector column,
  HNSW index and generated `tsvector` for Phase 2 hybrid retrieval.
- Authentication: argon2id, httpOnly cookie sessions, refresh rotation with reuse
  detection, CSRF double-submit on mutations.
- Owner-scoped repository layer — tenancy filtering is structural, not per-endpoint.
- Workspace, subject, notebook and note CRUD with cursor pagination.
- AI provider layer: registry, task-class routing, and Anthropic, OpenAI, Ollama and
  deterministic mock implementations.
- AI gateway: per-task timeouts, jittered retries on retryable failures only, provider
  fallback, token accounting and a daily budget guard.
- BYOK credential storage with AES-256-GCM envelope encryption, context-bound AAD and
  key rotation; write-only API surface.
- Streaming tutor chat over SSE with five versioned prompt modes.
- Next.js web app: design tokens, three-region shell, command palette, landing page,
  auth, library, note editor with autosave, tutor panel, provider settings.
- Backend test suite covering the engines, crypto, redaction, gateway, provider wire
  formats and OpenAPI response-schema contracts; grows with every phase below rather
  than being called out again per-phase.

#### Phase 2 — Knowledge

- Upload pipeline: format validation by content (not filename), per-user storage
  quotas, checksum dedupe.
- Parsers for PDF (with OCR fallback), DOCX, MD, TXT, CSV, URL and transcripts, into
  a shared intermediate representation.
- Structure-aware chunking that keeps heading paths and page anchors per chunk.
- Batched embedding pipeline with an HNSW index and a Redis cache keyed on text and
  model, so re-ingesting after a chunking change doesn't re-buy unchanged vectors.
- Hybrid retrieval (dense + full-text, reciprocal rank fusion); reranking is still open.
- Grounded answering: citations enforced against what was actually retrieved, and an
  honest refusal when the material doesn't answer the question.
- Concept extraction with deterministic resolution and merge.
- Knowledge graph: storage, DAG validation on prerequisite edges, a keyboard-navigable
  visualiser.
- Global semantic search across a user's material.
- Eval harness (recall@k, refusal rate) over a labelled corpus, with thresholds
  enforced in CI on every push.

#### Phase 3 — Learning *(in progress — see `ROADMAP.md`)*

- Flashcards: basic, definition, concept and code types; cloze deletions and reverse
  cards. Image cards exist at the API level (upload, owner-scoped serving) with no
  web UI yet to create or display one. The review session UI itself — keyboard-first,
  offline-tolerant — is not built.
- AI card generation, arriving unapproved until a human reviews them.
- FSRS scheduler with invariant/property tests against the reference algorithm.
- Question generation (mcq, true/false, fill-in-the-blank, ordering, open) and
  answering, every type keyboard-operable.
- Semantic AI grading for open answers: rubric-scored, partial credit, missing-concept
  feedback.
- Confidence capture on every answer.
- Mistake Bank: wrong, confident answers flagged as misconceptions, each row leading
  back into a drill question.
- Mastery Engine with a stored component breakdown, not just a headline number.
- Exam mode: assisted or free, timed, with concept-level results.
- Progress screen: mastery and its breakdown, a review forecast, the system's own
  calibration against itself.

#### Phase 4 — Intelligence

- Adaptive Learning Engine: candidate generation, a utility function, constrained
  session selection.
- Session plans that explain themselves — a `rationale` on every block.
- Prerequisite Engine: blocking prerequisites detected, prioritised, and named in the
  plan's own rationale.
- Misconception correction: the wrong belief is named, discriminating questions are
  written against it, and it only resolves on spaced evidence — never on one lucky
  answer.
- Study goals with deadlines, an ordered path to them, and an honest verdict (with a
  required daily pace) when the date doesn't fit.
- Feynman Mode: explain a concept back, judged against the learner's own material,
  counted as evidence.
- Socratic Mode: a dialogue that concludes and counts as evidence.
- Per-user FSRS parameter optimisation, fitted on a learner's earlier reviews and
  judged on their later ones.
- Counterfactual replay harness for evaluating scheduler changes against real history.

#### Phase 5 — Platform *(in progress — see `ROADMAP.md`)*

- Plugin SDK for AI providers: an installed package registers itself under the
  `noema.providers` entry-point group and is discovered at startup, isolated from
  built-ins so one broken plugin can't take a deployment down. Importers, exporters,
  question generators and themes are not plugin points yet.
- Public REST API with scoped bearer tokens, checked once and centrally so a route
  added later is scoped by construction.
- Import from Anki (`.apkg`, review history carried across), Obsidian (zipped vault,
  wikilinks read as titles) and Notion (zipped "Markdown & CSV" export). Readwise and
  Zotero import are not built — the export formats aren't well-understood enough yet
  to import against blind.
- Export to Anki (`.apkg`, review history included) and to Markdown (one notebook, or
  a full account).
- Full account data export (Markdown + original files + JSON) and account deletion
  with a real purge — rows, uploaded files, and any images attached to cards.
- Hardened self-hosting: `scripts/backup.sh`/`restore.sh` for database and uploads,
  with the restore path proven in CI against a real database rather than trusted on
  faith. Upgrades and single-user mode were already real.
- Local mode as a supported, tested configuration — network egress blocked at the
  runtime, asserted in CI, not just documented.
- Community extension registry is not built.

[Unreleased]: https://github.com/aislamsilvalol-ctrl/noema/commits/main
