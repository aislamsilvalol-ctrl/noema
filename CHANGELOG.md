# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.0 onward.

Entries are generated from [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

### Added

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
- 92 backend tests covering the engines, crypto, redaction, gateway, provider wire
  formats and OpenAPI response-schema contracts.

[Unreleased]: https://github.com/aislamsilvalol-ctrl/noema/commits/main
