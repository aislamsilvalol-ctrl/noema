# NOEMA — System Map

Generated 2026-09-02, Phase 2 of the Launch Readiness program. Reflects the real
codebase at commit `2782f74` (PR #132, the Stripe webhook typed-object fix),
`aislamsilvalol-ctrl/reconcile-noema-orca-agents` branch, not the brief's category
list. Read-only audit — nothing below was changed to produce this document.

## 1. Shape of the system

Two deployables (`apps/api` FastAPI, `apps/web` Next.js), one shared Postgres 16 +
pgvector database, one Redis instance doing double duty (rate-limit token buckets,
embedding cache, Dramatiq broker), object storage abstracted behind a `local`/`s3`
driver, hosted on Railway with GitHub Actions CI (`api`, `web`, `security`,
`compose` jobs — the summary's "stack" job name from memory is actually `compose`).
No email-sending integration exists anywhere in the codebase (verified: no
SendGrid/Postmark/Resend/SMTP/SES import or call in any `.py` file) — this is a
real, current gap, not an oversight in this map.

## 2. Request path

`apps/web` (Next.js App Router) → same-origin `/api/v1/[...path]` proxy route
(`apps/web/src/app/api/v1/[...path]/route.ts`, inert unless `NEXT_PUBLIC_DEMO=1`) →
FastAPI `noema/main.py`, mounting one router per domain under `noema/api/v1/`:
`auth`, `account`, `admin`, `ai`, `billing`, `concepts`, `exports`, `imports`,
`library`, `meta`, `notes_actions`, `sources`, `study`, `tokens`. Every mutating
route runs through `noema/api/middleware.py`'s CSRF check (double-submit cookie),
enforced generically and covered by a contract test
(`tests/test_api_contract.py::test_every_mutation_is_csrf_protected`) that walks
the real route table rather than a hand-maintained router list (the older
hand-maintained-tuple version was the class of gap that let PR #118's admin-router
CSRF hole ship briefly — that specific structural weakness is fixed as of this
audit, confirmed by reading the test).

Auth: `noema/services/auth.py` + `noema/api/v1/auth.py` — argon2id passwords,
cookie sessions (`Session` table), refresh rotation. Only four endpoints exist:
`register`, `login`, `refresh`, `logout`, `me`. **No password-reset or
email-verification flow exists at any layer** — consistent with "no email
integration" above; a user who forgets their password today has no self-service
recovery path.

## 3. Data model (`noema/db/models.py`, 39 entity/enum classes)

Ownership hierarchy: `Workspace → Subject → Notebook → {Note, Source → Chunk}`,
all inheriting `OwnedEntity` (an `owner_id` column enforced at the query layer,
not just the schema — `retrieval/grounding.py` and `retrieval/search.py` both
filter every chunk read by `Chunk.owner_id == owner_id`, confirmed by direct
grep, no unscoped read path found in either file).

Learning entities: `Concept`/`ConceptEdge` (knowledge graph), `Card`/`CardSchedule`
(FSRS-scheduled flashcards), `Review`, `ConceptMastery`, `Question`/`Answer`,
`Mistake`, `StudySession`, `Exam`, `Explanation`, `Goal`.

SaaS entities (all added by the 2026-08-29 pivot, PRs #108-120): `Plan` (enum:
free/student/pro/max), `PlanConfig` (admin-editable monthly price + AI unit
allowance + margin math, migration `0014`), `ModelTier` (economy/standard/premium)
+ `ModelTierConfig` (maps a tier to a real provider+model ID and its $/token
cost), `AIUsage` (one row per model call — provider/model/task/tokens/cost),
`StripeEvent` (webhook dedup, migration `0015`), `ProviderCredential` (BYOK,
AES-GCM encrypted), `ApiToken`.

## 4. AI subsystem — three layers, not one monolith

**Layer 1 — Gateway** (`noema/providers/gateway.py`, 301 lines): retries,
per-`TaskClass` timeouts, provider fallback, daily token-budget guarding
(`noema_ai_daily_token_budget` + interactive reserve), and the token-accounting
callback that writes `AIUsage` rows. `noema/providers/registry.py` resolves a
provider name (`anthropic`/`openai`/`gemini`/`openrouter`/`ollama`) to a live
`AIProvider` instance, BYOK-aware via `credentials.py`.

**Layer 2 — Pricing/tiering** (`noema/services/pricing.py`, `PricingService`):
maps `ModelTier` → real model ID + real $/token cost, sourced from
`ModelTierConfig` rows seeded with live-fetched Anthropic pricing (per
`noema_saas_pivot_2026-08-29.md`, re-verified 2026-08-31 against
`platform.claude.com/docs`). `noema/services/entitlements.py` (108 lines) checks
a user's calendar-month `AIUsage` sum against their `PlanConfig.monthly_ai_units`
**before** the gateway is ever called — a blocked turn costs the platform
nothing, confirmed by reading the call order in `ai.py`'s `professor_chat`.

**Layer 3 — Orchestration** (`noema/services/professor.py`, 244 lines): intent
classification (economy tier, one structured call) → dispatch to one of six
intents (EXPLAIN/DEEPEN/SUMMARIZE/QUIZ_ME/CREATE_FLASHCARD/CREATE_EXAM), each
reusing pre-existing domain logic (`study/generation.py`, `study/exam.py`, the
RAG-grounded chat stream) rather than reimplementing it. `professor_memory.py`
(148 lines) builds bounded mastery + open-misconception context, injected only
into EXPLAIN/DEEPEN. **No system prompt anywhere establishes a "Noema" persona or
an identity-concealment instruction** — grepped every file in `noema/prompts/`;
zero hits for "Noema" as a self-referential name and zero hits for
identity/persona guardrail language. This is the concrete, current gap that
Phase 7 (Noema Identity Layer) of the 34-phase program exists to close — today,
nothing in the prompt stack stops the underlying model from truthfully
identifying its own provider if asked.

## 5. RAG / retrieval pipeline

`ingestion/pipeline.py` (parse via `ingestion/parsers/*` → `chunking.py`
structure-aware chunking → embed, batched, cached in Redis by `providers/cache.py`
keyed on text+model, 30-day TTL) runs inside a Dramatiq actor
(`noema/workers/__init__.py`, `ingest()`), not the request path — the module's own
docstring states why (a 300-page PDF parse is minutes of work over untrusted
input). `retrieval/search.py` (297 lines) does hybrid vector+FTS retrieval with
RRF fusion (`retrieval/fusion.py`); `retrieval/grounding.py` (152 lines) enforces
citation grounding and honest refusal when the corpus doesn't support an answer.
Every retrieval query is owner-scoped (§3).

## 6. Knowledge graph

`knowledge/extraction.py` (LLM-driven concept extraction) → `resolution.py`
(deterministic merge/dedup) → `graph.py` (334 lines, DAG storage + validation) —
feeds `engines/mastery.py` (243 lines, per-concept mastery scoring) and the
FSRS scheduler (`engines/fsrs.py`, 166 lines) that drives `Card`/`CardSchedule`
spaced repetition. `study/correction.py` (297 lines) does misconception
detection/correction against this same graph.

## 7. Study modes

`study/socratic.py` (178 lines) and `study/feynman.py` (199 lines) implement the
two named pedagogical modes independent of the Professor orchestrator (reachable
both via manual mode selection in `POST /ai/chat` and, for Socratic, a dedicated
`POST /study/socratic` route). `study/goals.py` backs `Goal` (deadline-feasibility
study planning). `study/exam.py`/`grading.py`/`evaluation.py`/`questions.py` form
the exam pipeline, reused unchanged by the Professor's `CREATE_EXAM` intent.

## 8. Billing (`noema/services/billing.py`)

Stripe Checkout session creation, Customer Portal, and `handle_webhook()` — the
sole writer of `User.plan` anywhere in the codebase. As of PR #132, the webhook
dispatch converts the Stripe SDK's typed event object to a plain dict once
(`.to_dict()`) at the single dispatch point before any handler runs — confirmed
present at `noema/services/billing.py:185-200`. `StripeEvent` rows make webhook
redelivery a proven no-op. Every route fails closed (`FeatureUnavailable`) if the
five `NOEMA_STRIPE_*` variables aren't set — real behavior as of this audit is
that Stripe is live and configured (per prior session work), not still
unconfigured.

## 9. Admin

`noema/api/v1/admin.py`: `GET /intelligence` (usage aggregation), `POST
/simulator` (labelled hypothetical revenue), `GET/PATCH /users` (list + manual
plan override), `GET /reports/profit`, `GET /reports/users.csv`. Gated by
`deps.AdminUser`, an email-allowlist check (`NOEMA_ADMIN_EMAILS`) — no
admin-role schema, no bootstrap problem. Frontend at `apps/web/src/app/admin`,
unlinked from primary nav.

## 10. Frontend surface

Next.js App Router, top-level routes: `admin`, `explain`, `goals`, `graph`,
`library`, `login`, `mistakes`, `notebooks` (includes `/notebooks/[id]/professor`,
the Noema chat UI), `progress`, `review`, `settings`, `socratic`, `today`, plus
the marketing landing page at `app/page.tsx`. Landing page V2 (PRs #126-131):
orange-primary/blue-secondary brand palette, scroll-driven Mino mascot state
(`components/landing/`, `IntersectionObserver`-based, no scroll-hijacking), i18n,
auth-aware CTA, real pricing pulled from `PlanConfig`. The "Professor Noema" →
"Noema" rename (PR #131) is confirmed fully applied to landing/UI text — zero
remaining occurrences of "Professor Noema" in `page.tsx` or
`components/landing/*.tsx`.

## 11. Jobs / workers

Single Dramatiq worker process (`noema/workers/__init__.py`, 161 lines, one file
— not a package of multiple actor modules) on a Redis broker: `ingest()` (source
processing, retried 3x, 30-min time limit) and `purge_accounts()` (permanent
deletion past the grace period — triggered externally, Dramatiq has no built-in
scheduler; `docs/self-hosting.md` documents the cron/manual trigger requirement).
Account deletion also cancels any active Stripe subscription as of PR #124
(confirmed fixed, not still an open gap).

## 12. CI/CD

`.github/workflows/ci.yml`, four jobs: `api` (schema-currency check, migration
tests including a from-scratch-deploy-shaped migration, pytest, a real-database
eval-report run), `web` (generated-types-currency check, presumably lint/build —
not fully enumerated line-by-line in this pass), `security` (`pip-audit`), and
`compose` (a real `docker compose up` from a clean clone, notebook-creation
end-to-end, a backup/restore round-trip, and — notably — a "local mode has no
route to the internet" network-isolation check for the self-hosted deployment
mode). Deployment target is Railway; `noema_git_sha`/`RAILWAY_GIT_COMMIT_SHA`
drives `/api/v1/meta`'s deploy-verification contract (documented in `config.py`
with the specific 12-14 August stale-deploy incident that motivated it).
