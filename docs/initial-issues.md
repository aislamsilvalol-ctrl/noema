# Seed issues — Phase 1

Ready to file once the repository is on GitHub. `scripts/seed_issues.sh` creates them with
the `gh` CLI. Ordered by dependency; the `good first issue` set is deliberately
self-contained so a newcomer can finish one without understanding the whole system.

Labels used: `phase-1`, `backend`, `frontend`, `infra`, `ai`, `security`, `docs`,
`good first issue`, `help wanted`.

---

### #1 — Scaffold the FastAPI service · `phase-1` `backend`
App factory, settings via pydantic-settings, structlog JSON logging with request ids, RFC
9457 error handlers, `/health` and `/health/ready`. No business logic.
**Done when:** `uvicorn noema.main:app` serves `/docs` and both health endpoints, and
`mypy --strict` passes.

### #2 — Database schema and migrations · `phase-1` `backend`
SQLAlchemy 2.0 models for users, workspaces, subjects, notebooks, sources, chunks, notes.
Alembic baseline enabling the `vector` extension. HNSW index on `chunks.embedding`, GIN on
`chunks.tsv`. Follow [`docs/data-model.md`](./data-model.md).
**Done when:** `alembic upgrade head` then `downgrade base` runs cleanly against Postgres 16.
**Blocked by:** #1

### #3 — Auth: registration, login, sessions · `phase-1` `backend` `security`
argon2id hashing, httpOnly `SameSite=Lax` cookies, rotating refresh tokens with reuse
detection, CSRF double-submit on mutations, per-account and per-IP rate limits.
**Done when:** tests cover refresh rotation, reuse detection, CSRF rejection, and lockout.
**Blocked by:** #2

### #4 — Owner-scoped repository layer · `phase-1` `backend` `security`
Every query filtered by owner at the repository layer, never by callers remembering to.
**Done when:** a cross-tenant test suite asserts 404 (not 403) for every resource type.
**Blocked by:** #2

### #5 — Workspace / subject / notebook CRUD · `phase-1` `backend`
**Blocked by:** #4

### #6 — `AIProvider` protocol and registry · `phase-1` `ai`
The interface in `providers/base.py` already exists. Add the registry, capability
resolution, and a shared contract test suite every provider must pass.
**Done when:** a mock provider passes the contract suite and is selectable via
`NOEMA_DEFAULT_PROVIDER=mock`.

### #7 — Ollama provider · `phase-1` `ai` `good first issue`
Implement `AIProvider` against the Ollama HTTP API: chat, streaming, embeddings, prompted
structured output with schema-validated retry. This is the reference example in
`CONTRIBUTING.md`.
**Blocked by:** #6

### #8 — Anthropic provider · `phase-1` `ai` `good first issue`
Chat, streaming, native structured output. Declares `embeddings: False` — capability
negotiation should route embeddings elsewhere without special-casing.
**Blocked by:** #6

### #9 — OpenAI provider · `phase-1` `ai` `good first issue`
Chat, streaming, embeddings, native structured output.
**Blocked by:** #6

### #10 — AI gateway · `phase-1` `ai`
Timeouts per task class, retry with jitter on 429/5xx only, provider fallback with UI
attribution, token accounting to `ai_usage`, daily budget guard that degrades rather than
fails, and key redaction in logs.
**Done when:** a test asserts a known key string never appears in captured log output.
**Blocked by:** #6

### #11 — BYOK credential storage · `phase-1` `security`
AES-256-GCM, versioned data key wrapped by `NOEMA_MASTER_KEY`. Write-only endpoints.
**Done when:** a test asserts no response schema in the app can carry a plaintext key.
**Blocked by:** #3, #10

### #12 — Streaming chat endpoint · `phase-1` `backend` `ai`
`POST /api/v1/ai/chat` over SSE, scoped to a notebook, with cancellation.
**Blocked by:** #10

### #13 — Design tokens and app shell · `phase-1` `frontend`
Tokens from [`docs/design-system.md`](./design-system.md), three-region shell, dark/light,
Focus Mode chrome. shadcn/ui restyled to the tokens.

### #14 — Generated API client · `phase-1` `frontend` `infra`
Generate TypeScript types from `/openapi.json` in CI; fail the web typecheck on drift.
**Blocked by:** #1

### #15 — Note editor · `phase-1` `frontend`
Markdown source of truth, rich-text editing, headings, lists, checklists, callouts, code,
LaTeX, tables, `[[wiki-links]]`, images. Slash commands registered but no-op until Phase 3.
**Blocked by:** #13

### #16 — Selection actions · `phase-1` `frontend` `ai`
Select text → Explain · Simplify · Expand · Ask AI. Results stream into a panel and are
never auto-saved into the note.
**Blocked by:** #12, #15

### #17 — Command palette (⌘K) and Ask NOEMA (⌘J) · `phase-1` `frontend`
**Blocked by:** #13

### #18 — Docker Compose from a clean clone · `phase-1` `infra`
Dockerfiles for api and web, healthchecks, `docker compose up` working with no manual steps
beyond `cp .env.example .env`.
**Done when:** a CI job clones fresh, brings the stack up, and hits `/health/ready`.

### #19 — Local mode egress blocking · `phase-1` `infra` `security`
`docker-compose.local.yml` attaching api and worker to an internal-only network; UI hides
cloud-only features under `NOEMA_MODE=local`.
**Blocked by:** #18

### #20 — Data export and account deletion · `phase-1` `backend` `security`
`POST /me/export` (complete portable archive) and `DELETE /me` (30-day purge covering
embeddings and object storage). Phase 1, not "later" — this is a promise in the README.
**Blocked by:** #4

### #21 — Contributor onboarding docs · `phase-1` `docs` `good first issue`
Verify the `CONTRIBUTING.md` steps on a clean machine and fix whatever is wrong. Genuinely
useful: setup instructions rot faster than code.

---

## Not yet filed

Phase 2+ issues wait until Phase 1 lands. Opening 80 issues against unwritten code produces
a graveyard, not a roadmap.
