# Operations

What the API tells an operator about itself, and what to point at what.

## Health endpoints

| Endpoint | Question it answers | Checks | Status |
|---|---|---|---|
| `GET /health` | Is the process up? | Nothing. | Always 200 while the process serves. |
| `GET /health/ready` | Can this instance serve traffic? | `SELECT 1` on Postgres, Redis `PING`, and that the database's Alembic revision is the code's head. Each check has a 2 s timeout. | 200 when all pass, 503 otherwise. |

`/health/ready` answers with each dependency by name: `{"database": "ok", "redis": "error: timeout", "migrations": "ok", "status": "degraded", ...}`. A failure names the error *class*, never its message (a driver error can carry a hostname or a DSN). A migration mismatch names both revisions, which are not secret.

**Point restart probes at `/health` only.** Railway's healthcheck path is `/health`, and so is the Dockerfile `HEALTHCHECK` (checked 2026-10-07). Pointing a restart-on-failure probe at `/health/ready` would turn a Redis blip into a crash loop of a process that was fine. Use `/health/ready` for load-balancer readiness, a deploy smoke check (CI's compose job does), or an alert.

Rate limiting skips both endpoints.

## Startup validation

With `NOEMA_ENV=production` the API (in its lifespan) and the worker (at import) refuse to start, listing every problem at once, when any of these is wrong:

- `NOEMA_MASTER_KEY`, `NOEMA_SESSION_SECRET`: set, not a placeholder, base64 of 32 bytes
- `NOEMA_SECURE_COOKIES=true`; `NOEMA_CORS_ORIGINS` without `*`
- `DATABASE_URL` set explicitly, `postgresql…`; `REDIS_URL` set explicitly, `redis://` or `rediss://`
- `NOEMA_WEB_ORIGIN` set, `https://` (links in emails and Stripe redirects)
- `NOEMA_DEFAULT_PROVIDER` and `NOEMA_EMBEDDING_PROVIDER` usable: `anthropic` needs `ANTHROPIC_API_KEY`, `openai` needs `OPENAI_API_KEY`, `ollama` needs `OLLAMA_BASE_URL`, `mock` is refused

Messages name the variable, never its value. Development and test stay permissive (the mock provider, empty keys, localhost).

## AI provider resilience

Every model call goes through `noema/providers/gateway.py`:

- **Timeout** per task class (`TIMEOUTS`: 15 s for intent classification up to 120 s for tutor chat and embeddings), on top of each provider's HTTP client timeout.
- **Retries**: 3 attempts, exponential backoff with full jitter (0.5 s base, 8 s cap), only for retryable errors (429, 5xx, transport). A 400 is not retried.
- **Fallback chain**: the default provider, then every other provider the deployment or the learner has a key for. Streaming falls back only before the first token.
- **Interleaving** (`NOEMA_AI_ROUTING=anthropic:50,openai:50`, unset by default): each call's first provider is picked by weight, sticky per teaching session (else per learner), among providers whose circuit is not open; the rest are its fallback chain. `anthropic:0,openai:100` drains Anthropic to fallback-only. Details: `docs/ai-providers.md`.
- **Circuit breaker** (`noema/providers/circuit.py`), per provider name, per process: 5 outage-class failures (timeout, transport error, 429, 5xx) within 60 s open it; while open, calls skip that provider and go straight to the next one; after 30 s one probe call is let through, and its result closes or reopens it. 4xx responses never count: the provider answered, and with BYOK a 401 may be one learner's bad key. When every provider in the chain is open the call fails at once with `CircuitOpen`.
- **Out of credit** (Anthropic's 400 "credit balance is too low", OpenAI's 429 `insufficient_quota`): the circuit opens on the first one, for `NOEMA_AI_BILLING_COOLDOWN_SECONDS` (600 s), and the call fails over at once. The ops view shows the error class `credit_exhausted`. Not for a learner's own key.
- **What the client sees**: `504 ai-timeout` for a timeout, `502 provider-unavailable` otherwise, with a fixed sentence. Streams send an `error` event with the same neutral message. The provider's own text goes to logs only.

## Request ids

Every response carries `X-Request-ID`. An incoming one is kept when it is 8–128 characters of `[A-Za-z0-9._:-]`; anything else is replaced with a UUID. The id is:

- bound into every structlog line for the request (`request_id`),
- written to `ai_usage.request_id` for every model call the request made (indexed),
- carried into Dramatiq jobs enqueued during the request (message option `request_id`); the job's logs carry it, plus `job` and `message_id`.

To follow one request: search the logs for its id, then `SELECT * FROM ai_usage WHERE request_id = '…'`.

## Lesson lifecycle facts

`learning_events` holds `lesson_started`, `lesson_completed` and `session_abandoned`, unique on (owner, kind, source). `session_abandoned` is written lazily when a learner starts a new lesson, and for everyone by the `sweep_abandoned_sessions` actor: trigger it like `purge_accounts`, from a cron:

```
python -c "from noema.workers import sweep_abandoned_sessions; sweep_abandoned_sessions.send()"
```

Threshold: `NOEMA_SESSION_ABANDONED_AFTER_HOURS` (default 24, 0 disables).

## Admin ops view

`GET /api/v1/admin/ops` (admin allowlist plus two-step verification), shown in the Operations section of `/admin`:

- readiness checks, as above;
- each configured provider (default, embeddings, fallbacks) and any BYOK-only provider this process has called: circuit state, recent failures, last error class, when the circuit last opened;
- Dramatiq `default` queue depth and dead letters (`HLEN` on the broker's message hashes);
- the newest object under `postgres/` in the backup bucket, when read credentials are configured (`NOEMA_BACKUP_BUCKET`, `NOEMA_BACKUP_ENDPOINT_URL`, `NOEMA_BACKUP_REGION`, `NOEMA_BACKUP_ACCESS_KEY_ID`, `NOEMA_BACKUP_SECRET_ACCESS_KEY`); "stale" past 36 h; "unknown" without credentials;
- last 24 h: AI calls and failed AI calls (`ai_usage`), failed uploads (`sources`), feedback reports;
- last 24 h per provider (`ai_providers`): calls served, failovers in (served for another provider), failovers out (meant for it, served by another, from `ai_usage.failed_over_from`), errors, cost. Cost counts only models priced in `model_tier_config`, so OpenAI shows 0 until priced.

Circuit state is per process and resets on deploy. HTTP 5xx counts are not stored by the API; read them from the platform's metrics.

## Backups

Nightly `pg_dump` by the `db-backup` cron service. What runs, retention and restore steps: `docs/backups.md`.
